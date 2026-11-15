"""Theme-aware CAD map presentation; no project geometry or simulation edits."""
import math


def contrast_colour(colour, background, minimum=4.5):
    """Keep a saved colour where readable, otherwise blend toward black/white.

    The adjusted colour is display-only. Route style preferences remain intact.
    """
    from appearance import contrast
    if contrast(colour, background) >= minimum:
        return colour
    end = max(('#000000', '#ffffff'), key=lambda c: contrast(c, background))
    origin = [int(colour[i:i+2],16) for i in (1,3,5)]
    target = [int(end[i:i+2],16) for i in (1,3,5)]
    for step in range(1,101):
        blended = '#' + ''.join(f'{round(a+(b-a)*step/100):02x}' for a,b in zip(origin,target))
        if contrast(blended, background) >= minimum:
            return blended
    return end


def map_colours(value):
    presets = {
        'Light': dict(background='#fbfdff', panel='#ffffff', text='#172b4d',
                      minor='#eaf0f6', major='#d6e1ee', border='#a9bacf', accent='#0065cc'),
        'Dark': dict(background='#151a20', panel='#20252b', text='#f2f5f8',
                     minor='#202b37', major='#344355', border='#8995a3', accent='#80c7ff'),
        'High contrast': dict(background='#000000', panel='#000000', text='#ffffff',
                              minor='#262626', major='#515151', border='#ffffff', accent='#ffff00'),
    }
    result = dict(presets[value.theme])
    if value.map_background_colour:
        result['background'] = result['panel'] = value.map_background_colour
        result['minor'] = contrast_colour(result['minor'], result['background'], 1.12)
        result['major'] = contrast_colour(result['major'], result['background'], 1.3)
    if value.map_text_colour != 'auto':
        result['text'] = value.map_text_colour
    else:
        result['text'] = contrast_colour(result['text'], result['background'])
    result['accent'] = contrast_colour(value.accent_colour or result['accent'], result['background'], 3)
    for key, colour in dict(none='#2563ad', staff='#00788a', public='#aa5900', both='#8947a0',
                            location='#008353', node='#8a6500', door='#a34d00',
                            department='#008578', lift='#bf403a', muted='#718096').items():
        result[key] = contrast_colour(colour, result['background'], 3)
    return result


def _nice_floor(value):
    power = 10 ** math.floor(math.log10(value))
    return max(factor*power for factor in (1,2,5,10) if factor*power <= value*(1+1e-12))


def adaptive_grid(bounds, pixels_per_metre, *, max_lines=180):
    """Return (spacing_metres, scene_lines), bounded independently of zoom.

    Lines lie on actual world-metre multiples. Scene Y is reflected world Y,
    so the same multiples apply. Every fifth line receives major styling.
    """
    x0,y0,x1,y1 = bounds
    if (not all(math.isfinite(v) for v in (*bounds,pixels_per_metre)) or pixels_per_metre <= 0
            or x1 <= x0 or y1 <= y0 or max_lines < 4):
        return 0, []
    target_spacing = 40/pixels_per_metre
    span = (x1-x0)+(y1-y0)
    if not math.isfinite(target_spacing) or not math.isfinite(span) or target_spacing <= 0:
        return 0, []
    spacing = _nice_floor(target_spacing)
    while span/spacing + 4 > max_lines:
        spacing *= 2
    if not math.isfinite(spacing) or any(abs(v/spacing) > 1e14 for v in bounds):
        return 0, []  # Grid precision is exhausted; do not invent misplaced lines.
    lines = []
    for index in range(math.ceil(x0/spacing),math.floor(x1/spacing)+1):
        x = index*spacing
        lines.append((x,y0,x,y1,index % 5 == 0))
    for index in range(math.ceil(y0/spacing),math.floor(y1/spacing)+1):
        y = index*spacing
        lines.append((x0,y,x1,y,index % 5 == 0))
    return spacing, lines


def scale_bar(pixels_per_metre, target_pixels=120):
    if (not all(math.isfinite(v) and v > 0 for v in (pixels_per_metre,target_pixels))
            or not math.isfinite(target_pixels/pixels_per_metre) or target_pixels/pixels_per_metre == 0):
        return None
    metres = _nice_floor(target_pixels/pixels_per_metre)
    return metres, metres*pixels_per_metre


def compact_legend(profile=None, show_blocked=False):
    lines = ['Map key', '○ Location   □ Node   D Door', '◇ Department / lift   → One-way']
    if profile:
        lines.extend([f'Profile: {profile}', 'Names + patterns show access, not lanes'])
        if show_blocked:lines.append('Dotted arrows: blocked directions')
    return lines


class ContrastRouteStyles:
    """Read-only adapter for existing user colours on a different map theme."""
    def __init__(self, styles, background):
        self.styles, self.background = styles, background

    def get(self, name):
        style = self.styles.get(name)
        return dict(style, colour=contrast_colour(style['colour'], self.background))
