"""Build and query the AMR Simulator source graph without importing the application."""

import argparse
import ast
from collections import Counter, defaultdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile


TOOL = Path(__file__).resolve()
ANNOTATIONS = TOOL.with_name('amr_knowledge_links.json')
JS_PARSER = TOOL.with_name('amr_knowledge_js.cjs')
DEFAULT_ROOT = TOOL.parents[1]
CACHE = Path('.cache/amr-knowledge-graph/graph.json')
EXCLUDED = {'__pycache__', '.venv', 'node_modules', 'build', 'dist'}


def collect_sources(root):
    paths = set(root.glob('*.py')) | set(root.glob('*.mjs'))
    for directory in ('visualiser', 'report', 'installer', 'native'):
        paths.update(path for path in (root / directory).rglob('*')
                     if path.suffix in {'.py', '.spec', '.js', '.mjs', '.cjs'}
                     and not EXCLUDED.intersection(path.relative_to(root).parts))
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(paths)
            if path.is_file() and path.resolve().is_relative_to(root)}


def fingerprint(sources):
    return {name: sha256(data).hexdigest() for name, data in sources.items()} | {
        f'@tool/{path.name}': sha256(path.read_bytes()).hexdigest()
        for path in (TOOL, ANNOTATIONS, JS_PARSER)
    }


def module_name(path):
    return path.removesuffix('/__init__.py').removesuffix('.py').replace('/', '.')


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        if prefix:
            return f'{prefix}.{node.attr}'
    return None


class Scope:
    def __init__(self, symbol, parent=None, owner=None):
        self.symbol, self.parent, self.owner = symbol, parent, owner
        self.bindings = {}

    def bind(self, name, value):
        self.bindings[name] = value if self.bindings.get(name, value) == value else None

    def resolve(self, name):
        if name in self.bindings:
            return self.bindings[name]
        return self.parent.resolve(name) if self.parent else None


class PythonSource(ast.NodeVisitor):
    def __init__(self, graph, path, tree):
        self.graph, self.path, self.tree = graph, path, tree
        self.module = module_name(path)
        self.package = self.module if path.endswith('/__init__.py') else self.module.rpartition('.')[0]
        self.scope = Scope(self.module)
        self.scopes = {}
        self.imports = []
        self.graph.add_symbol(self.module, 'module', path, 1, tree.body[-1].end_lineno if tree.body else 1,
                              ast.get_docstring(tree))
        self.visit(tree)

    def visit_definition(self, node, kind):
        parent = self.scope
        qualified = f'{parent.symbol}.{node.name}'
        symbol = self.graph.add_symbol(qualified, kind, self.path, node.lineno, node.end_lineno,
                                       ast.get_docstring(node))
        parent.bind(node.name, qualified)
        self.graph.edge(parent.symbol, symbol, 'defines', self.path, node.lineno)
        if kind == 'class':
            scope = Scope(symbol, parent)
        else:
            lexical = parent.parent if kind == 'method' else parent
            scope = Scope(symbol, lexical, parent.symbol if kind == 'method' else None)
            arguments = node.args
            parameters = arguments.posonlyargs + arguments.args + arguments.kwonlyargs
            for parameter in [*parameters, arguments.vararg, arguments.kwarg]:
                if parameter:
                    scope.bind(parameter.arg, None)
            if scope.owner and parameters and parameters[0].arg in ('self', 'cls'):
                scope.bindings[parameters[0].arg] = scope.owner
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            if len(body) >= 3:
                signature = ast.dump(arguments, include_attributes=False)
                content = '\n'.join(ast.dump(statement, include_attributes=False) for statement in body)
                self.graph.clones[sha256((signature + content).encode()).hexdigest()].append(symbol)
        self.scopes[node] = scope
        self.scope = scope
        for child in node.body:
            self.visit(child)
        self.scope = parent

    def visit_FunctionDef(self, node):
        kind = 'method' if self.graph.nodes[self.scope.symbol]['kind'] == 'class' else 'function'
        self.visit_definition(node, kind)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.visit_definition(node, 'class')

    def add_import(self, alias, target, node, binding=None):
        self.scope.bind(alias, binding or target)
        self.imports.append((self.scope.symbol, target, node.lineno))

    def visit_Import(self, node):
        for item in node.names:
            base = item.name.split('.')[0]
            self.add_import(item.asname or base, item.name, node, None if item.asname else base)

    def visit_ImportFrom(self, node):
        source = node.module or ''
        if node.level:
            try:
                source = importlib.util.resolve_name('.' * node.level + source, self.package)
            except (ImportError, ValueError):
                self.graph.unresolved(self.scope.symbol, 'relative import', node.lineno, source)
                return
        for item in node.names:
            if item.name == '*':
                self.graph.unresolved(self.scope.symbol, 'star import', node.lineno, source)
            else:
                self.add_import(item.asname or item.name, f'{source}.{item.name}', node)

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.scope.bind(node.id, None)


