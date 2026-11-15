"""Geometry for two-corner location footprint drawing, in world metres."""
import math


def dimensioned_rectangle(centre, text):
    """Width,height[,counterclockwise degrees] centred on a location anchor."""
    parts = text.split(',')
    if len(parts) not in (2, 3):
        raise ValueError('Enter width,height or width,height,angle.')
    try:
        width, height = map(float, parts[:2])
        angle = float(parts[2]) if len(parts) == 3 else 0.
        cx, cy = map(float, centre)
    except (TypeError, ValueError):
        raise ValueError('Dimensions and angle must be finite numbers.') from None
    if not all(math.isfinite(v) for v in (width, height, angle, cx, cy)):
        raise ValueError('Dimensions and angle must be finite numbers.')
    if width < 1e-6 or height < 1e-6:
        raise ValueError('Width and height must be positive and at least 0.000001 m.')
    theta = math.radians(angle % 360)
    co, si = math.cos(theta), math.sin(theta)
    points = [dict(x=cx+x*co-y*si, y=cy+x*si+y*co) for x, y in
              [(-width/2,-height/2),(width/2,-height/2),(width/2,height/2),(-width/2,height/2)]]
    if not all(math.isfinite(p[k]) for p in points for k in ('x','y')):
        raise ValueError('The resulting rectangle coordinates must be finite.')
    return points, width, height, angle


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
