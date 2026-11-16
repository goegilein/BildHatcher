"""Colour palettes in a perceptual colour space (CIELAB) and the pixel-art clean-up. Pure numpy/OpenCV/sklearn.

P8.2  kmeans_quantize: k-means on the distinct colours (weighted by pixel count) in CIELAB.
P8.3  pixel_art_cleanup: reduce an image to a few clear colour areas without anti-aliasing traces.
"""
import os

# sklearn/joblib otherwise detects the physical CPU cores with a subprocess on Windows (~2 s on first use)
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402

MAX_FIT_COLORS = 100_000  # above this many distinct colours k-means is fitted on a random sample


def rgb_to_lab(rgb):
    """uint8 RGB (..., 3) -> float32 CIELAB (L 0..100)."""
    rgb = np.asarray(rgb, dtype=np.uint8)
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    return lab.reshape(rgb.shape)


def lab_to_rgb(lab):
    """float CIELAB (..., 3) -> uint8 RGB."""
    lab = np.asarray(lab, dtype=np.float32)
    rgb = cv2.cvtColor(lab.reshape(-1, 1, 3), cv2.COLOR_LAB2RGB)
    return np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8).reshape(lab.shape)


def _distinct(rgb):
    """Distinct colours of an (N, 3) uint8 array: (colours (M, 3), inverse (N,), counts (M,))."""
    keys = (rgb[:, 0].astype(np.int32) << 16) | (rgb[:, 1].astype(np.int32) << 8) | rgb[:, 2]
    unique_keys, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    colors = np.stack([unique_keys >> 16, (unique_keys >> 8) & 255, unique_keys & 255], axis=1).astype(np.uint8)
    return colors, inverse.reshape(-1), counts


def kmeans_palette(rgb, n_colors, seed=42):
    """Palette (uint8 RGB (k, 3)) of the pixels `rgb` (N, 3): k-means in CIELAB on the distinct colours, weighted by
    their pixel count (same objective as clustering every pixel, far fewer points)."""
    colors, _, counts = _distinct(rgb)
    n_colors = min(n_colors, len(colors))
    lab = rgb_to_lab(colors).astype(np.float64)
    fit = np.arange(len(colors))
    if len(colors) > MAX_FIT_COLORS:
        fit = np.random.default_rng(seed).choice(len(colors), MAX_FIT_COLORS, replace=False)
    kmeans = KMeans(n_clusters=n_colors, random_state=seed, n_init="auto").fit(lab[fit], sample_weight=counts[fit])
    palette = lab_to_rgb(kmeans.cluster_centers_)
    return np.unique(palette, axis=0)  # two centres can round to the same RGB colour