class Calls(ast.NodeVisitor):
    def __init__(self, source):
        self.source = source
        self.graph = source.graph
        self.scope = source.scope
        for caller, target, line in source.imports:
            candidate = target
            while candidate and not self.graph.reference(candidate):
                candidate = candidate.rpartition('.')[0]
            if candidate:
                self.edge(caller, self.graph.reference(candidate), 'imports', line)
        self.visit(source.tree)

    def edge(self, caller, target, relation, line):
        self.graph.edge(caller, target, relation, self.source.path, line)

    def visit_definition(self, node):
        parent = self.scope
        self.scope = self.source.scopes[node]
        for child in node.body:
            self.visit(child)
        self.scope = parent

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = visit_definition

    def target(self, node):
        name = dotted(node)
        if not name:
            return None
        first, *tail = name.split('.')
        binding = self.scope.resolve(first)
        return self.graph.reference('.'.join([binding, *tail])) if binding else None

    def visit_Call(self, node):
        name = dotted(node.func)
        target = self.target(node.func)
        caller = self.scope.symbol
        if target:
            self.edge(caller, target, 'calls', node.lineno)
        elif name and name.endswith('.connect') and node.args:
            callback = self.target(node.args[0])
            if callback:
                self.edge(caller, callback, 'connects Qt callback', node.lineno)
            else:
                self.graph.unresolved(caller, 'Qt callback', node.lineno, dotted(node.args[0]))
        else:
            self.graph.unresolved(caller, 'call target', node.lineno, name)
        self.generic_visit(node)

    def visit_If(self, node):
        test = node.test
        if (self.scope.parent is None and isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name) and test.left.id == '__name__'
                and len(test.comparators) == 1 and isinstance(test.ops[0], ast.Eq)
                and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == '__main__'):
            self.graph.nodes[self.scope.symbol]['entry_point'] = True
            for call in (child for statement in node.body for child in ast.walk(statement)
                         if isinstance(child, ast.Call)):
                target = self.target(call.func)
                if target:
                    self.edge(self.scope.symbol, target, 'entry point', call.lineno)
        self.generic_visit(node)


