"""Fit the vector models in shapes.json to Apill's original curved art.

    python tools/fit_shapes.py            # refit everything, rewrite shapes.json
    python tools/fit_shapes.py --check    # only report how well shapes.json fits

For each image, the geometry and band depths are searched (Nelder-Mead) and
the band colors are solved exactly (least squares) for each candidate. The
report gives the mean and worst per-pixel error when the model is drawn back
at 1x, and the fraction of pixels that match exactly or within 8 levels.
Needs scipy (only this tool does; the build reads the stored models).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import differential_evolution, minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SRC = ROOT / "source"
OUT = ROOT / "shapes.json"

# image: (shape type, number of bands, alpha mode, invert)
# The crescent is cut off at x = 20, the right side of the volume control.
CLIP = {"player/volume.png": [0, 0, 20, 45]}
# The window frame is cut into 9 pieces and its edges are stretched, so its
# corners must end within 21 px of each side, as in the original art.
CORNER_END = {"system/window/border.png": 21, "system/window/border-inner.png": 21,
              "system/window/border-mask.png": 21}
TARGETS = {
    "player/background.png": ("rrect", 3, "binary", False),
    "player/lcd.png": ("rrect", 6, "coverage", False),
    "player/winshade-background.png": ("rrect", 3, "coverage", False),
    "player/winshade-lcd.png": ("rrect", 6, "coverage", False),
    "system/window/border.png": ("rrect", 3, "coverage", False),
    "system/window/border-inner.png": ("rrect", 6, "coverage", False),
    "system/window/border-mask.png": ("rrect", 1, "binary", True),
    "player/volume.png": ("crescent", 2, "coverage", False),
}


def target(rel, invert):
    a = np.asarray(Image.open(SRC / rel).convert("RGBA")).astype(np.float64)
    gray, al = a[..., 0], a[..., 3] / 255
    if invert:  # the mask is opaque outside the shape: fit the hole instead
        gray, al = np.zeros_like(gray), 1 - al
    return gray, al


def unpack(rel, kind, nb, mode, p):
    if kind == "rrect":
        x0, y0, x1, y1, r = p[:5]
        if rel in CORNER_END:
            e = CORNER_END[rel]
            w, h = SIZES[rel]
            r = min(r, e - x0, e - y0, x1 - (w - e), y1 - (h - e))
        m = {"type": "rrect", "box": list(p[:4]), "r": r, "n": p[5]}
        rest = p[6:]
    else:
        m = {"type": "crescent", "c1": list(p[:2]), "r1": list(p[2:4]),
             "c2": list(p[4:6]), "r2": list(p[6:8])}
        if rel in CLIP:
            m["clip"] = CLIP[rel]
        rest = p[8:]
    depths = list(np.cumsum(np.abs(rest[:nb - 1])))
    theta = float(1 / (1 + np.exp(-rest[nb - 1]))) if mode == "binary" else None
    m["bands"] = [[d, 0, 255] for d in depths] + [[None, 0, 255]]
    return m, theta


def solve(m, theta, mode, gray, al, window):
    """Best band colors for this geometry; returns (model, rendered gray, alpha)."""
    import shapes
    x0, y0, x1, y1 = window
    F = shapes.band_fractions(m, x1 - x0, y1 - y0, origin=(x0, y0))
    G, A = gray[y0:y1, x0:x1], al[y0:y1, x0:x1]
    nb = F.shape[-1]
    Fm = F.reshape(-1, nb)
    if mode == "binary":
        cover = Fm.sum(1)
        inside = cover >= theta
        Fn = Fm[inside] / cover[inside, None]
        g = np.linalg.lstsq(Fn, G.ravel()[inside], rcond=None)[0] if inside.any() else np.zeros(nb)
        g = np.clip(g, 0, 255)
        a = np.ones(nb)
        val = np.zeros(cover.shape)
        val[inside] = Fn @ g
        alpha = inside.astype(float)
    else:
        a = np.clip(np.linalg.lstsq(Fm, A.ravel(), rcond=None)[0], 0, 1)
        q = np.linalg.lstsq(Fm, (G * A).ravel(), rcond=None)[0]
        g = np.clip(q / np.maximum(a, 1e-6), 0, 255)
        alpha = Fm @ a
        val = (Fm @ (a * g)) / np.maximum(alpha, 1e-9)
    for b, gi, ai in zip(m["bands"], g, a):
        b[1], b[2] = round(float(gi), 2), round(float(ai) * 255, 2)
    return val.reshape(G.shape), alpha.reshape(G.shape)


def loss(m, theta, mode, gray, al, window):
    val, alpha = solve(m, theta, mode, gray, al, window)
    x0, y0, x1, y1 = window
    G, A = gray[y0:y1, x0:x1], al[y0:y1, x0:x1]
    return float((((val * alpha - G * A) / 255) ** 2).sum() + ((alpha - A) ** 2).sum())


def circle_through(pts):
    """Least-squares circle through points (Kasa fit): (cx, cy, r)."""
    x, y = np.asarray(pts, float).T
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]
    cx, cy, c = np.linalg.lstsq(A, x * x + y * y, rcond=None)[0]
    return cx, cy, np.sqrt(c + cx * cx + cy * cy)


def crescent_circles(al):
    """Start the search from circles through the crescent's two edges: the soft
    outer (left) edge, and the right side of each row, where the cut-out disc
    begins."""
    outer, inner = [], []
    for y in range(al.shape[0]):
        xs = np.nonzero(al[y] > 0)[0]
        if len(xs) < 3:
            continue
        x0 = xs[0]
        cover = al[y, x0:x0 + 2].sum()  # how far into the first pixels the edge sits
        outer.append((x0 + 2 - cover, y + 0.5))
        inner.append((xs[-1] + 1, y + 0.5))
    n = len(outer)
    o = circle_through(outer[n // 6:n - n // 6])  # the tips belong to both edges
    i = circle_through(inner[n // 6:n - n // 6])
    return [o[0], o[1], o[2], o[2], i[0], i[1], i[2], i[2]]


def initial(kind, nb, mode, al):
    ys, xs = np.nonzero(al > 0.5)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    if kind == "rrect":
        geo = [x0, y0, x1, y1, min(x1 - x0, y1 - y0) / 2 * 0.9, 2.0]
    else:
        geo = crescent_circles(al)
    rest = [1.0] * (nb - 1) + ([0.0] if mode == "binary" else [])
    return np.array(geo + rest, float)


SIZES = {}


def fit(rel):
    kind, nb, mode, invert = TARGETS[rel]
    gray, al = target(rel, invert)
    SIZES[rel] = gray.shape[::-1]
    ys, xs = np.nonzero(al > 0)
    h, w = gray.shape
    window = (max(xs.min() - 2, 0), max(ys.min() - 2, 0), min(xs.max() + 3, w), min(ys.max() + 3, h))
    p0 = initial(kind, nb, mode, al)
    f = lambda p: loss(*unpack(rel, kind, nb, mode, p), mode, gray, al, window)
    best = None
    if kind == "crescent":
        # small and oddly shaped: local search stalls, so search the whole
        # plausible range first (centres within 12 px, radii 0.5x to 3x)
        bounds = [(v - 12, v + 12) for v in p0[:2]] + [(v * 0.5, v * 3) for v in p0[2:4]] +                  [(v - 12, v + 12) for v in p0[4:6]] + [(v * 0.5, v * 3) for v in p0[6:8]] +                  [(0.3, 2.5)] * (nb - 1)
        best = differential_evolution(f, bounds, seed=1, maxiter=400, popsize=20, tol=1e-8,
                                      polish=False)
        p0 = best.x
    for start in (p0, p0 + 0.3):  # two starts; keep the better
        r = minimize(f, start, method="Nelder-Mead",
                     options={"maxiter": 6000, "maxfev": 6000, "xatol": 1e-4, "fatol": 1e-7})
        r = minimize(f, r.x, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-5})
        if best is None or r.fun < best.fun:
            best = r
    m, theta = unpack(rel, kind, nb, mode, best.x)
    solve(m, theta, mode, gray, al, window)
    m = {"size": [w, h], **m, "alpha": mode}
    if theta is not None:
        m["theta"] = theta
    if invert:
        m["invert"] = True
    return round_floats(m)


def round_floats(o):
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, (np.floating,)):
        return round(float(o), 4)
    if isinstance(o, list):
        return [round_floats(v) for v in o]
    if isinstance(o, dict):
        return {k: round_floats(v) for k, v in o.items()}
    return o


def report(rel):
    import shapes
    _, _, _, invert = TARGETS[rel]
    orig = np.asarray(Image.open(SRC / rel).convert("RGBA")).astype(int)
    got = np.asarray(shapes.render(rel, 1)).astype(int)
    if invert:
        orig = orig.copy()
        orig[..., :3] = 0
    # compare as premultiplied gray + alpha (color under a clear pixel is irrelevant)
    po, pg = orig[..., 0] * orig[..., 3] // 255, got[..., 0] * got[..., 3] // 255
    err = np.maximum(abs(po - pg), abs(orig[..., 3] - got[..., 3]))
    # score only the edge: pixels within 2 px of where the original changes
    a = np.pad(orig[..., 0] * 256 + orig[..., 3], 2, mode="edge")
    h, w = err.shape
    near = np.zeros((h, w), bool)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near |= a[2 + dy:2 + dy + h, 2 + dx:2 + dx + w] != a[2:2 + h, 2:2 + w]
    e = err[near]
    print("%-34s edge px: mean err %5.2f  worst %3d  exact %5.1f%%  within 8: %5.1f%%"
          % (rel, e.mean(), e.max(), 100 * (e == 0).mean(), 100 * (e <= 8).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("only", nargs="*")
    args = ap.parse_args()
    if not args.check:
        models = json.loads(OUT.read_text()) if OUT.exists() else {}
        for rel in args.only or TARGETS:
            print("fitting", rel, flush=True)
            models[rel] = fit(rel)
            OUT.write_text(json.dumps(models, indent=1) + "\n")
    import importlib, shapes
    importlib.reload(shapes)
    for rel in args.only or TARGETS:
        report(rel)


if __name__ == "__main__":
    main()
