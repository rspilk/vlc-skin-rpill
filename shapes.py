"""Vector redraws of Apill's curved art, for builds above 1x.

The pills, the window frame's rounded corners and the volume crescent were
drawn as simple shapes with flat 1 px bands (outline, highlight ring, fill).
At 1x they are anti-aliased pixels; enlarged, those pixels turn into blurry
staircases. tools/fit_shapes.py fits a shape model to each original image
(geometry to a fraction of a pixel, band widths and colors), and this module
draws the models at any size, so curves stay smooth at 1.5x and 2x.

Models live in shapes.json, keyed by source image path:
    rrect     rounded rectangle: box [x0, y0, x1, y1], corner radius r and
              corner exponent n (2 = circular arcs, more = squarer corners).
              Bands are measured inwards from the edge.
    crescent  ellipse c1/r1 minus ellipse c2/r2 (r: [rx, ry]). Bands are
              measured outwards from the edge of the cut-out ellipse (the
              inner, concave arc), and from the sides of the optional clip
              box [x0, y0, x1, y1] that cuts the shape straight.
    bands     [[depth, gray, alpha], ...]: each band runs to its depth; the
              last band has no depth (null) and fills the rest.
    invert    the image is opaque outside the shape (border-mask.png).
    alpha     "coverage" (edges fade out) or "binary": the original has a hard
              edge, opaque wherever at least `theta` of the pixel is covered.
              Enlarged renders always use coverage, for a smooth silhouette.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

_JSON = Path(__file__).parent / "shapes.json"
MODELS = json.loads(_JSON.read_text(encoding="utf-8")) if _JSON.exists() else {}


def _rrect_depth(m, x, y):
    x0, y0, x1, y1 = m["box"]
    r, n = m["r"], m.get("n", 2.0)
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    qx, qy = np.abs(x - cx) - (hx - r), np.abs(y - cy) - (hy - r)
    ox, oy = np.maximum(qx, 0), np.maximum(qy, 0)
    out = (ox ** n + oy ** n) ** (1 / n) + np.minimum(np.maximum(qx, qy), 0) - r
    return -out  # > 0 inside


def _ellipse_dist(x, y, c, r):
    """Signed distance (to first order) from an ellipse's edge; < 0 inside."""
    rx, ry = (r, r) if np.isscalar(r) else r
    u, v = (x - c[0]) / rx, (y - c[1]) / ry
    q = np.hypot(u, v)
    grad = np.hypot(u / rx, v / ry) / np.maximum(q, 1e-9)
    return (q - 1) / np.maximum(grad, 1e-9)


def band_index(m, x, y):
    """Band of each sample point: 0, 1, ... or -1 outside the shape."""
    if m["type"] == "rrect":
        inside = d = _rrect_depth(m, x, y)
        inside = inside > 0
    elif m["type"] == "crescent":
        d = _ellipse_dist(x, y, m["c2"], m["r2"])
        inside = (_ellipse_dist(x, y, m["c1"], m["r1"]) < 0) & (d > 0)
        if "clip" in m:  # cut straight by a box; the rim follows that edge too
            x0, y0, x1, y1 = m["clip"]
            d = np.minimum.reduce([d, x - x0, y - y0, x1 - x, y1 - y])
            inside &= d > 0
    else:
        raise ValueError(m["type"])
    idx = np.zeros(x.shape, np.int8)
    for depth in [b[0] for b in m["bands"][:-1]]:
        idx += d >= depth
    return np.where(inside, idx, -1)


def _samples(w, h, k, ss, origin=(0, 0)):
    """Sample points (in 1x units) for a w x h image drawn k times larger."""
    o = (np.arange(ss) + 0.5) / ss
    xs = ((np.arange(w * k)[:, None] + o) / k).ravel() + origin[0]
    ys = ((np.arange(h * k)[:, None] + o) / k).ravel() + origin[1]
    return np.meshgrid(xs, ys)


def band_fractions(m, w, h, k=1, ss=8, origin=(0, 0)):
    """Per output pixel, the share of its area in each band: (H, W, bands).
    origin offsets the w x h area within the image (for fitting a window)."""
    x, y = _samples(w, h, k, ss, origin)
    idx = band_index(m, x, y)
    nb = len(m["bands"])
    H, W = h * k, w * k
    onehot = (idx[..., None] == np.arange(nb)).astype(np.float32)
    return onehot.reshape(H, ss, W, ss, nb).mean(axis=(1, 3))


def render(rel, k, alpha=None, ss=None):
    """Draw the model for source image `rel` at k times its size (RGBA).
    alpha overrides the model's alpha mode ("coverage" or "binary")."""
    m = MODELS[rel]
    w, h = m["size"]
    ss = ss or max(4, 16 // k)
    frac = band_fractions(m, w, h, k, ss)
    gray = np.array([b[1] for b in m["bands"]], np.float32)
    a = np.array([b[2] for b in m["bands"]], np.float32) / 255
    mode = alpha or ("coverage" if k > 1 else m["alpha"])
    if mode == "binary":
        cover = frac.sum(-1)
        inside = cover >= m["theta"]
        val = (frac * gray).sum(-1) / np.maximum(cover, 1e-9)
        al = np.where(inside, (frac * a).sum(-1) / np.maximum(cover, 1e-9), 0)
    else:
        al = (frac * a).sum(-1)
        val = (frac * a * gray).sum(-1) / np.maximum(al, 1e-9)
    if m.get("invert"):  # a mask: opaque outside the shape
        al, val = 1 - al, np.zeros_like(val)
    v = np.clip(np.round(val), 0, 255).astype(np.uint8)
    out = np.dstack([v, v, v, np.clip(np.round(al * 255), 0, 255).astype(np.uint8)])
    out[out[..., 3] == 0] = 0
    return Image.fromarray(out, "RGBA")
