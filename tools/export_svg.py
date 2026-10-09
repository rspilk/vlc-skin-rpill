"""Write the vector models in shapes.json as SVG files, for editing or for
drawing the skin at any size elsewhere.

    python tools/export_svg.py            # into svg/

Each file is in 1x pixel units with the original image's size, untinted
(grayscale, like the source art; build.py tints per color preset). Rounded
rectangles become one even-odd ring per band, so semi-transparent bands don't
overlap. VLC itself can't load SVG: the skin always ships bitmaps.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "svg"


def rrect_path(x0, y0, x1, y1, r, n, steps=24):
    """Rounded rectangle with superellipse corners (n = 2: circular)."""
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return ""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r == 0:
        return "M%.3f %.3fH%.3fV%.3fH%.3fZ" % (x0, y0, x1, y1, x0)
    pts = []
    # corner centres, clockwise from top-right, and the quarter each one draws
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                       (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90 * i / steps)
            c, s = math.cos(a), math.sin(a)
            # point on |x|^n + |y|^n = r^n in this direction
            k = r / (abs(c) ** n + abs(s) ** n) ** (1 / n)
            pts.append((cx + k * c, cy + k * s))
    return "M" + "L".join("%.3f %.3f" % p for p in pts) + "Z"


def fill(gray, alpha):
    g = round(gray)
    return 'fill="#%02x%02x%02x" fill-opacity="%.3f"' % (g, g, g, alpha / 255)


def rrect_svg(m):
    x0, y0, x1, y1 = m["box"]
    r, n = m["r"], m.get("n", 2.0)
    inset = lambda t: rrect_path(x0 + t, y0 + t, x1 - t, y1 - t, r - t, n)
    out, top = [], 0.0
    for depth, gray, alpha in m["bands"]:
        ring = inset(top) + (inset(depth) if depth is not None else "")
        if alpha > 0:
            out.append('<path fill-rule="evenodd" %s d="%s"/>' % (fill(gray, alpha), ring))
        top = depth
    if m.get("invert"):  # a mask: opaque outside the shape
        w, h = m["size"]
        out = ['<path fill-rule="evenodd" fill="#000" d="M0 0H%dV%dH0Z%s"/>' % (w, h, inset(0))]
    return out


def ellipse(c, r, **attrs):
    rx, ry = (r, r) if not isinstance(r, list) else r
    extra = "".join(' %s="%s"' % (k.replace("_", "-"), v) for k, v in attrs.items())
    return '<ellipse cx="%.3f" cy="%.3f" rx="%.3f" ry="%.3f"%s/>' % (c[0], c[1], rx, ry, extra)


def crescent_svg(m, name):
    (d_rim, g_rim, a_rim), (_, g_body, a_body) = m["bands"]
    w, h = m["size"]
    x0, y0, x1, y1 = m.get("clip", [0, 0, w, h])
    rx, ry = m["r2"]
    defs = ['<clipPath id="%s-clip"><rect x="%g" y="%g" width="%g" height="%g"/></clipPath>'
            % (name, x0, y0, x1 - x0, y1 - y0)]
    shape = '<mask id="%s-shape">%s%s</mask>' % (
        name, ellipse(m["c1"], m["r1"], fill="#fff"), ellipse(m["c2"], m["r2"], fill="#000"))
    # the rim runs along the cut-out ellipse: approximated by one d_rim larger
    body = '<mask id="%s-body">%s%s</mask>' % (
        name, ellipse(m["c1"], m["r1"], fill="#fff"),
        ellipse(m["c2"], [rx + d_rim, ry + d_rim], fill="#000"))
    defs += [shape, body]
    g = ['<g clip-path="url(#%s-clip)">' % name]
    if a_rim > 0:
        g.append('<rect width="%d" height="%d" mask="url(#%s-shape)" %s/>' % (w, h, name, fill(g_rim, a_rim)))
    g.append('<rect width="%d" height="%d" mask="url(#%s-body)" %s/>' % (w, h, name, fill(g_body, a_body)))
    g.append("</g>")
    return ["<defs>"] + defs + ["</defs>"] + g


def main():
    models = json.loads((ROOT / "shapes.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for rel, m in models.items():
        name = Path(rel).stem
        body = rrect_svg(m) if m["type"] == "rrect" else crescent_svg(m, name)
        w, h = m["size"]
        svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
               % (w, h, w, h),
               "<!-- Apill (c) 2001-2002 Brian Bryce: vector redraw of source/%s -->" % rel]
        svg += body + ["</svg>", ""]
        dest = OUT / (rel.replace("/", "_").replace(".png", ".svg"))
        dest.write_text("\n".join(svg), encoding="utf-8")
        print("wrote", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
