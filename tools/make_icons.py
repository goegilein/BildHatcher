"""BildHatcher's own pictograms: writes GUI_Files/icons/<meaning>.svg in one consistent style.

    python tools/make_icons.py            # write all icons defined here
    python tools/make_icons.py rotate     # only some

Style: 24 x 24 grid, round line ends, one dark outline colour (INK), flat fills, colour only where it means
something (red / green / blue channels, red = add / remove, blue = movement / transformation).
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
PAPER = "#FFFFFF"   # halo behind badges
SKY = "#E3F2FD"     # picture background
HILL = "#81C784"    # picture hills
SUN = "#FFB300"     # picture sun
RED, GREEN, BLUE = "#E53935", "#43A047", "#1E88E5"
BLACK = "#263238"
STROKE = 1.6        # outline width
LINE = 2.0          # arrows / symbols


def svg(*parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">\n'
            + "\n".join(parts) + "\n</svg>\n")


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pts(points):
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


def line(points, color=INK, width=LINE, dash=None):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{pts(points)}" fill="none" stroke="{color}" stroke-width="{f(width)}" '
            f'stroke-linecap="round" stroke-linejoin="round"{extra}/>')


def polygon(points, fill, stroke="none", width=STROKE):
    return (f'<polygon points="{pts(points)}" fill="{fill}" stroke="{stroke}" stroke-width="{f(width)}" '
            f'stroke-linejoin="round"/>')


def rect(x, y, w, h, fill, stroke=INK, width=STROKE, r=1.5):
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{f(width)}"/>')


def head(tip, direction, color, size=3.4):
    """Filled arrow head with its tip at `tip`, pointing along `direction` (dx, dy)."""
    dx, dy = direction
    n = math.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    bx, by = tip[0] - dx * size, tip[1] - dy * size
    px, py = -dy * size * 0.62, dx * size * 0.62
    return polygon([tip, (bx + px, by + py), (bx - px, by - py)], color, color, 0.8)


def arc_arrow(cx, cy, r, start_deg, end_deg, color=BLUE, width=LINE):
    """Clockwise arc (screen coordinates, 0° = right, 90° = down) with an arrow head at the end."""
    a0, a1 = math.radians(start_deg), math.radians(end_deg)
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    sweep = (end_deg - start_deg) % 360
    back = math.radians(end_deg - 14)  # the head covers the last bit of the arc
    pe = (cx + r * math.cos(back), cy + r * math.sin(back))
    large = 1 if sweep - 14 > 180 else 0
    path = (f'<path d="M {f(p0[0])} {f(p0[1])} A {f(r)} {f(r)} 0 {large} 1 {f(pe[0])} {f(pe[1])}" fill="none" '
            f'stroke="{color}" stroke-width="{f(width)}" stroke-linecap="round"/>')
    tip = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    tangent = (-math.sin(a1), math.cos(a1))  # clockwise direction
    return path + "\n" + head(tip, tangent, color)


def picture(x, y, w, h):
    """The picture motif: frame, sky, two hills, sun."""
    def at(u, v):
        return (x + u * w, y + v * h)
    hills = polygon([at(0.08, 0.88), at(0.38, 0.42), at(0.58, 0.68), at(0.72, 0.52), at(0.92, 0.88)], HILL)
    sun = f'<circle cx="{f(x + 0.72 * w)}" cy="{f(y + 0.28 * h)}" r="{f(min(w, h) * 0.11)}" fill="{SUN}"/>'
    return "\n".join([rect(x, y, w, h, SKY), hills, sun])


def badge(*strokes, color=RED):
    """Red symbol (one or more strokes) with a white halo, readable on top of the picture."""
    return "\n".join([line(s, PAPER, 4.6) for s in strokes] + [line(s, color, 2.4) for s in strokes])


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


ICONS = {
    "image-add": lambda: svg(picture(2, 3.5, 15, 12.5), badge([(18.5, 15), (18.5, 22)], [(15, 18.5), (22, 18.5)])),
    "image-remove": lambda: svg(picture(2, 3.5, 15, 12.5), badge([(15, 18.5), (22, 18.5)])),
    "set-original": lambda: svg(picture(6.5, 7.5, 11, 9), arc_arrow(12, 12, 9.6, 200, 160)),
    "split-channels": lambda: svg(
        striped_bar(2, 9.5, 9.3, 5.4),
        line([(9, 10), (13, 5), (18, 5)], RED), head((22, 5), (1, 0), RED),
        line([(9, 12), (18, 12)], BLUE), head((22, 12), (1, 0), BLUE),
        line([(9, 14), (13, 19), (18, 19)], GREEN), head((22, 19), (1, 0), GREEN)),
    "combine": lambda: combine_icon(),
    "combine-mono": lambda: combine_icon(BLACK),
    "rotate": lambda: svg(rect(3, 9, 11, 11, SKY), arc_arrow(14, 9, 6.2, 205, 65)),
    # mirror top / bottom: original filled above, mirror image outlined below a horizontal axis
    "mirror-v": lambda: svg(polygon([(5, 9.2), (19, 9.2), (19, 3)], BLUE, BLUE),
                            polygon([(5, 14.8), (19, 14.8), (19, 21)], "none", BLUE),
                            line([(2, 12), (22, 12)], INK, 1.4, "2 2")),
    # mirror left / right: standing triangles on both sides of a vertical axis
    "mirror-h": lambda: svg(polygon([(9.2, 5), (9.2, 19), (3, 19)], BLUE, BLUE),
                            polygon([(14.8, 5), (14.8, 19), (21, 19)], "none", BLUE),
                            line([(12, 2), (12, 22)], INK, 1.4, "2 2")),
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
