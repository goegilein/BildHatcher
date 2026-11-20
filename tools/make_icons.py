"""BildHatcher's own pictograms: writes GUI_Files/icons/<meaning>.svg in one consistent style.

    python tools/make_icons.py            # write all icons defined here
    python tools/make_icons.py rotate     # only some

Style: 24 x 24 grid, round line ends, one dark outline colour (INK), flat fills, colour only where it means
something (red / green / blue channels, red = add / remove / the hatch centre, blue = movement /
transformation, cyan dashes = masks, black circled arrow = reset / restore).
Qt renders SVG Tiny: only plain shapes, paths, solid colours (no filters, masks, clip paths, CSS or text).
Icons drawn here replace the corresponding rows in GUI_Files/icons/SOURCES.md.
"""
import math
import re
import sys
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parents[1] / "GUI_Files" / "icons"

# --- style ---
INK = "#37474F"     # outlines
PAPER = "#FFFFFF"   # halo behind badges, paper, glass
SKY = "#E3F2FD"     # picture background
HILL = "#81C784"    # picture hills
SUN = "#FFB300"     # picture sun, sparkles
RED, GREEN, BLUE = "#E53935", "#43A047", "#1E88E5"
BLACK = "#263238"
MASK = "#0097B8"    # mask outlines (dashed)
MASK_FILL = "#E0F7FA"
GREY = "#CFD8DC"    # neutral bodies (database, bucket, robot)
WOOD = "#A1887F"    # stamp
TOPO = "#8D6E63"    # contour (relief) lines
CURRENT = "currentColor"  # recoloured at runtime (colour buttons of the Text section)
STROKE = 1.6        # outline width
LINE = 2.0          # arrows / symbols
DASH = "2.4 1.9"


def svg(*parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">\n'
            + "\n".join(p for p in parts if p) + "\n</svg>\n")


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pts(points):
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


def _dash(dash):
    return f' stroke-dasharray="{dash}"' if dash else ""


def line(points, color=INK, width=LINE, dash=None):
    return (f'<polyline points="{pts(points)}" fill="none" stroke="{color}" stroke-width="{f(width)}" '
            f'stroke-linecap="round" stroke-linejoin="round"{_dash(dash)}/>')


def polygon(points, fill, stroke="none", width=STROKE, dash=None):
    return (f'<polygon points="{pts(points)}" fill="{fill}" stroke="{stroke}" stroke-width="{f(width)}" '
            f'stroke-linejoin="round"{_dash(dash)}/>')


def path(d, fill="none", stroke=INK, width=STROKE, dash=None):
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{f(width)}" stroke-linecap="round" '
            f'stroke-linejoin="round"{_dash(dash)}/>')


def rect(x, y, w, h, fill, stroke=INK, width=STROKE, r=1.5, dash=None):
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{f(width)}"{_dash(dash)}/>')


