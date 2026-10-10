"""Check documentation navigation/assets and optionally the rendered Pages site.

Uses only the Python standard library; run from any working directory.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit

DOCS = Path(__file__).resolve().parent
BASE = '/AMR_Simulator'
EXCLUDED = {'building-tutorial/COVERAGE.md'}


def front_matter(path: Path):
    text = path.read_text(encoding='utf-8-sig')
    match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
    if not match:
        raise ValueError('missing YAML front matter')
    values = {}
    for line in match[1].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition(':')
        if not separator or not key.strip() or key.strip() in values:
            raise ValueError(f'invalid or duplicate front-matter key: {line}')
        values[key.strip()] = value.strip().strip('\"\'')
    return values, text[match.end():]


def page_url(path: Path, values: dict):
    if 'permalink' in values:
        return BASE + values['permalink']
    # The site uses Jekyll's pretty permalinks for Markdown pages.
    return BASE + '/' + path.relative_to(DOCS).with_suffix('').as_posix() + '/'


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.add(values['id'])
        for attribute in ('href', 'src'):
            if values.get(attribute):
                self.links.append(values[attribute])


def rendered_path(folder: Path, url: str):
    path = unquote(urlsplit(url).path)
    if path != BASE and not path.startswith(BASE + '/'):
        raise ValueError(f'local link omits project prefix: {url}')
    relative = path[len(BASE):].lstrip('/')
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder.resolve()):
        raise ValueError(f'link escapes rendered site: {url}')
    if target.is_dir() or path.endswith('/'):
        target /= 'index.html'
    if not target.exists() and not target.suffix:
        target = target.with_suffix('.html')
    return target


def validate(built_site: Path | None):
    errors = []
    pages = {}
    source_links = 0
    config = (DOCS / '_config.yml').read_text(encoding='utf-8')
    for required in ('baseurl: "/AMR_Simulator"', 'url: "https://bomtellis.github.io"',
                     'remote_theme: just-the-docs/just-the-docs@v0.12.0',
                     'search_enabled: true', 'jekyll-relative-links'):
        if required not in config:
            errors.append(f'_config.yml: missing {required}')
    if (DOCS / '.nojekyll').exists():
        errors.append('.nojekyll disables this site\'s required Jekyll build')

    for path in sorted(DOCS.rglob('*.md')):
        relative = path.relative_to(DOCS).as_posix()
        if relative in EXCLUDED or relative.startswith(('_build/', '.')):
            continue
        try:
            values, body = front_matter(path)
            if not values.get('title'):
                raise ValueError('missing title')
            pages[path] = values
            # Samples of Markdown syntax in code fences are not real links.
            body = re.sub(r'^```.*?^```[^\n]*', '', body, flags=re.M | re.S)
            for destination in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', body):
                destination = destination.strip()
                if '{{' in destination or '{%' in destination:
                    continue
                destination = destination.split(' "', 1)[0].strip('<>')
                parsed = urlsplit(destination)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                if parsed.path.startswith('/'):
                    errors.append(f'{relative}: use relative source links: {destination}')
                    continue
                target = (path.parent / unquote(parsed.path)).resolve()
                if not target.is_relative_to(DOCS):
                    errors.append(f'{relative}: source link leaves docs: {destination}')
                elif not target.is_file():
                    errors.append(f'{relative}: missing local target: {destination}')
                elif target.suffix == '.md' and target.relative_to(DOCS).as_posix() in EXCLUDED:
                    errors.append(f'{relative}: link to excluded page: {destination}')
                source_links += 1
        except ValueError as exc:
            errors.append(f'{relative}: {exc}')

    visible = {path: data for path, data in pages.items() if data.get('nav_exclude') != 'true'}
    titles = {}
    positions = {}
    urls = {}
    for path, values in visible.items():
        title = values['title']
        if title in titles:
            errors.append(f'duplicate navigation title: {title}')
        titles[title] = path
        order = values.get('nav_order', '')
        if not order.isdigit():
            errors.append(f'{path.name}: missing numeric navigation order')
        position = (values.get('parent'), order)
        if position in positions:
            errors.append(f'duplicate sibling navigation position: {position}')
        positions[position] = path
        url = page_url(path, values)
        if url in urls:
            errors.append(f'duplicate published URL: {url}')
        urls[url] = path
    for path, values in visible.items():
        parent = values.get('parent')
        if parent:
            if parent not in titles:
                errors.append(f'{path.name}: unknown parent {parent}')
            elif pages[titles[parent]].get('has_children') != 'true':
                errors.append(f'{parent}: parent needs has_children: true')
    identity = (DOCS / '_data/source.yml').read_text(encoding='utf-8')
    if not re.search(r'^commit: [0-9a-f]{40}$', identity, re.M):
        errors.append('_data/source.yml: missing complete reviewed commit')

    rendered_links = 0
    if built_site:
        folder = built_site.resolve()
        parsed_files = {}
        for path in folder.rglob('*.html'):
            parser = HTMLLinks()
            text = path.read_text(encoding='utf-8')
            if '{% ' in text or '{{ site.' in text:
                errors.append(f'{path.name}: unrendered Liquid')
            parser.feed(text)
            parsed_files[path.resolve()] = parser
        for url in urls:
            target = rendered_path(folder, url)
            if not target.is_file():
                errors.append(f'missing rendered page: {url}')
        for path, parser in parsed_files.items():
            relative = path.relative_to(folder).as_posix()
            current_url = BASE + '/' + relative
            if current_url.endswith('/index.html'):
                current_url = current_url[:-len('index.html')]
            for link in parser.links:
                split = urlsplit(link)
                if split.scheme or split.netloc:
                    continue
                try:
                    resolved = urljoin(current_url, link)
                    target = rendered_path(folder, resolved)
                    if not target.is_file():
                        errors.append(f'{relative}: missing rendered target {link}')
                    elif split.fragment and target in parsed_files:
                        fragment = unquote(split.fragment)
                        if fragment not in parsed_files[target].ids:
                            errors.append(f'{relative}: missing anchor {link}')
                    rendered_links += 1
                except ValueError as exc:
                    errors.append(f'{relative}: {exc}')
        search_path = folder / 'assets/js/search-data.json'
        if not search_path.is_file():
            errors.append('missing generated search index: assets/js/search-data.json')
        else:
            try:
                search = json.loads(search_path.read_text(encoding='utf-8'))
                if not search:
                    errors.append('empty generated search index')
                for item in search.values() if isinstance(search, dict) else search:
                    if isinstance(item, dict) and item.get('url'):
                        target = rendered_path(folder, item['url'])
                        if not target.is_file():
                            errors.append(f'missing search-result target: {item["url"]}')
            except (ValueError, TypeError) as exc:
                errors.append(f'invalid search index: {exc}')

    if errors:
        for error in sorted(set(errors)):
            print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(f'PASS: {len(pages)} pages; {source_links} source links/assets; '
          f'{len(visible)} navigation entries; {rendered_links} rendered links.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built-site', type=Path, help='Jekyll output folder to check')
    arguments = parser.parse_args()
    sys.exit(validate(arguments.built_site))
