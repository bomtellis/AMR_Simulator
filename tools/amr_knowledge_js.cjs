// Parse workbook sources without evaluating application code or loading workbook dependencies.
const fs = require('node:fs');
let parser;
try {
  parser = require('acorn');
} catch {
  // Current Node distributions ship this parser. A standalone Acorn install also works.
  parser = require('internal/deps/acorn/acorn/dist/acorn');
}

function extract(source) {
  const tree = parser.parse(source, { ecmaVersion: 'latest', sourceType: 'module', locations: true });
  const symbols = [];
  const sites = [];
  const functions = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);

  function walk(node, parent, frame, caller) {
    if (!node?.type) return;
    if (node.type === 'BlockStatement' || node.type === 'CatchClause') {
      frame = { parent: frame, names: new Map() };
    }
    if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier'
        && !functions.has(node.init?.type)) {
      frame.names.set(node.id.name, null);
    }
    if (node.type === 'ImportDeclaration') {
      for (const item of node.specifiers) frame.names.set(item.local.name, null);
    }
    if (functions.has(node.type) || node.type === 'ClassDeclaration' || node.type === 'ClassExpression') {
      const method = parent?.type === 'MethodDefinition';
      const line = node.loc.start.line;
      const declared = node.id?.name ?? (parent?.type === 'VariableDeclarator' ? parent.id.name : undefined);
      const leaf = declared ?? (method && !parent.computed ? parent.key.name : undefined)
        ?? `<callback@${line}:${node.loc.start.column + 1}>`;
      const name = caller ? `${caller}.${leaf}` : leaf;
      const kind = node.type.startsWith('Class') ? 'class' : method ? 'method' : 'function';
      symbols.push({ name, kind, line, end: node.loc.end.line, parent: caller });
      if (declared && !method) frame.names.set(declared, name);
      caller = name;
      frame = { parent: frame, names: new Map() };
      for (const parameter of node.params ?? []) {
        if (parameter.type === 'Identifier') frame.names.set(parameter.name, null);
      }
    }
    if (node.type === 'CallExpression' || node.type === 'NewExpression') {
      const target = node.callee.type === 'Identifier' ? node.callee.name : null;
      sites.push({ caller, target, line: node.loc.start.line, frame });
    }
    for (const [key, value] of Object.entries(node)) {
      if (key === 'loc') continue;
      if (Array.isArray(value)) {
        for (const child of value) walk(child, node, frame, caller);
      } else {
        walk(value, node, frame, caller);
      }
    }
  }

  walk(tree, null, { parent: null, names: new Map() }, null);
  const calls = sites.map(({ caller, target, line, frame }) => {
    let scope = frame;
    while (scope && !scope.names.has(target)) scope = scope.parent;
    return { caller, target: scope?.names.get(target) ?? target, resolved: !!scope?.names.get(target), line };
  });
  return { symbols, calls };
}

const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const output = {};
for (const [path, source] of Object.entries(sources)) {
  try {
    output[path] = extract(source);
  } catch (error) {
    output[path] = { error: String(error) };
  }
}
process.stdout.write(JSON.stringify(output));