class Graph:
    def __init__(self):
        self.nodes = {}
        self.qualified = defaultdict(list)
        self.edges = set()
        self.gaps = defaultdict(lambda: {'count': 0, 'examples': []})
        self.clones = defaultdict(list)
        self.errors = {}

    def add_symbol(self, qualified, kind, path, line, end, doc=None):
        symbol = qualified if qualified not in self.nodes else f'{qualified}@{line}'
        self.qualified[qualified].append(symbol)
        self.nodes[symbol] = {'id': symbol, 'name': qualified, 'kind': kind, 'path': path,
                              'line': line, 'end': end, 'summary': doc.splitlines()[0] if doc else ''}
        return symbol

    def unique(self, name):
        choices = self.qualified.get(name, ())
        return choices[0] if len(choices) == 1 else None

    def reference(self, name):
        if name in self.qualified:
            return self.unique(name)
        # Legacy entry points add these directories to sys.path for flat imports.
        module = name.partition('.')[0]
        alternatives = [self.unique(f'{prefix}.{name}') for prefix in ('visualiser', 'report')
                        if f'{prefix}.{module}' in self.nodes
                        and self.nodes[f'{prefix}.{module}']['kind'] == 'module']
        return alternatives[0] if len(alternatives) == 1 else None

    def edge(self, source, target, relation, path, line):
        self.edges.add((source, target, relation, path, line))

    def unresolved(self, caller, kind, line, name):
        gap = self.gaps[(caller, kind)]
        gap['count'] += 1
        if len(gap['examples']) < 3:
            gap['examples'].append({'line': line, 'expression': name or '<dynamic>'})

    def javascript(self, paths):
        if not paths:
            return
        try:
            run = subprocess.run(['node', '--expose-internals', str(JS_PARSER)], input=json.dumps(paths),
                                 text=True, encoding='utf-8', capture_output=True, timeout=20, check=True)
            documents = json.loads(run.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self.errors.update(dict.fromkeys(paths, f'JavaScript parser unavailable: {error}'))
            return
        for path, document in documents.items():
            if 'error' in document:
                self.errors[path] = document['error']
                continue
            module = self.add_symbol(path, 'module', path, 1, paths[path].count('\n') + 1)
            self.nodes[module]['entry_point'] = True
            for item in document['symbols']:
                qualified = f'{module}::{item["name"]}'
                symbol = self.add_symbol(qualified, item['kind'], path, item['line'], item['end'])
                parent = self.unique(f'{module}::{item["parent"]}') if item['parent'] else module
                self.edge(parent or module, symbol, 'defines', path, item['line'])
            for item in document['calls']:
                parent = self.unique(f'{module}::{item["caller"]}') if item['caller'] else module
                target = self.unique(f'{module}::{item["target"]}') if item['resolved'] else None
                if parent and target:
                    self.edge(parent, target, 'calls', path, item['line'])
                else:
                    self.unresolved(parent or module, 'JavaScript call target', item['line'], item['target'])

    def annotate(self, sources):
        annotations = json.loads(ANNOTATIONS.read_text(encoding='utf-8'))
        for name, description in annotations['artifacts'].items():
            self.add_symbol(name, 'data artifact', None, None, None, description)
        for topic, names in annotations['capabilities'].items():
            capability = self.add_symbol(topic, 'capability', None, None, None)
            for name in names:
                target = self.unique(name)
                if not target:
                    self.errors[f'capability {topic} → {name}'] = 'Source symbol missing or ambiguous'
                    continue
                node = self.nodes[target]
                self.edge(capability, target, 'implemented by', node['path'], node['line'])
        for source, target, relation, anchor in annotations['links']:
            origin, destination = self.unique(source), self.unique(target)
            if origin and destination:
                node = self.nodes[origin]
                path, start, end = node['path'], node['line'], node['end']
                lines = sources[path].decode('utf-8-sig').splitlines()
                matches = [index for index in range(start, min(end, len(lines)) + 1)
                           if anchor in lines[index - 1]]
                if len(matches) == 1:
                    self.edge(origin, destination, relation, path, matches[0])
                    continue
            self.errors[f'link {source} → {target}'] = f'Symbol or unique anchor missing: {anchor}'

    def export(self, hashes):
        return {'source_hashes': hashes, 'nodes': self.nodes, 'edges': sorted(self.edges),
                'coverage': {'symbols': dict(Counter(node['kind'] for node in self.nodes.values())),
                             'edges': dict(sorted(Counter(edge[2] for edge in self.edges).items())),
                             'unresolved': sum(gap['count'] for gap in self.gaps.values()),
                             'errors': self.errors},
                'unresolved': [{'caller': caller, 'kind': kind, **value}
                               for (caller, kind), value in self.gaps.items()],
                'exact_body_candidates': [group for group in self.clones.values()
                                          if len({self.nodes[item]['path'] for item in group}) > 1]}


def build(sources, hashes, cache):
    graph = Graph()
    python_sources, javascript = [], {}
    for path, data in sources.items():
        try:
            if Path(path).suffix in {'.py', '.spec'}:
                python_sources.append(PythonSource(graph, path, ast.parse(data, filename=path)))
            else:
                javascript[path] = data.decode('utf-8-sig')
        except (SyntaxError, UnicodeError) as error:
            graph.errors[path] = str(error)
    for source in python_sources:
        Calls(source)
    graph.javascript(javascript)
    graph.annotate(sources)
    result = graph.export(hashes)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=cache.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
    try:
        temporary.replace(cache)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def read_cache(cache):
    try:
        graph = json.loads(cache.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return {}
    return graph if isinstance(graph, dict) and {'nodes', 'edges', 'coverage'} <= graph.keys() else {}


def tokens(value):
    value = re.sub(r'([a-z\d])([A-Z])', r'\1 \2', value)
    return re.findall(r'[a-z0-9]+', value.lower())


def find(graph, query):
    query_words = tokens(query)
    if not query_words:
        return []
    matches = []
    for node in graph['nodes'].values():
        name, leaf = node['name'], re.split(r'\.|::', node['name'])[-1]
        words = tokens(name)
        context = words + tokens(node['summary'])
        if query.lower() in {node['id'].lower(), name.lower(), leaf.lower()}:
            rank = 0
        elif all(any(word.startswith(part) for word in words) for part in query_words):
            rank = 1
        elif all(any(word.startswith(part) for word in context) for part in query_words):
            rank = 2
        else:
            continue
        matches.append((rank, node['kind'] != 'capability', len(name), node['id'], node))
    return [node for *_, node in sorted(matches)]


def refs(graph, query):
    nodes = graph['nodes']
    matches = ([nodes[query]] if query in nodes
               else [node for node in nodes.values() if query == node['name']])
    if len(matches) != 1:
        return None
    node = matches[0]
    incoming, outgoing = [], []
    for source, target, relation, path, line in graph['edges']:
        if node['id'] == source:
            outgoing.append({'relation': relation, 'node': nodes[target], 'path': path, 'line': line})
        if node['id'] == target:
            incoming.append({'relation': relation, 'node': nodes[source], 'path': path, 'line': line})
    return {'symbol': node, 'incoming': incoming, 'outgoing': outgoing,
            'unresolved': [gap for gap in graph['unresolved'] if gap['caller'] == node['id']]}


def location(node):
    return f'{node["id"]} [{node["path"]}:{node["line"]}]' if node['path'] else node['id']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--cache', type=Path, help='Override the generated graph path')
    parser.add_argument('--json', action='store_true', help='Emit machine-readable output')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('build', 'check', 'find', 'refs'):
        command = commands.add_parser(name)
        if name in ('find', 'refs'):
            command.add_argument('query')
        if name == 'find':
            command.add_argument('--limit', type=int, default=15)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / 'amr_app.py').is_file():
        parser.error(f'AMR Simulator source root not found at {root}')
    cache = args.cache or root / CACHE
    sources = collect_sources(root)
    hashes = fingerprint(sources)
    graph = read_cache(cache)
    current = graph.get('source_hashes') == hashes
    if args.command == 'check' and not current:
        print('Graph missing or stale. Run build.', file=sys.stderr)
        return 1
    if args.command == 'build' or not current:
        graph = build(sources, hashes, cache)
    coverage = graph['coverage']
    if args.command in ('build', 'check'):
        print(json.dumps({'cache': str(cache), 'source_files': len(sources), **coverage}, indent=2))
        return 2 if coverage['errors'] else 0
    if coverage['errors']:
        print('Graph is partial. Run check for details.', file=sys.stderr)
    if args.command == 'find':
        matches = find(graph, args.query)[:max(1, args.limit)]
        for item in matches:
            if item['kind'] == 'capability':
                item['implemented_by'] = [edge['node'] for edge in refs(graph, item['id'])['outgoing']]
        if args.json:
            print(json.dumps(matches, indent=2))
        else:
            for item in matches:
                print(f'{location(item)} ({item["kind"]})')
                for definition in item.get('implemented_by', ()):
                    print(f'  {location(definition)}')
        return 0 if matches else 1
    result = refs(graph, args.query)
    if result is None:
        print('Provide an exact, unambiguous ID from find.', file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(location(result['symbol']))
        for direction in ('incoming', 'outgoing'):
            for edge in result[direction]:
                print(f'  {direction:8} {edge["relation"]}: {location(edge["node"])}'
                      f' via {edge["path"]}:{edge["line"]}')
        for gap in result['unresolved']:
            examples = ', '.join(f'{item["expression"]} at {item["line"]}' for item in gap['examples'])
            print(f'  unresolved {gap["kind"]}: {gap["count"]} ({examples})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