def circle(cx, cy, r, fill, stroke=INK, width=STROKE, dash=None):
    return (f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{f(width)}"{_dash(dash)}/>')


def ellipse(cx, cy, rx, ry, fill, stroke=INK, width=STROKE, dash=None):
    return (f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(ry)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{f(width)}"{_dash(dash)}/>')


def place(points, origin, angle_deg=0, scale=1.0):
    """Rotate (degrees, clockwise on screen) and scale local points, then move them to `origin`."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(origin[0] + scale * (x * ca - y * sa), origin[1] + scale * (x * sa + y * ca)) for x, y in points]


def head(tip, direction, color, size=3.4):
    """Filled arrow head with its tip at `tip`, pointing along `direction` (dx, dy)."""
    dx, dy = direction
    n = math.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    bx, by = tip[0] - dx * size, tip[1] - dy * size
    px, py = -dy * size * 0.62, dx * size * 0.62
    return polygon([tip, (bx + px, by + py), (bx - px, by - py)], color, color, 0.8)


def arrow(start, tip, color=BLUE, width=LINE, size=3.4):
    """Straight arrow from `start` to `tip`."""
    dx, dy = tip[0] - start[0], tip[1] - start[1]
    n = math.hypot(dx, dy)
    end = (tip[0] - dx / n * (size - 0.6), tip[1] - dy / n * (size - 0.6))
    return line([start, end], color, width) + "\n" + head(tip, (dx, dy), color, size)


def double_arrow(a, b, color=INK, width=1.4, size=2.8):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    s = size - 0.5
    return "\n".join([line([(a[0] + ux * s, a[1] + uy * s), (b[0] - ux * s, b[1] - uy * s)], color, width),
                      head(a, (-dx, -dy), color, size), head(b, (dx, dy), color, size)])


def arc_arrow(cx, cy, r, start_deg, end_deg, color=BLUE, width=LINE, ccw=False, size=3.4):
    """Arc (screen coordinates, 0° = right, 90° = down) with an arrow head at the end; clockwise unless ccw."""
    sign = -1 if ccw else 1
    a0, a1 = math.radians(start_deg), math.radians(end_deg)
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    sweep = ((end_deg - start_deg) * sign) % 360
    back_deg = end_deg - sign * math.degrees(size * 0.8 / r)  # the head covers the last bit of the arc
    back = math.radians(back_deg)
    pe = (cx + r * math.cos(back), cy + r * math.sin(back))
    large = 1 if sweep - math.degrees(size * 0.8 / r) > 180 else 0
    d = f"M {f(p0[0])} {f(p0[1])} A {f(r)} {f(r)} 0 {large} {0 if ccw else 1} {f(pe[0])} {f(pe[1])}"
    tip = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    tangent = (-math.sin(a1) * sign, math.cos(a1) * sign)
    return path(d, "none", color, width) + "\n" + head(tip, tangent, color, size)


def reset_arrow(cx=12, cy=12, r=9.8):
    """Black circled arrow around a motif: reset / restore."""
    return arc_arrow(cx, cy, r, 235, 190, BLACK, 1.8)


def picture(x, y, w, h):
    """The picture motif: frame, sky, two hills, sun."""
    def at(u, v):
        return (x + u * w, y + v * h)
    hills = polygon([at(0.08, 0.88), at(0.38, 0.42), at(0.58, 0.68), at(0.72, 0.52), at(0.92, 0.88)], HILL)
    sun = f'<circle cx="{f(x + 0.72 * w)}" cy="{f(y + 0.28 * h)}" r="{f(min(w, h) * 0.11)}" fill="{SUN}"/>'
    return "\n".join([rect(x, y, w, h, SKY), hills, sun])


def badge(*strokes, color=RED):
    """Red symbol (one or more strokes) with a white halo, readable on top of the motif."""
    return "\n".join([line(s, PAPER, 4.6) for s in strokes] + [line(s, color, 2.4) for s in strokes])


PLUS = badge([(18.5, 15), (18.5, 22)], [(15, 18.5), (22, 18.5)])
MINUS = badge([(15, 18.5), (22, 18.5)])
CROSS = badge([(15.5, 15.5), (21.5, 21.5)], [(21.5, 15.5), (15.5, 21.5)])


def slash(a=(4, 3.5), b=(20, 20.5), color=INK):
    """Crossed out (with a white halo)."""
    return line([a, b], PAPER, 4.4) + "\n" + line([a, b], color, 2.0)


def sparkle(cx, cy, s, color=SUN):
    k = s * 0.28
    return polygon([(cx, cy - s), (cx + k, cy - k), (cx + s, cy), (cx + k, cy + k), (cx, cy + s), (cx - k, cy + k),
                    (cx - s, cy), (cx - k, cy - k)], color, color, 0.6)


# --- drops ---
def _drop_geometry(cx, cy, r, d=1.95):
    """Circle (cx, cy, r) with a tip d * r above its centre: tip, right / left tangent points, tangent angle."""
    a = math.acos(1 / d)
    tip = (cx, cy - d * r)
    right = (cx + r * math.sin(a), cy - r * math.cos(a))
    left = (cx - r * math.sin(a), cy - r * math.cos(a))
    return tip, right, left, a


def drop_path(cx, cy, r):
    tip, right, left, _ = _drop_geometry(cx, cy, r)
    return (f"M {f(tip[0])} {f(tip[1])} L {f(right[0])} {f(right[1])} "
            f"A {f(r)} {f(r)} 0 1 1 {f(left[0])} {f(left[1])} Z")


def drop(cx, cy, r, fill=BLUE, stroke=INK, width=1.4):
    return path(drop_path(cx, cy, r), fill, stroke, width)


def half_drop(cx, cy, r, fill_left=PAPER, fill_right=BLACK):
    """Drop with a white left and a black right half."""
    tip, right, left, _ = _drop_geometry(cx, cy, r)
    bottom = (cx, cy + r)
    d_right = (f"M {f(tip[0])} {f(tip[1])} L {f(right[0])} {f(right[1])} "
               f"A {f(r)} {f(r)} 0 0 1 {f(bottom[0])} {f(bottom[1])} Z")
    return "\n".join([path(drop_path(cx, cy, r), fill_left, "none"), path(d_right, fill_right, "none"),
                      path(drop_path(cx, cy, r), "none", INK, 1.4)])


def rgb_drop(cx, cy, r):
    """Drop cut like a cake into a red, a green and a blue piece."""
    tip, right, left, a = _drop_geometry(cx, cy, r)

    def at(deg):
        t = math.radians(deg)
        return (cx + r * math.cos(t), cy + r * math.sin(t))
    p30, p150 = at(30), at(150)
    c = f"{f(cx)} {f(cy)}"
    pieces = [
        (f"M {c} L {f(tip[0])} {f(tip[1])} L {f(right[0])} {f(right[1])} A {f(r)} {f(r)} 0 0 1 "
         f"{f(p30[0])} {f(p30[1])} Z", GREEN),
        (f"M {c} L {f(p30[0])} {f(p30[1])} A {f(r)} {f(r)} 0 0 1 {f(p150[0])} {f(p150[1])} Z", BLUE),
        (f"M {c} L {f(p150[0])} {f(p150[1])} A {f(r)} {f(r)} 0 0 1 {f(left[0])} {f(left[1])} "
         f"L {f(tip[0])} {f(tip[1])} Z", RED),
    ]
    return "\n".join([path(d, col, PAPER, 0.7) for d, col in pieces] + [path(drop_path(cx, cy, r), "none", INK, 1.4)])


# --- recurring motifs ---
def crosshair(cx, cy, r=4.2, color=RED):
    """The hatch centre."""
    return "\n".join([circle(cx, cy, r, "none", color, 1.6),
                      line([(cx - r - 2.4, cy), (cx - r + 1.6, cy)], color, 1.6),
                      line([(cx + r - 1.6, cy), (cx + r + 2.4, cy)], color, 1.6),
                      line([(cx, cy - r - 2.4), (cx, cy - r + 1.6)], color, 1.6),
                      line([(cx, cy + r - 1.6), (cx, cy + r + 2.4)], color, 1.6),
                      circle(cx, cy, 0.9, color, "none", 0)])


def eye(cx, cy, w=10, crossed=False):
    h = w * 0.36
    d = (f"M {f(cx - w / 2)} {f(cy)} Q {f(cx)} {f(cy - 2 * h)} {f(cx + w / 2)} {f(cy)} "
         f"Q {f(cx)} {f(cy + 2 * h)} {f(cx - w / 2)} {f(cy)} Z")
    parts = [path(d, PAPER, PAPER, 3.6), path(d, PAPER, INK, 1.4), circle(cx, cy, h * 0.95, BLUE, "none", 0),
             circle(cx, cy, h * 0.42, BLACK, "none", 0)]
    if crossed:
        parts.append(slash((cx - w / 2 + 0.6, cy + h * 1.9), (cx + w / 2 - 0.6, cy - h * 1.9)))
    return "\n".join(parts)


def cursor(tip, scale=1.0):
    """Mouse arrow with its tip at `tip`."""
    shape = [(0, 0), (0, 11), (2.7, 8.4), (4.6, 12.6), (6.5, 11.7), (4.7, 7.6), (8.3, 7.6)]
    return polygon(place(shape, tip, 0, scale), PAPER, INK, 1.3)


def transform_path(d, origin, scale=1.0):
    """Scale a path written with absolute M / L / Q / C / A / Z commands and move its (0, 0) to `origin`."""
    tokens, out, i = d.split(), [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("M", "L", "Q", "C", "Z"):
            out.append(t)
            i += 1
        elif t == "A":
            rx, ry, rot, large, sweep, x, y = tokens[i + 1:i + 8]
            out += ["A", f(float(rx) * scale), f(float(ry) * scale), rot, large, sweep,
                    f(origin[0] + float(x) * scale), f(origin[1] + float(y) * scale)]
            i += 8
        else:
            out += [f(origin[0] + float(t) * scale), f(origin[1] + float(tokens[i + 1]) * scale)]
            i += 2
    return " ".join(out)


HAND = ("M 0 9 L 0 1.3 A 1.3 1.3 0 0 1 2.6 1.3 L 2.6 6.2 A 1.2 1.2 0 0 1 5 6.2 L 5 7 A 1.2 1.2 0 0 1 7.4 7 "
        "L 7.4 7.8 A 1.2 1.2 0 0 1 9.8 7.8 L 9.8 12.5 Q 9.8 16.5 6 16.5 L 4 16.5 Q 1.6 16.5 0.4 14 "
        "L -2.6 9.6 A 1.3 1.3 0 0 1 -0.4 8.2 Z")


def hand(tip, scale=1.0):
    """Pointing hand (index finger up) with the finger tip at `tip`."""
    return path(transform_path(HAND, (tip[0] - 1.3 * scale, tip[1]), scale), PAPER, INK, 1.3)


def database(x, y, w, h, top_fill=GREY):
    """Cylinder with three rings: red, blue, green (top to bottom)."""
    ry = w * 0.2
    x1 = x + w
    top = y + ry
    band = (h - 2 * ry) / 3
    parts = []
    for i, col in enumerate((RED, BLUE, GREEN)):
        ya, yb = top + i * band, top + (i + 1) * band
        d = (f"M {f(x)} {f(ya)} L {f(x)} {f(yb)} A {f(w / 2)} {f(ry)} 0 0 0 {f(x1)} {f(yb)} "
             f"L {f(x1)} {f(ya)} A {f(w / 2)} {f(ry)} 0 0 1 {f(x)} {f(ya)} Z")
        parts.append(path(d, col, INK, 1.2))
    parts.append(ellipse(x + w / 2, top, w / 2, ry, top_fill, INK, 1.2))
    return "\n".join(parts)


def pencil(tip, angle=-45, length=19, width=4.6):
    """Pencil with its tip at `tip`, body along `angle` (degrees, screen; -45 = up right)."""
    h = width / 2
    cone = place([(0, 0), (4.4, -h), (4.4, h)], tip, angle)
    lead = place([(0, 0), (1.6, -h * 0.36), (1.6, h * 0.36)], tip, angle)
    body = place([(4.4, -h), (length - 3, -h), (length - 3, h), (4.4, h)], tip, angle)
    eraser = place([(length - 3, -h), (length, -h), (length, h), (length - 3, h)], tip, angle)
    return "\n".join([polygon(body, SUN, INK, 1.3), polygon(eraser, "#F48FB1", INK, 1.3),
                      polygon(cone, "#FFE0B2", INK, 1.3), polygon(lead, BLACK, BLACK, 0.6)])


def bucket(fill_color=BLUE, mono=None):
    """Paint bucket tipped over towards the bottom right, pouring a drop (mono: one colour, e.g. currentColor)."""
    origin, angle = (8.6, 8.6), 135
    body = place([(-5.2, -4.2), (5.2, -4.2), (4, 5.2), (-4, 5.2)], origin, angle)
    lip = place([(-5.2, -4.2), (5.2, -4.2)], origin, angle)
    handle = place([(-5.2, -4.2), (0, -9.8), (5.2, -4.2)], origin, angle)
    ink = mono or INK
    paint = mono or fill_color
    handle_path = path(f"M {f(handle[0][0])} {f(handle[0][1])} Q {f(handle[1][0])} {f(handle[1][1])} "
                       f"{f(handle[2][0])} {f(handle[2][1])}", "none", ink, 1.4)
    body_fill = "none" if mono else GREY
    return "\n".join([handle_path, polygon(body, body_fill, ink, 1.6), line(lip, paint, 2.6),
                      drop(18.6, 18.2, 3.0, paint if not mono else "none", ink, 1.4)])


def scissors(pivot, angle=180, scale=1.0):
    """Scissors with the blades pointing along `angle` from `pivot`."""
    blades = [polygon(place([(-1, -0.4), (7, -2.6), (7.4, -1.6), (0, 1)], pivot, angle, scale), "#B0BEC5", INK, 1.1),
              polygon(place([(-1, 0.4), (7, 2.6), (7.4, 1.6), (0, -1)], pivot, angle, scale), "#B0BEC5", INK, 1.1)]
    h1, h2 = place([(-3.6, -2.6), (-3.6, 2.6)], pivot, angle, scale)
    arms = [line([pivot, h1], RED, 1.6), line([pivot, h2], RED, 1.6)]
    rings = [circle(h1[0], h1[1], 1.9 * scale, PAPER, RED, 1.5), circle(h2[0], h2[1], 1.9 * scale, PAPER, RED, 1.5)]
    return "\n".join(arms + rings + blades + [circle(pivot[0], pivot[1], 0.7, INK, "none", 0)])


def wand(tip, end):
    """Magic wand: black stick with a white tip at `tip`."""
    dx, dy = end[0] - tip[0], end[1] - tip[1]
    n = math.hypot(dx, dy)
    mid = (tip[0] + dx / n * 3, tip[1] + dy / n * 3)
    return "\n".join([line([tip, end], INK, 3.4), line([mid, end], BLACK, 2.2), line([tip, mid], PAPER, 2.2)])


def blob(cx, cy, rx, ry, wobble, phase=0.0, n=9):
    """Irregular closed curve (relief line): Catmull-Rom through wobbly points."""
    points = []
    for i in range(n):
        t = 2 * math.pi * i / n
        k = 1 + wobble * math.sin(3 * t + phase) + wobble * 0.6 * math.cos(2 * t - phase)
        points.append((cx + rx * k * math.cos(t), cy + ry * k * math.sin(t)))
    d = f"M {f(points[0][0])} {f(points[0][1])}"
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C {f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(p2[0])} {f(p2[1])}"
    return d + " Z"


def contour_lines():
    return "\n".join([path(blob(12, 12.3, 9.6, 8.4, 0.09, 0.3), "none", TOPO, 1.5),
                      path(blob(12.8, 12.6, 6.2, 5.2, 0.12, 1.2), "none", TOPO, 1.5),
                      path(blob(13.4, 12.8, 2.8, 2.2, 0.1, 2.0), "none", TOPO, 1.5)])


def hatch_lines(x, y, s, step=3.2, color=INK, width=1.6):
    """Diagonal hatch lines (/) filling the square x, y, s."""
    parts = []
    c = step
    while c < 2 * s:
        a = (x + max(0, c - s), y + min(c, s))   # along the left / bottom edge
        b = (x + min(c, s), y + max(0, c - s))   # along the top / right edge
        parts.append(line([a, b], color, width))
        c += step
    return "\n".join(parts)


def dashed_rect(x, y, w, h, fill=MASK_FILL):
    return rect(x, y, w, h, fill, MASK, 1.6, 0.8, DASH)


def floppy(x, y, s, body=BLUE):
    k = s / 16
    shape = [(x, y), (x + 12.5 * k, y), (x + 16 * k, y + 3.5 * k), (x + 16 * k, y + 16 * k), (x, y + 16 * k)]
    return "\n".join([polygon(shape, body, INK, 1.3),
                      rect(x + 3 * k, y, 8 * k, 5 * k, GREY, INK, 1.0, 0.3),
                      rect(x + 2.6 * k, y + 8.8 * k, 10.8 * k, 7.2 * k, PAPER, INK, 1.0, 0.4)])


def page(x, y, w, h, fold=4.2, fill=PAPER):
    return "\n".join([polygon([(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)], fill, INK),
                      polyline_fold(x + w - fold, y, fold)])


def polyline_fold(x, y, fold):
    return line([(x, y), (x, y + fold), (x + fold, y + fold)], INK, 1.3)


def letter_t(x, y, w, h, color=INK, width=2.6):
    return line([(x, y), (x + w, y)], color, width) + "\n" + line([(x + w / 2, y), (x + w / 2, y + h)], color, width)


def shapes_trio(x, y, s, color=INK, width=1.4):
    """Overlapping square, triangle and circle outlines in an s x s box at (x, y)."""
    k = s / 12
    return "\n".join([rect(x, y + 4.5 * k, 6.5 * k, 6.5 * k, "none", color, width, 0.4),
                      circle(x + 8 * k, y + 8 * k, 3.6 * k, "none", color, width),
                      polygon([(x + 6 * k, y), (x + 10.5 * k, y + 7 * k), (x + 1.5 * k, y + 7 * k)], "none", color,
                              width)])


# --- RGB arrows (split / combine) ---
STRIPES = (RED, BLUE, GREEN)  # top to bottom (as asked: red, blue, green)


def striped_bar(x0, x1, y_top, height):
    band = height / 3
    return "\n".join(polygon([(x0, y_top + i * band), (x1, y_top + i * band), (x1, y_top + (i + 1) * band),
                              (x0, y_top + (i + 1) * band)], c) for i, c in enumerate(STRIPES))


def striped_head(base_x, tip_x, cy, half):
    """Arrow head (tip to the right) cut into three horizontal colour bands."""
    def x_at(y):  # right edge of the triangle at height y
        return base_x + (tip_x - base_x) * (1 - abs(y - cy) / half)
    y0, y3 = cy - half, cy + half
    y1, y2 = cy - half / 3, cy + half / 3
    top = polygon([(base_x, y0), (x_at(y1), y1), (base_x, y1)], STRIPES[0])
    mid = polygon([(base_x, y1), (x_at(y1), y1), (tip_x, cy), (x_at(y2), y2), (base_x, y2)], STRIPES[1])
    bottom = polygon([(base_x, y2), (x_at(y2), y2), (base_x, y3)], STRIPES[2])
    return "\n".join([top, mid, bottom])


def combine_icon(result_color=None):
    """Three channel lines (red / blue / green) join into one arrow (RGB striped, or one colour)."""
    parts = [line([(2.5, 5), (8, 5), (12.5, 10.8)], RED), line([(2.5, 12), (12.5, 12)], BLUE),
             line([(2.5, 19), (8, 19), (12.5, 13.2)], GREEN)]
    if result_color is None:
        parts += [striped_bar(12, 17.2, 9.3, 5.4), striped_head(17, 22, 12, 5)]
    else:
        parts += [polygon([(12, 9.3), (17.2, 9.3), (17.2, 14.7), (12, 14.7)], result_color),
                  polygon([(17, 7), (22, 12), (17, 17)], result_color)]
    return svg(*parts)


# --- icons ---
def two_x(cx=12, cy=12.2):
    """The characters "2x", drawn as strokes."""
    two = path(f"M {f(cx - 3.6)} {f(cy - 1.9)} C {f(cx - 3.6)} {f(cy - 4.2)} {f(cx - 0.3)} {f(cy - 4.2)} "
               f"{f(cx - 0.3)} {f(cy - 1.9)} C {f(cx - 0.3)} {f(cy - 0.4)} {f(cx - 3.6)} {f(cy + 1.2)} "
               f"{f(cx - 3.6)} {f(cy + 3)} L {f(cx - 0.1)} {f(cy + 3)}", "none", INK, 1.6)
    x = line([(cx + 1.1, cy - 0.6), (cx + 4.1, cy + 3)], INK, 1.6) + "\n" + \
        line([(cx + 4.1, cy - 0.6), (cx + 1.1, cy + 3)], INK, 1.6)
    return two + "\n" + x


def upscale_icon(ai=False):
    parts = [two_x(), arrow((7, 7), (2.5, 2.5)), arrow((7, 17), (2.5, 21.5)), arrow((17, 17), (21.5, 21.5))]
    if ai:
        parts += [arrow((16.2, 7.8), (19, 5)), sparkle(20.6, 3.4, 3.0), sparkle(16.2, 2.6, 1.7)]
    else:
        parts.append(arrow((17, 7), (21.5, 2.5)))
    return svg(*parts)


def bright_transparent():
    cx, cy, r = 12, 10, 4.6
    rays = []
    for deg in (90, 135, 180, 225, 270):
        t = math.radians(deg)
        a = (cx + (r + 1.6) * math.cos(t), cy + (r + 1.6) * math.sin(t))
        b = (cx + (r + 3.6) * math.cos(t), cy + (r + 3.6) * math.sin(t))
        rays.append(line([a, b], SUN, 1.8))
    ghost_rays = []
    for deg in (-45, 0, 45):
        t = math.radians(deg)
        a = (cx + (r + 1.6) * math.cos(t), cy + (r + 1.6) * math.sin(t))
        b = (cx + (r + 3.6) * math.cos(t), cy + (r + 3.6) * math.sin(t))
        ghost_rays.append(line([a, b], INK, 1.2, "1.2 1.2"))
    left = path(f"M {f(cx)} {f(cy - r)} A {f(r)} {f(r)} 0 0 0 {f(cx)} {f(cy + r)} Z", SUN, SUN, 1.0)
    right = path(f"M {f(cx)} {f(cy - r)} A {f(r)} {f(r)} 0 0 1 {f(cx)} {f(cy + r)}", "none", INK, 1.3, "1.6 1.4")
    return svg(*rays, *ghost_rays, left, right, arrow((4, 20.5), (20.5, 20.5), BLACK, 1.8, 3.2))


def size_reset():
    return svg(rect(7.2, 8, 7, 5, BLUE, INK, 1.3, 0.5),
               double_arrow((7.2, 15.6), (14.2, 15.6), INK, 1.0, 2.0),
               double_arrow((16.8, 8), (16.8, 13), INK, 1.0, 2.0),
               reset_arrow())


def mask_polygon_points():
    return [(4, 9), (11.5, 3.5), (20, 7.5), (17, 19.5), (7, 18)]


def mask_polygon(points=None, dots=True, width=1.6):
    points = points or mask_polygon_points()
    parts = [polygon(points, MASK_FILL, MASK, width, DASH)]
    if dots:
        parts += [circle(x, y, 1.5, PAPER, MASK, 1.2) for x, y in points]
    return "\n".join(parts)


def mask_edit():
    d = "M 13 4 L 4 4 L 4 20 L 20 20 L 20 11"
    return svg(path(d + " L 20 4 Z", MASK_FILL, "none", 0), path(d, "none", MASK, 1.6, DASH),
               pencil((13.2, 10.8), -45, 13.5, 4.0))


def mask_move():
    return svg(dashed_rect(8, 8, 8, 8),
               arrow((12, 6.6), (12, 1.6)), arrow((12, 17.4), (12, 22.4)),
               arrow((6.6, 12), (1.6, 12)), arrow((17.4, 12), (22.4, 12)))


def delete_all():
    return svg(rect(2.5, 3, 9, 8, MASK_FILL, MASK, 1.4, 0.6, DASH),
               ellipse(14.5, 7.5, 6.5, 5, MASK_FILL, MASK, 1.4, DASH),
               mask_polygon([(3, 15), (8.5, 11.5), (13.5, 14.5), (11.5, 21), (4.5, 20.5)], dots=False, width=1.4),
               CROSS)


def mask_save():
    return svg(dashed_rect(1.5, 6.5, 10, 10, PAPER), floppy(3.8, 8.8, 5.4),
               arrow((12.6, 11.5), (16, 11.5), BLACK, 1.6, 2.6),
               picture(16.5, 8, 6.5, 7))


def image_restore():
    return svg(picture(6.5, 8, 11, 8.5), sparkle(17.2, 7.4, 2.6), sparkle(6.6, 16.6, 1.8), reset_arrow())


def recenter():
    return svg(circle(12, 12, 2.2, RED, "none", 0),
               arrow((12, 1.8), (12, 8.2)), arrow((12, 22.2), (12, 15.8)),
               arrow((1.8, 12), (8.2, 12)), arrow((22.2, 12), (15.8, 12)))


def grid(crossed=False):
    lines = [rect(2.5, 2.5, 14, 14, PAPER, INK, 1.4, 0.8)]
    for v in (7.17, 11.83):
        lines.append(line([(v, 2.5), (v, 16.5)], INK, 1.1))
        lines.append(line([(2.5, v), (16.5, v)], INK, 1.1))
    return svg(*lines, eye(16.8, 18, 10.4, crossed))


def zoom_reset():
    return svg(line([(13.8, 13.8), (16.6, 16.6)], INK, 2.8), circle(10.6, 10.6, 4.2, SKY, INK, 1.6), reset_arrow())


def machine():
    """Laser head: housing, objective, red beam, spark on the work piece."""
    return svg(rect(6.5, 1.5, 11, 6, GREY, INK, 1.4, 1.0),
               polygon([(7.5, 7.5), (16.5, 7.5), (14, 12.5), (10, 12.5)], "#90A4AE", INK, 1.4),
               ellipse(12, 12.6, 2, 0.8, BLUE, INK, 1.0),
               line([(12, 13.8), (12, 19.5)], RED, 2.0),
               sparkle(12, 19.6, 2.6, RED),
               line([(3, 22), (21, 22)], INK, 1.6))


def robot():
    return svg(line([(12, 6), (12, 3)], INK, 1.5), circle(12, 2.6, 1.5, RED, INK, 1.1),
               rect(1.8, 10, 2.4, 5, GREY, INK, 1.2, 0.6), rect(19.8, 10, 2.4, 5, GREY, INK, 1.2, 0.6),
               rect(4, 6, 16, 14, GREY, INK, 1.6, 3),
               circle(9, 11.5, 2, BLUE, INK, 1.1), circle(15, 11.5, 2, BLUE, INK, 1.1),
               line([(9, 16.2), (15, 16.2)], INK, 1.6))


def group_text():
    return svg(line([(2.5, 21.5), (21.5, 2.5)], GREY, 1.0),
               letter_t(2.5, 3, 10.5, 11, INK, 2.8),
               shapes_trio(11.5, 10.5, 11.5, INK, 1.4))


def flask():
    glass = [(9.5, 2.5), (14.5, 2.5), (14.5, 9), (20.5, 20), (19.6, 21.5), (4.4, 21.5), (3.5, 20), (9.5, 9)]
    liquid = [(6.6, 15.5), (17.4, 15.5), (20.5, 20), (19.6, 21.5), (4.4, 21.5), (3.5, 20)]
    return svg(polygon(glass, PAPER, "none"), polygon(liquid, GREEN, "none"), polygon(glass, "none", INK, 1.6),
               line([(8.5, 2.5), (15.5, 2.5)], INK, 1.8), circle(11, 18.5, 1.0, PAPER, "none", 0),
               circle(14, 17.5, 0.7, PAPER, "none", 0))


def stamp(dx=0.0):
    return "\n".join([circle(12 + dx, 4.6, 2.8, WOOD, INK, 1.4), rect(10.4 + dx, 7, 3.2, 4.6, WOOD, INK, 1.3, 0.3),
                      rect(4.5 + dx, 11.5, 15, 4.2, WOOD, INK, 1.4, 1.0),
                      rect(5.5 + dx, 15.7, 13, 2.2, RED, INK, 1.2, 0.3),
                      line([(4.5 + dx, 21), (19.5 + dx, 21)], RED, 2.0)])


def imprint_colors():
    """Stamp with a small colourful drop at the bottom right."""
    return svg(stamp(-2.5), path(drop_path(19, 18.6, 3.4), PAPER, PAPER, 3.0), rgb_drop(19, 18.6, 3.4))


def imprint_overlays():
    """Stamp with a "T" in a square at the bottom right."""
    return svg(stamp(-2.5), rect(14, 13.5, 9, 9, PAPER, PAPER, 2.6, 1.2), rect(14, 13.5, 9, 9, PAPER, INK, 1.4, 1.2),
               letter_t(16, 16, 5, 4.6, INK, 1.7))


def rotate_icon():
    """Square at the bottom left, a quarter-circle arrow around its top right corner, "90°" above it."""
    nine = circle(4.4, 4, 1.5, "none", INK, 1.3) + "\n" + path("M 5.9 4 L 5.9 6 Q 5.9 7.6 4.2 7.6", "none", INK, 1.3)
    zero = ellipse(9.4, 4.9, 1.5, 2.25, "none", INK, 1.3)
    degree = circle(12.3, 3, 0.85, "none", INK, 1.0)
    return svg(rect(2.5, 10.5, 11, 11, SKY), nine, zero, degree,
               path("M 14.2 5.5 Q 19.6 5.5 19.6 11.2", "none", BLUE, LINE), head((19.6, 14.4), (0, 1), BLUE))


def spin_arrow(up):
    """Slim chevron for the spin box buttons (8 x 5)."""
    points = "1,4 4,1 7,4" if up else "1,1 4,4 7,1"
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5" viewBox="0 0 8 5">\n'
            f'<polyline points="{points}" fill="none" stroke="#7A0020" stroke-width="1.5" '
            'stroke-linecap="round" stroke-linejoin="round"/>\n</svg>\n')


def palette():
    d = ("M 12 2.5 C 6 2.5 2 6.8 2 12 C 2 17.3 6.2 21.5 11.5 21.5 C 13.6 21.5 14 20 13 18.6 "
         "C 12 17.2 12.8 15.5 14.6 15.5 L 17 15.5 C 19.8 15.5 22 13.5 22 10.5 C 22 6 17.5 2.5 12 2.5 Z")
    return svg(path(d, "#FFE0B2", INK, 1.5),
               circle(7, 9.5, 1.7, RED, "none", 0), circle(11, 6.6, 1.7, SUN, "none", 0),
               circle(16, 7.6, 1.7, GREEN, "none", 0), circle(6.8, 14.6, 1.7, BLUE, "none", 0))


def pipette(tip=(3, 21), angle=-45):
    h = 1.5
    tube = place([(0, 0), (2.2, -h * 0.6), (10, -h), (10, h), (2.2, h * 0.6)], tip, angle)
    liquid = place([(0.6, 0), (2.4, -h * 0.4), (6, -h * 0.65), (6, h * 0.65), (2.4, h * 0.4)], tip, angle)
    collar = place([(10, -2.6), (12, -2.6), (12, 2.6), (10, 2.6)], tip, angle)
    bulb_c = place([(16, 0)], tip, angle)[0]
    neck = place([(12, -1.6), (14, -1.6), (14, 1.6), (12, 1.6)], tip, angle)
    return "\n".join([polygon(tube, PAPER, INK, 1.2), polygon(liquid, BLUE, "none", 0),
                      polygon(neck, "#546E7A", INK, 1.1), circle(bulb_c[0], bulb_c[1], 3.4, "#546E7A", INK, 1.2),
                      polygon(collar, INK, INK, 1.0)])


def replace_color():
    return svg(drop(6, 8.6, 3.4, RED), path("M 11 6.5 L 17.6 6.5 L 17.6 10.6", "none", BLACK, 1.8),
               head((17.6, 13.4), (0, 1), BLACK, 3.2), drop(17.6, 19.4, 2.9, BLUE))


def recolor_db():
    return svg(database(1.5, 5, 8, 14), arrow((10.6, 12), (14.4, 12), BLACK, 1.6, 2.8), picture(15, 7.5, 8, 9))


def pick_db():
    return svg(database(2, 2, 12, 15), hand((14, 11), 0.78))


def clean_up():
    return svg(rgb_drop(8.5, 16, 5), wand((13, 10), (21.5, 2)), sparkle(11.4, 5, 2.2), sparkle(17.6, 11.8, 1.8),
               sparkle(15.6, 4, 1.3))


def filter_icon():
    funnel = [(2.5, 3.5), (21.5, 3.5), (14, 11.5), (14, 14), (10, 14), (10, 11.5)]
    return svg(polygon(funnel, SKY, INK, 1.6), line([(8.6, 16.2), (12, 18.6), (15.4, 16.2)], BLUE, 1.9),
               line([(8.6, 19.6), (12, 22), (15.4, 19.6)], BLUE, 1.9))


def font_icon():
    return svg(path("M 4 6 L 4 3.5 L 20 3.5 L 20 6", "none", INK, 2.2), line([(12, 3.5), (12, 20.5)], INK, 2.6),
               line([(8.5, 20.5), (15.5, 20.5)], INK, 2.2))


def font_size():
    return svg(path("M 2.5 6.5 L 2.5 3.5 L 14 3.5 L 14 6.5", "none", INK, 2.0), line([(8.25, 3.5), (8.25, 20.5)], INK, 2.4),
               line([(5.5, 20.5), (11, 20.5)], INK, 2.0),
               path("M 14.5 13 L 14.5 11.5 L 21.5 11.5 L 21.5 13", "none", INK, 1.6),
               line([(18, 11.5), (18, 20.5)], INK, 1.8), line([(16.5, 20.5), (19.5, 20.5)], INK, 1.6))


def add_text():
    return svg(rect(2.5, 2.5, 15.5, 15.5, "none", INK, 1.3, 0.8, "2 1.8"),
               line([(5.6, 15), (10.25, 5), (14.9, 15)], INK, 2.4), line([(7.3, 11.4), (13.2, 11.4)], INK, 2.0),
               PLUS)


def add_geometry():
    return svg(shapes_trio(2, 2, 15, INK, 1.6), PLUS)


def outline_color():
    return svg(rect(3, 3, 18, 18, "none", CURRENT, 2.2, 2.5), drop(12, 13.6, 3.6, CURRENT, CURRENT, 1.0))


def outline_width():
    return svg(*[line([(3, y), (21, y)], INK, w) for y, w in ((4, 0.9), (8.6, 1.8), (13.8, 2.9), (19.8, 4.2))])


def hatch_tile():
    return svg(rect(2.5, 2.5, 19, 19, PAPER, INK, 1.5, 2), hatch_lines(4.2, 4.2, 15.6, 4.4, INK, 1.5))


def hatch_square():
    return hatch_lines(2.5, 2.5, 19, 4.6, BLACK, 1.8)


def export_icon():
    return svg(page(3, 2.5, 13, 19), line([(6, 9), (11, 9)], GREY, 1.4), line([(6, 12.5), (10, 12.5)], GREY, 1.4),
               line([(6, 16), (11, 16)], GREY, 1.4), arrow((10.5, 14.5), (22, 14.5), BLUE, 2.4, 4.2))


def folder_open():
    return svg(path("M 2.5 19.5 L 2.5 5 L 9 5 L 11 7 L 18.5 7 L 18.5 10", "#FFB300", INK, 1.5),
               polygon([(2.5, 19.5), (6, 10), (22, 10), (18.5, 19.5)], "#FFCA28", INK, 1.5))


def new_page():
    return svg(page(4, 2.5, 14, 19), sparkle(18, 17, 4.2), sparkle(13.2, 12, 1.8))


def color_profile():
    return svg(database(2, 2, 13, 17), drop(18.5, 17.8, 3.6, SUN))


def mouse_device():
    """Computer mouse: no tool selected."""
    return svg(rect(6, 2.5, 12, 19, GREY, INK, 1.6, 6), line([(12, 2.8), (12, 9)], INK, 1.4),
               line([(6.2, 9), (17.8, 9)], INK, 1.4), rect(11, 4.6, 2, 3.2, BLUE, "none", 0, 1))


# --- canvas cursors (P11): 32 x 32, the hot spot is the centre of pixel CURSOR_HOT[name]; paint in currentColor
def cursor_svg(*parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">\n'
            + "\n".join(p for p in parts if p) + "\n</svg>\n")


CURSOR_TIP = (1.5, 30.5)  # the tip of draw / fill / pick: centre of pixel (1, 30)


def cursor_fill():
    """Tipped bucket, the poured paint narrows to a sharp point at the hot spot."""
    origin, angle = (21.5, 10.5), 220
    body = place([(-6.5, -4.5), (6.5, -4.5), (5, 5.5), (-5, 5.5)], origin, angle)
    lip = place([(-6.5, -4.5), (6.5, -4.5)], origin, angle)
    handle = place([(-6.5, -4.5), (0, 21), (6.5, -4.5)], origin, angle)  # the bail hangs over the bottom
    tip_x, tip_y = CURSOR_TIP
    stream = [(lip[0][0] - 0.5, lip[0][1] + 0.5), (lip[1][0] + 0.5, lip[1][1] - 0.5), (tip_x, tip_y)]
    return cursor_svg(
        polygon(body, GREY, INK, 1.6),
        path(f"M {f(handle[0][0])} {f(handle[0][1])} Q {f(handle[1][0])} {f(handle[1][1])} "
             f"{f(handle[2][0])} {f(handle[2][1])}", "none", INK, 1.6),
        polygon(stream, CURRENT, INK, 1.2),
        line(lip, CURRENT, 2.6))


def cursor_replace():
    """Plain triangular pointer (no shaft) in the replace colour, tip at the hot spot (pixel 1, 1)."""
    return cursor_svg(polygon([(1.5, 1.5), (1.5, 19), (13.5, 12.5)], CURRENT, INK, 1.4))


ICONS = {
    # --- Images ---
    "image-add": lambda: svg(picture(2, 3.5, 15, 12.5), PLUS),
    "image-remove": lambda: svg(picture(2, 3.5, 15, 12.5), MINUS),
    "set-original": lambda: svg(picture(6.5, 7.5, 11, 9), arc_arrow(12, 12, 9.6, 200, 160)),
    "split-channels": lambda: svg(
        striped_bar(2, 9.5, 9.3, 5.4),
        line([(9, 10), (13, 5), (18, 5)], RED), head((22, 5), (1, 0), RED),
        line([(9, 12), (18, 12)], BLUE), head((22, 12), (1, 0), BLUE),
        line([(9, 14), (13, 19), (18, 19)], GREEN), head((22, 19), (1, 0), GREEN)),
    "combine": lambda: combine_icon(),
    "combine-mono": lambda: combine_icon(BLACK),
    "rotate": rotate_icon,
    # mirror top / bottom: original filled above, mirror image outlined below a horizontal axis
    "mirror-v": lambda: svg(polygon([(5, 9.2), (19, 9.2), (19, 3)], BLUE, BLUE),
                            polygon([(5, 14.8), (19, 14.8), (19, 21)], "none", BLUE),
                            line([(2, 12), (22, 12)], INK, 1.4, "2 2")),
    # mirror left / right: standing triangles on both sides of a vertical axis
    "mirror-h": lambda: svg(polygon([(9.2, 5), (9.2, 19), (3, 19)], BLUE, BLUE),
                            polygon([(14.8, 5), (14.8, 19), (21, 19)], "none", BLUE),
                            line([(12, 2), (12, 22)], INK, 1.4, "2 2")),
    "crop": lambda: svg(line([(6.5, 2), (6.5, 17.5), (22, 17.5)], BLACK, 2.6),
                        line([(2, 6.5), (17.5, 6.5), (17.5, 22)], BLACK, 2.6)),
    "cut-mask": lambda: svg(dashed_rect(2.5, 5, 13.5, 14), scissors((18.6, 12), 180, 1.0)),
    "upscale-ai": lambda: upscale_icon(ai=True),
    "upscale": lambda: upscale_icon(),
    "bright-transparent": bright_transparent,
    # --- Size & Center ---
    "width": lambda: svg(rect(2.5, 4, 19, 10.5, SKY, INK, 1.6, 1), double_arrow((2.5, 19.2), (21.5, 19.2))),
    "height": lambda: svg(rect(4, 2.5, 10.5, 19, SKY, INK, 1.6, 1), double_arrow((19.2, 2.5), (19.2, 21.5))),
    "size-reset": size_reset,
    "center-show": lambda: svg(crosshair(8.5, 8.5), eye(16.6, 18, 10.4)),
    "center-hide": lambda: svg(crosshair(8.5, 8.5), eye(16.6, 18, 10.4, crossed=True)),
    "center-set": lambda: svg(crosshair(10, 10, 5), cursor((10, 10), 0.95)),
    "center-reset": lambda: svg(crosshair(12, 12, 3.4), reset_arrow()),
    # --- Adjust ---
    "invert": lambda: svg(half_drop(12, 14.2, 6.6)),
    "colors-reset": lambda: svg(rgb_drop(12, 14, 4.4), reset_arrow()),
    "filter": filter_icon,
    # --- Color ---
    "more-colors": palette,
    "pick": lambda: svg(pipette()),
    "pick-db": pick_db,
    "draw": lambda: svg(pencil((3, 21), -45, 23)),
    "fill": lambda: svg(bucket()),
    "replace": replace_color,
    "recolor-db": recolor_db,
    "clean-up": clean_up,
    "imprint-colors": imprint_colors,
    "imprint-overlays": imprint_overlays,
    "image-restore": image_restore,
    "contours": lambda: svg(contour_lines()),
    "contours-hide": lambda: svg(contour_lines(), slash((3, 3), (21, 21))),
    # --- Masks ---
    "mask-ellipse": lambda: svg(ellipse(12, 12, 9.5, 8, MASK_FILL, MASK, 1.6, DASH)),
    "mask-rect": lambda: svg(dashed_rect(3, 4, 18, 16)),
    "mask-polygon": lambda: svg(mask_polygon()),
    "mask-edit": mask_edit,
    "mask-move": mask_move,
    "mask-unselect": lambda: svg(dashed_rect(3, 4, 18, 16), slash((3.5, 3.5), (20.5, 20.5))),
    "delete": lambda: svg(dashed_rect(2.5, 3, 16, 13), CROSS),
    "delete-all": delete_all,
    "mask-save": mask_save,
    # --- Text ---
    "add-text": add_text,
    "add-geometry": add_geometry,
    "text-fill-color": lambda: svg(bucket(mono=CURRENT)),
    "text-outline-color": outline_color,
    "outline-width": outline_width,
    "font": font_icon,
    "font-size": font_size,
    # --- Hatching / Tests / Export ---
    "hatch": hatch_tile,
    "test-structure": flask,
    "hatch-add": lambda: svg(hatch_lines(2, 2, 16, 4.4, BLACK, 1.6), PLUS),
    "hatch-remove": lambda: svg(hatch_lines(2, 2, 16, 4.4, BLACK, 1.6), CROSS),
    "export": export_icon,
    # --- group strip ---
    "group-image": lambda: svg(picture(2, 3.5, 20, 17)),
    "group-text": group_text,
    "group-hatching": lambda: svg(hatch_square()),
    "group-automation": robot,
    # --- toolbar ---
    "open": folder_open,
    "save": lambda: svg(floppy(3, 3, 18)),
    "new": new_page,
    "zoom-reset": zoom_reset,
    "recenter": recenter,
    "grid": lambda: grid(),
    "grid-hide": lambda: grid(crossed=True),
    "color-profile": color_profile,
    "machine": machine,
    # --- spin box arrows (stylesheet) ---
    "spin-up": lambda: spin_arrow(True),
    "spin-down": lambda: spin_arrow(False),
    # --- tools (P11) ---
    "tool-none": mouse_device,
    "cursor-draw": lambda: cursor_svg(pencil(CURSOR_TIP, -45, 30, 6.4)),
    "cursor-fill": cursor_fill,
    "cursor-replace": cursor_replace,
    "cursor-pick": lambda: cursor_svg(pipette(CURSOR_TIP, -45)),
}


def update_sources(names):
    sources = ICON_DIR / "SOURCES.md"
    text = sources.read_text(encoding="utf-8")
    for name in names:
        row = f"| {name} | drawn for BildHatcher (tools/make_icons.py) | BildHatcher |"
        text, n = re.subn(rf"^\| {re.escape(name)} \|.*$", row, text, flags=re.M)
        if n == 0:
            text = text.rstrip("\n") + "\n" + row + "\n"
    sources.write_text(text, encoding="utf-8")


def main(names):
    names = names or list(ICONS)
    for name in names:
        (ICON_DIR / f"{name}.svg").write_text(ICONS[name](), encoding="utf-8")
    update_sources(names)
    print(f"{len(names)} icons written to {ICON_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
