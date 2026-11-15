"""Disposable, data-only caches for prepared vector report underlays."""
from concurrent.futures import Future
import gzip
import json
import math
import os
from pathlib import Path
import tempfile
from threading import Lock
import zlib

import reportlab
from reportlab.graphics import shapes
from reportlab.lib.colors import Color
try:
    from svglib.svglib import NoStrokePath
except ImportError:
    NoStrokePath = None


# Explicit primitive types: cache files never contain executable Python/pickles.
_SHAPES = {cls.__name__: cls for cls in (
    shapes.Drawing, shapes.Group, shapes.Path, shapes.Rect, shapes.Line,
    shapes.PolyLine, shapes.Polygon, shapes.Circle, shapes.Ellipse, shapes.String,
)}
if NoStrokePath is not None:
    _SHAPES['NoStrokePath'] = NoStrokePath
_VERSION = 'vector-scene-1/' + reportlab.Version


def simplify_groups(drawing):
    """Remove SVG wrapper groups that change neither geometry nor styling."""
    def visit(node):
        children = getattr(node, 'contents', None)
        if children is None:
            return
        simplified = []
        for child in children:
            visit(child)
            if (type(child) is shapes.Group
                    and set(child.getProperties()) == {'contents', 'transform'}
                    and tuple(child.transform) == (1, 0, 0, 1, 0, 0)):
                simplified.extend(child.contents)
            else:
                simplified.append(child)
        node.contents = simplified
    visit(drawing)
    return drawing


def _encode(value):
    if type(value) in _SHAPES.values():
        return {'shape': type(value).__name__,
                'properties': {key: _encode(item) for key, item in value.getProperties().items()}}
    if type(value) is Color:
        return {'rgba': [value.red, value.green, value.blue, value.alpha]}
    if isinstance(value, (tuple, list)):
        # Most lists contain only path coordinates/operators. Let the JSON
        # encoder handle these directly rather than visiting every number.
        if not value or isinstance(value[0], (int, float, str)):
            return value
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f'Unsupported drawing cache value: {type(value).__name__}')


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {'rgba'}:
            return Color(*value['rgba'])
        if set(value) != {'shape', 'properties'}:
            raise ValueError('Invalid drawing cache object')
        cls = _SHAPES[value['shape']]
        properties = value['properties']
        if not set(properties).issubset(cls._attrMap):
            raise ValueError('Invalid drawing cache properties')
        node = cls.__new__(cls)
        node.__dict__.update({key: _decode(item) for key, item in properties.items()})
        return node
    if isinstance(value, list) and value and isinstance(value[0], (dict, list)):
        return [_decode(item) for item in value]
    return value


def _extents(value):
    result = tuple(float(item) for item in value)
    if (len(result) != 4 or not all(math.isfinite(item) for item in result)
            or result[0] >= result[1] or result[2] >= result[3]):
        raise ValueError('Invalid cached drawing bounds')
    return result


def _stamp(svg):
    stat = svg.stat()
    return [stat.st_size, stat.st_mtime_ns]


def _atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_svg(path, svg_string):
    # Different reports may prepare the same content-addressed drawing at once.
    # Publish complete SVGs only, so another reader never sees a partial file.
    _atomic_write(Path(path), svg_string.encode('utf-8'))


def load_bounds(svg):
    try:
        payload = json.loads(svg.with_suffix('.bounds.json').read_text(encoding='utf-8'))
        if payload['svg'] == _stamp(svg):
            return _extents(payload['extents'])
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def save_bounds(svg, extents):
    try:
        payload = {'svg': _stamp(svg), 'extents': _extents(extents)}
        _atomic_write(svg.with_suffix('.bounds.json'), json.dumps(payload).encode('utf-8'))
    except (OSError, ValueError, TypeError):
        pass  # A cache write failure must not prevent report generation.


def load_scene(svg):
    try:
        payload = json.loads(gzip.decompress(svg.with_suffix('.scene.json.gz').read_bytes()))
        if payload['version'] != _VERSION or payload['svg'] != _stamp(svg):
            return None
        drawing = _decode(payload['drawing'])
        if not isinstance(drawing, shapes.Drawing):
            return None
        return drawing
    except (OSError, EOFError, ValueError, TypeError, KeyError, AttributeError, zlib.error):
        return None


def save_scene(svg, drawing):
    try:
        payload = {'version': _VERSION, 'svg': _stamp(svg), 'drawing': _encode(drawing)}
        data = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
        _atomic_write(svg.with_suffix('.scene.json.gz'), gzip.compress(data, compresslevel=1))
    except (OSError, ValueError, TypeError):
        pass


class DrawingPreparationCache:
    """Share one preparation per drawing within a report, including workers."""
    def __init__(self):
        self._lock = Lock()
        self._futures = {}

    def get(self, key, prepare):
        with self._lock:
            future = self._futures.get(key)
            owner = future is None
            if owner:
                future = self._futures[key] = Future()
        if owner:
            try:
                future.set_result(prepare())
            except BaseException as exc:
                future.set_exception(exc)
        return future.result()
