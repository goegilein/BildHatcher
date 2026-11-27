"""Outlines for laser cutting: closed contours from images and a check for contours that are not closed. Pure numpy/OpenCV.

Why contours can be open: cv2.findContours always returns a formally closed point chain, but in the edge modes it traces
the Canny edge *stroke*. Where Canny loses a few pixels (sharp or narrow corners) the stroke is an open line; its
contour runs along the line and back again. The toolpath then burns that line twice and leaves the gap uncut.

shape_mask/shape_contours  outline of the filled shapes themselves -> closed by construction (best for cutting).
bridge_gaps                closes small gaps of a Canny edge image by joining nearby stroke ends.
find_open_contours         flags contours that enclose (almost) no area of their own, with the points where they turn back.
"""
import cv2
import numpy as np

MAX_GAP_PX = 4  # stroke ends closer than this are joined by bridge_gaps
ALPHA_THRESHOLD = 128  # with a transparent background, pixels with at least this alpha belong to a shape
MIN_INTERIOR_FRACTION = 0.05  # a contour whose own interior is smaller than this fraction of its area is "open"
MIN_INTERIOR_PX = 2
MIN_FLAG_LENGTH_PX = 6  # shorter contours (specks of one or two pixels) are not reported as open

_NEIGHBOURS = np.ones((3, 3), np.float32)


def edge_endpoints(edges):
    """(N, 2) int array of (x, y) stroke ends of a thin binary edge image: edge pixels with exactly one 8-neighbour."""
    e = (np.asarray(edges) > 0).astype(np.uint8)
    neighbours = cv2.filter2D(e, cv2.CV_16S, _NEIGHBOURS, borderType=cv2.BORDER_CONSTANT) - e
    ys, xs = np.nonzero((e == 1) & (neighbours == 1))
    return np.column_stack([xs, ys])


def bridge_gaps(edges, max_gap=MAX_GAP_PX):
    """Copy of `edges` where every stroke end is joined by a line to the nearest edge pixel at most `max_gap` px away
    that does not belong to its own stroke piece (pixels reachable from the end along the stroke within a few steps).
    The other side of a gap is often no stroke end itself (the edge just continues there), so ends are not paired.
    Returns (bridged edges, number of bridges)."""
    out = np.asarray(edges).copy()
    on = out > 0
    h, w = on.shape
    value = int(out.max()) or 255
    reach = 2 * max_gap + 2  # steps along the own stroke that are never a bridge target
    r = max_gap + reach
    bridges = 0
    for x, y in edge_endpoints(out):
        y0, y1, x0, x1 = max(0, y - r), min(h, y + r + 1), max(0, x - r), min(w, x + r + 1)
        window = on[y0:y1, x0:x1]
        if np.count_nonzero(window[max(0, y - 1 - y0):y + 2 - y0, max(0, x - 1 - x0):x + 2 - x0]) != 2:
            continue  # no longer an end: an earlier bridge ended here
        own = np.zeros_like(window)
        frontier = [(y - y0, x - x0)]
        own[frontier[0]] = True
        for _ in range(reach):  # breadth-first along the stroke
            nxt = []
            for fy, fx in frontier:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = fy + dy, fx + dx
                        if 0 <= ny < window.shape[0] and 0 <= nx < window.shape[1] and window[ny, nx] and not own[ny, nx]:
                            own[ny, nx] = True
                            nxt.append((ny, nx))
            frontier = nxt
        ty, tx = np.nonzero(window & ~own)
        if not len(ty):
            continue
        d = np.hypot(ty + y0 - y, tx + x0 - x)
        k = int(np.argmin(d))
        if d[k] <= max_gap:
            cv2.line(out, (int(x), int(y)), (int(tx[k] + x0), int(ty[k] + y0)), value, 1)
            on = out > 0
            bridges += 1
    return out, bridges


def shape_mask(rgba, region=None, tolerance=50):
    """bool (H, W) mask of the shapes of an RGBA image.
    Transparent background (any fully transparent border pixel): every pixel with alpha >= ALPHA_THRESHOLD is a shape.
    Opaque image: the background is the most frequent border colour; pixels whose largest channel difference to it
    exceeds `tolerance` are shapes."""
    rgba = np.asarray(rgba)
    alpha = rgba[..., 3]
    border = np.concatenate([rgba[0], rgba[-1], rgba[:, 0], rgba[:, -1]])
    if (border[:, 3] == 0).any():
        mask = alpha >= ALPHA_THRESHOLD
    else:
        colors, counts = np.unique(border[:, :3], axis=0, return_counts=True)
        background = colors[np.argmax(counts)].astype(np.int16)
        mask = np.abs(rgba[..., :3].astype(np.int16) - background).max(axis=2) > tolerance
    if region is not None:
        mask &= np.asarray(region, bool)
    return mask


def shape_contours(mask):
    """Outer outlines and holes of a bool mask (closed by construction, as returned by cv2.findContours)."""
    contours, _ = cv2.findContours(np.asarray(mask, np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    return list(contours)


def turn_back_points(contour):
    """(x, y) points where a contour reverses its direction exactly: the ends of a traced open line (the gap ends)."""
    p = np.asarray(contour, np.int64).reshape(-1, 2)
    if len(p) < 3:
        return [tuple(int(v) for v in q) for q in p]  # a straight line: both ends turn back
    a = p - np.roll(p, 1, axis=0)  # incoming direction
    b = np.roll(p, -1, axis=0) - p  # outgoing direction
    cross = a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
    dot = (a * b).sum(axis=1)
    idx = np.flatnonzero((cross == 0) & (dot < 0))
    return [tuple(int(v) for v in p[i]) for i in idx]


def is_open(contour):
    """True if the contour encloses (almost) no pixels besides the ones it runs over: a traced open line, not a loop."""
    p = np.asarray(contour, np.int32).reshape(-1, 1, 2)
    if len(p) < 3:
        return True
    x, y, w, h = cv2.boundingRect(p)
    p = p - [x - 1, y - 1]
    filled = np.zeros((h + 2, w + 2), np.uint8)
    cv2.drawContours(filled, [p], -1, 1, thickness=cv2.FILLED)
    cv2.drawContours(filled, [p], -1, 0, thickness=1)  # remove the outline itself: what remains is the interior
    interior = int(filled.sum())
    area = abs(cv2.contourArea(p))
    return interior < max(MIN_INTERIOR_PX, MIN_INTERIOR_FRACTION * area)


def find_open_contours(contours):
    """[(index, [gap points (x, y)]), ...] of all contours that are not closed loops (see is_open).
    Specks (contour shorter than MIN_FLAG_LENGTH_PX) are ignored: no relevant cut, no relevant gap."""
    result = []
    for i, c in enumerate(contours):
        p = np.asarray(c).reshape(-1, 2)
        if len(p) < 2 or cv2.arcLength(p.reshape(-1, 1, 2).astype(np.int32), True) < MIN_FLAG_LENGTH_PX:
            continue
        if is_open(p):
            result.append((i, turn_back_points(p)))
    return result
