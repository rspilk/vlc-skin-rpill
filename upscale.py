"""Pixel-art upscaling for the skin's art at scales above 1x.

Scale2x and Scale3x (Andrea Mazzoleni's EPX family) enlarge pixel art by
copying neighbouring pixels into the corners of each enlarged pixel wherever
two edges meet on a diagonal. Straight edges stay exactly as nearest-neighbour
would draw them; staircases on curves and diagonals become smoother. They only
copy existing pixels, so no new colors appear and alpha stays as it was
(including the 1/255 click-target pixels).

build.py composes the art at a whole factor (e.g. 3 for 1.5x) and then
reduces it with an area filter, so every 1x pixel covers the same area
(nearest-neighbour at 1.5x would make some pixels 1 wide and others 2).
"""
import numpy as np
from PIL import Image


def _neighbours(a):
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = a.shape[:2]
    g = lambda dy, dx: p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return {k: g(dy, dx) for k, (dy, dx) in {
        "A": (-1, -1), "B": (-1, 0), "C": (-1, 1),
        "D": (0, -1), "E": (0, 0), "F": (0, 1),
        "G": (1, -1), "H": (1, 0), "I": (1, 1)}.items()}


def _eq(x, y):
    return np.all(x == y, axis=-1)


def _pick(cond, x, y):
    return np.where(cond[..., None], x, y)


def _corners(n):
    """Which corners of E to fill from its neighbours. Plain EPX fills every
    corner where two edges meet, which rounds off the corners of squares and
    bars. Fill only where the edge carries on diagonally (the pixels on the
    other diagonal match E), as it does along a slope or a curve."""
    A, B, C, D, E, F, G, H, I = (n[k] for k in "ABCDEFGHI")
    ok = ~_eq(B, H) & ~_eq(D, F)
    cont_ag = _eq(E, C) | _eq(E, G)   # slope running through A's corner
    cont_ci = _eq(E, A) | _eq(E, I)   # slope running through C's corner
    return (ok & _eq(D, B) & cont_ag, ok & _eq(B, F) & cont_ci,
            ok & _eq(D, H) & cont_ci, ok & _eq(H, F) & cont_ag)


def scale2x(a):
    n = _neighbours(a)
    D, E, F = n["D"], n["E"], n["F"]
    c0, c1, c2, c3 = _corners(n)
    e0 = _pick(c0, D, E)
    e1 = _pick(c1, F, E)
    e2 = _pick(c2, D, E)
    e3 = _pick(c3, F, E)
    h, w, c = a.shape
    out = np.empty((h * 2, w * 2, c), a.dtype)
    out[0::2, 0::2], out[0::2, 1::2] = e0, e1
    out[1::2, 0::2], out[1::2, 1::2] = e2, e3
    return out


def scale3x(a):
    n = _neighbours(a)
    A, B, C, D, E, F, G, H, I = (n[k] for k in "ABCDEFGHI")
    DB, BF, DH, HF = _corners(n)
    cells = [
        _pick(DB, D, E),
        _pick((DB & ~_eq(E, C)) | (BF & ~_eq(E, A)), B, E),
        _pick(BF, F, E),
        _pick((DB & ~_eq(E, G)) | (DH & ~_eq(E, A)), D, E),
        E,
        _pick((BF & ~_eq(E, I)) | (HF & ~_eq(E, C)), F, E),
        _pick(DH, D, E),
        _pick((DH & ~_eq(E, I)) | (HF & ~_eq(E, G)), H, E),
        _pick(HF, F, E),
    ]
    h, w, c = a.shape
    out = np.empty((h * 3, w * 3, c), a.dtype)
    for i, cell in enumerate(cells):
        out[i // 3::3, i % 3::3] = cell
    return out


def epx(im, k):
    """Enlarge by a whole factor k made of 2s and 3s (2, 3, 4, 6, 8, 9, ...)."""
    a = np.asarray(im.convert("RGBA"))
    while k > 1:
        if k % 2 == 0:
            a, k = scale2x(a), k // 2
        elif k % 3 == 0:
            a, k = scale3x(a), k // 3
        else:
            raise ValueError("EPX factor must be a product of 2s and 3s")
    return Image.fromarray(a, "RGBA")


def reduce(im, size):
    """Area-average art drawn larger down to size (w, h). Pillow premultiplies
    alpha for this, so edges don't pick up the color of clear pixels."""
    if im.size == tuple(size):
        return im
    out = np.asarray(im.resize(size, Image.BOX)).copy()
    # keep click targets: any area that had alpha keeps at least 1/255
    had = np.asarray(Image.fromarray(((np.asarray(im)[..., 3] > 0) * 255).astype(np.uint8))
                     .resize(size, Image.BOX)) > 0
    out[had & (out[..., 3] == 0), 3] = 1
    return Image.fromarray(out, "RGBA")
