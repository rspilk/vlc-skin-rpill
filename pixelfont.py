"""Build "pixel-outline" TrueType fonts from aliased (1-bit) text rendering.

Winamp 3 drew Apill's text with GDI Arial and no smoothing. VLC's skins2
engine always anti-aliases TrueType text, so we bake the 1-bit glyphs into a
font whose outlines are pixel squares. Rendered at exactly `ppem` pixels,
every edge falls on the pixel grid and the result is crisp.
"""
from PIL import ImageFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

UNITS = 64  # font units per pixel


def _runs(mask, w, h):
    """Yield (x0, x1, y) horizontal runs of lit pixels."""
    for y in range(h):
        x = 0
        while x < w:
            if mask.getpixel((x, y)):
                x0 = x
                while x < w and mask.getpixel((x, y)):
                    x += 1
                yield x0, x, y
            else:
                x += 1


class _Mask:
    """A 1-bit bitmap with the getpixel/size interface of a PIL mask."""

    def __init__(self, rows):
        self.rows = rows
        self.size = (len(rows[0]) if rows else 0, len(rows))

    def getpixel(self, xy):
        return self.rows[xy[1]][xy[0]]


def _autohinter(src_ttf, ppem):
    """Glyph source using FreeType's auto-hinter (monochrome). Some fonts'
    own hinting gives lumpy strokes at small sizes; this one is cleaner."""
    import freetype
    face = freetype.Face(src_ttf)
    face.set_pixel_sizes(0, ppem)
    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_FORCE_AUTOHINT

    def glyph(ch):
        face.load_char(ch, flags)
        g, bm = face.glyph, face.glyph.bitmap
        rows = [[(bm.buffer[y * bm.pitch + x // 8] >> (7 - x % 8)) & 1 for x in range(bm.width)]
                for y in range(bm.rows)]
        return _Mask(rows), (g.bitmap_left, -g.bitmap_top), (g.advance.x + 32) >> 6

    m = face.size
    return glyph, (m.ascender + 63) >> 6, (-m.descender + 63) >> 6


def _native(src_ttf, ppem):
    """Glyph source using the font's own hinting (via Pillow/FreeType)."""
    font = ImageFont.truetype(src_ttf, ppem)

    def glyph(ch):
        mask, off = font.getmask2(ch, mode="1", anchor="ls")
        return mask, off, round(font.getlength(ch, mode="1"))

    return (glyph,) + font.getmetrics()


def build(src_ttf, ppem, out_path, family, overrides=None, names=None, hinting="native"):
    """overrides: {char: (dx_shift, advance_px)} to tweak individual glyphs.
    names: extra name-table entries, e.g. copyright and license notices.
    hinting: "native" (the font's own hinting) or "autohint" (FreeType's)."""
    overrides = overrides or {}
    glyph, ascent, descent = (_autohinter if hinting == "autohint" else _native)(src_ttf, ppem)

    from fontTools.ttLib import TTFont
    cmap_src = TTFont(src_ttf).getBestCmap()

    glyph_order = [".notdef"]
    cmap, glyphs, metrics = {}, {}, {}

    pen = TTGlyphPen(None)
    glyphs[".notdef"] = pen.glyph()
    metrics[".notdef"] = (ppem // 3 * UNITS, 0)

    for cp in sorted(cmap_src):
        if cp < 0x20 or cp > 0xFFFF:
            continue
        ch = chr(cp)
        name = "uni%04X" % cp
        mask, (ox, oy), adv = glyph(ch)
        dx = 0
        if ch in overrides:
            dx, adv = overrides[ch]
        pen = TTGlyphPen(None)
        w, h = mask.size
        xmin = None
        for x0, x1, y in _runs(mask, w, h):
            # pixel row y (top-down) relative to baseline: top edge = -(oy + y)
            top = -(oy + y) * UNITS
            bot = top - UNITS
            l = (ox + x0 + dx) * UNITS
            r = (ox + x1 + dx) * UNITS
            pen.moveTo((l, bot))
            pen.lineTo((l, top))
            pen.lineTo((r, top))
            pen.lineTo((r, bot))
            pen.closePath()
            xmin = l if xmin is None else min(xmin, l)
        glyph_order.append(name)
        cmap[cp] = name
        glyphs[name] = pen.glyph()
        metrics[name] = (adv * UNITS, xmin or 0)

    fb = FontBuilder(ppem * UNITS, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent * UNITS, descent=-descent * UNITS)
    fb.setupOS2(sTypoAscender=ascent * UNITS, sTypoDescender=-descent * UNITS,
                sTypoLineGap=0, usWinAscent=ascent * UNITS,
                usWinDescent=descent * UNITS)
    fb.setupNameTable({"familyName": family, "styleName": "Regular", **(names or {})})
    fb.setupPost()
    # fixed timestamps keep rebuilt fonts (and the .vlt files) byte-identical
    from fontTools.misc.timeTools import timestampFromString
    stamp = timestampFromString("Tue Jan  1 00:00:00 2002")
    fb.updateHead(created=stamp, modified=stamp)
    # gasp: no grid-fitting, no smoothing hints needed (outlines are on-grid)
    from fontTools.ttLib import newTable
    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = {0xFFFF: 0x000A}
    fb.font["gasp"] = gasp
    fb.save(out_path)
    return ascent, descent