def nearest(rgb, palette):
    """Index of the nearest palette colour (CIELAB distance) for every colour of `rgb` (N, 3)."""
    colors, inverse, _ = _distinct(rgb)
    d = ((rgb_to_lab(colors)[:, None, :] - rgb_to_lab(palette)[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(d, axis=1)[inverse]


def kmeans_quantize(rgb, n_colors, seed=42):
    """P8.2: every pixel of `rgb` (N, 3) replaced by its nearest colour of a k-means palette in CIELAB."""
    palette = kmeans_palette(rgb, n_colors, seed)
    return palette[nearest(rgb, palette)]


_NEIGHBOURS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _shift(a, dy, dx, fill):
    """a shifted by (dy, dx): out[y, x] = a[y + dy, x + dx], `fill` outside."""
    h, w = a.shape[:2]
    out = np.full_like(a, fill)
    ys, yd = slice(max(dy, 0), h + min(dy, 0)), slice(max(-dy, 0), h + min(-dy, 0))
    xs, xd = slice(max(dx, 0), w + min(dx, 0)), slice(max(-dx, 0), w + min(-dx, 0))
    out[yd, xd] = a[ys, xs]
    return out


def pixel_art_cleanup(image, n_colors=8, min_region=4, edge_threshold=12.0, search_radius=2, seed=42):
    """P8.3: reduce an RGBA image (binary alpha) to at most n_colors clear colour areas.

    1. core pixels: opaque pixels whose 8 neighbours are all opaque and closer than edge_threshold (CIELAB delta E);
       the palette is computed from these only, so anti-aliasing blends at edges cannot become palette colours
    2. core pixels that the palette represents well (delta E < 2 * edge_threshold) get their nearest palette colour;
       every other pixel gets the nearest colour among the already labelled pixels within search_radius, growing
       outwards from the trusted areas (a red/blue blend becomes red or blue, never a third colour that happens to
       be close); pixels that no labelled area reaches fall back to the nearest palette colour
    3. connected regions smaller than min_region pixels are merged into the neighbouring colour they share the
       longest border with
    Transparent pixels are never changed, opaque pixels never become transparent.
    """
    image = np.asarray(image)
    opaque = image[..., 3] > 0
    if not opaque.any():
        return image.copy()
    rgb = image[..., :3]
    lab = rgb_to_lab(rgb)

    # 1. core pixels and palette
    core = opaque.copy()
    for dy, dx in _NEIGHBOURS_8:
        neighbour_lab = _shift(lab, dy, dx, 0)
        neighbour_opaque = _shift(opaque, dy, dx, False)
        delta = np.sqrt(((lab - neighbour_lab) ** 2).sum(axis=2))
        core &= neighbour_opaque & (delta < edge_threshold)
    if core.sum() < max(n_colors, 0.01 * opaque.sum()):  # (almost) no flat areas: use all pixels
        core = opaque
    palette = kmeans_palette(rgb[core], n_colors, seed)
    palette_lab = rgb_to_lab(palette)

    # 2. labels: trusted pixels (core and well represented by the palette) -> nearest palette colour;
    #    all others take the nearest colour among their already labelled neighbours, growing outwards from the
    #    trusted areas (so also wide halos of blends get the colour of the area they belong to)
    nearest_label = np.full(opaque.shape, -1, dtype=np.int32)
    nearest_label[opaque] = nearest(rgb[opaque], palette)
    nearest_delta = np.sqrt(((lab - palette_lab[np.maximum(nearest_label, 0)]) ** 2).sum(axis=2))
    labels = np.where(core & (nearest_delta < 2 * edge_threshold), nearest_label, -1)
    h, w = opaque.shape
    flat_labels, flat_lab = labels.reshape(-1), lab.reshape(-1, 3)
    unknown = np.flatnonzero(opaque & (labels < 0))  # work on the unknown pixels only (usually a thin band)
    offsets = [(dy, dx) for dy in range(-search_radius, search_radius + 1) for dx in range(-search_radius, search_radius + 1)]
    while len(unknown):
        uy, ux = np.divmod(unknown, w)
        best = np.full(len(unknown), np.inf, dtype=np.float32)
        best_label = np.full(len(unknown), -1, dtype=np.int32)
        for dy, dx in offsets:
            ny, nx = uy + dy, ux + dx
            inside = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
            candidate = np.full(len(unknown), -1, dtype=np.int32)
            candidate[inside] = flat_labels[ny[inside] * w + nx[inside]]
            valid = np.flatnonzero(candidate >= 0)
            if not len(valid):
                continue
            d = ((flat_lab[unknown[valid]] - palette_lab[candidate[valid]]) ** 2).sum(axis=1)
            better = d < best[valid]
            best[valid[better]] = d[better]
            best_label[valid[better]] = candidate[valid[better]]
        reached = best_label >= 0
        if not reached.any():  # isolated pixels without any labelled neighbour
            flat_labels[unknown] = nearest_label.reshape(-1)[unknown]
            break
        flat_labels[unknown[reached]] = best_label[reached]
        unknown = unknown[~reached]

    # 3. merge small regions into the neighbour with the longest common border
    if min_region > 1:
        kernel = np.ones((3, 3), np.uint8)
        for label in range(len(palette)):
            count, components, stats, _ = cv2.connectedComponentsWithStats((labels == label).astype(np.uint8), connectivity=8)
            for c in np.flatnonzero(stats[1:, cv2.CC_STAT_AREA] < min_region) + 1:
                x, y, w, h = stats[c, :4]
                x0, y0, x1, y1 = max(x - 1, 0), max(y - 1, 0), x + w + 1, y + h + 1
                region = components[y0:y1, x0:x1] == c
                ring = cv2.dilate(region.astype(np.uint8), kernel).astype(bool) & ~region
                neighbours = labels[y0:y1, x0:x1][ring]
                neighbours = neighbours[(neighbours >= 0) & (neighbours != label)]
                if len(neighbours):
                    labels[y0:y1, x0:x1][region] = np.bincount(neighbours).argmax()

    out = image.copy()
    out[opaque, :3] = palette[labels[opaque]]
    return out
