"""Geometry for two-corner location footprint drawing, in world metres."""
import math


def rectangle_points(first, second):
    x1, y1, x2, y2 = map(float, (*first, *second))
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        raise ValueError('Choose finite rectangle corners.')
    left, right = sorted((x1, x2))
    bottom, top = sorted((y1, y2))
    if right-left < 1e-6 or top-bottom < 1e-6:
        raise ValueError('The rectangle must have non-zero width and height.')
    return [dict(x=left,y=bottom), dict(x=right,y=bottom),
            dict(x=right,y=top), dict(x=left,y=top)]
