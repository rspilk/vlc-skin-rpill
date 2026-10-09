"""Build VLC skins (.vlt) from the Winamp 3 skin Apill.

    python build.py                 # every color preset, at the default 1.25x
    python build.py Default         # one preset
    python build.py --scale 1 ...   # authentic Winamp size (or 2, 1.5, ...)
    python build.py --release       # every preset at 1x, 1.25x, 1.5x, 2x, 3x, 4x into builds/

Apill's art is grayscale and Winamp tinted it at runtime with "gamma groups".
VLC can't tint, so each preset gets its own pre-tinted .vlt. All positions are
copied from the skin's Winamp 3 XML (source/xml, source/system/xml).
"""
import argparse
import math
import os
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import pixelfont
import shapes
import upscale

ROOT = Path(__file__).parent
SRC = ROOT / "source"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
RELEASE = ROOT / "builds"  # committed downloads
RELEASE_SCALES = (1, 1.25, 1.5, 2, 3, 4)
# Text fonts. Liberation Sans (SIL OFL, metric-compatible with Arial) is the
# default so published skins contain no Microsoft font data. Arial reproduces
# Winamp's text pixel for pixel but is for personal builds only.
LIB = ROOT / "vendor/liberation-fonts"
FONTS = {
    "liberation": {
        "regular": str(LIB / "LiberationSans-Regular.ttf"),
        "bold": str(LIB / "LiberationSans-Bold.ttf"),
        "license": LIB / "LICENSE",
        "names": {
            "copyright": "Copyright (c) 2012 Red Hat, Inc., with Reserved Font Name Liberation. "
                         "Digitized data copyright (c) 2010 Google Corporation, with Reserved "
                         "Font Arimo, Tinos and Cousine. Pixel rendering for the Apill VLC skin.",
            "description": "Aliased pixel rendering of Liberation Sans 2.1.5 for the Apill VLC skin.",
            "licenseDescription": "This Font Software is licensed under the SIL Open Font "
                                  "License, Version 1.1.",
            "licenseInfoURL": "https://openfontlicense.org",
        },
        # Liberation's own hinting smears strokes at 11 px; FreeType's auto-hinter is
        # cleaner there. Native looks best at 9 and 14 px (compared visually).
        "hinting": {11: "autohint"},
    },
    "arial": {
        "regular": "C:/Windows/Fonts/arial.ttf",
        "bold": "C:/Windows/Fonts/arialbd.ttf",
        "license": None,
        "names": {"description": "Derived from Microsoft Arial. Personal use only; "
                                 "do not redistribute."},
        "hinting": {},
    },
}
DEFAULT_FONT = "liberation"
FONT = DEFAULT_FONT
NAVY = (50, 63, 110)  # Apill's hard-coded text color (same in every preset)

# Default sizes of the resizable windows (playlist: pledit.xml; video: our pick
# above Winamp's 275x232 minimum).
PL_W, PL_H = 325, 350
VID_W, VID_H = 360, 300

# VLC's skin engine has no zoom setting, so the scale is baked in at build time.
DEFAULT_SCALE = 1.25
SCALE = DEFAULT_SCALE
# How art is enlarged above 1x:
#   "hd"       the art is put together K times larger (see work_factor), from
#              vector redraws of the curved shapes (shapes.py) and pixel-art
#              upscaling of everything else (upscale.py), then reduced to size.
#   "nearest"  the finished 1x art has every pixel drawn bigger.
#   "auto"     hd from 1.5x up. Smaller scales stay nearest, where reducing
#              would only blur the art.
DEFAULT_UPSCALE = "auto"
UPSCALE = DEFAULT_UPSCALE
K = 1  # work factor: the art is composed at K times 1x (set in build)


def S(v):
    """Scale a 1x coordinate. Sizes use S(x + w) - S(x) so edges line up."""
    return int(math.floor(v * SCALE + 0.5))


def read_presets():
    """Parse the <gammaset>s out of source/xml/color-presets.xml."""
    xml = (SRC / "xml/color-presets.xml").read_text(encoding="utf-8")
    presets = {}
    for name, body in re.findall(r'<gammaset id="([^"]+)">(.*?)</gammaset>', xml, re.S):
        presets[name] = {g: tuple(int(v) for v in val.split(","))
                         for g, val in re.findall(r'<gammagroup id="([^"]+)" value="([^"]+)"', body)}
    return presets


PRESETS = read_presets()


# enlarged pixel for pixel, without smoothing: data (volume levels), and the
# EQ's tiny glyphs, where 3 px plus signs would come out as diamonds
NEAREST = {"player/volume-map.png", "eq/eq-elements.png"}


def load(rel):
    """A source image, K times its size."""
    im = Image.open(SRC / rel).convert("RGBA")
    if K == 1:
        return im
    if rel in shapes.MODELS:
        return shapes.render(rel, K)
    if rel in NEAREST:
        return im.resize((im.width * K, im.height * K), Image.NEAREST)
    return upscale.epx(im, K)


def new(w, h, color=0):
    return Image.new("RGBA", (w * K, h * K), color)


def put(dst, src, x, y):
    """Composite src onto dst at the 1x position (x, y)."""
    dst.alpha_composite(src, (x * K, y * K))


def tint(im, preset, group):
    """Winamp 3 gamma: each channel scaled by (4096 + v) / 4096."""
    v = PRESETS[preset].get(group)
    if not v or v == (0, 0, 0):
        return im
    a = np.asarray(im).astype(np.float32)
    for c in range(3):
        a[..., c] *= (4096 + v[c]) / 4096
    return Image.fromarray(np.clip(np.floor(a), 0, 255).astype(np.uint8), "RGBA")


def tint_rgb(rgb, preset, group):
    px = tint(Image.new("RGBA", (1, 1), rgb + (255,)), preset, group).getpixel((0, 0))
    return "#%02X%02X%02X" % px[:3]


def crop(im, x, y, w, h):
    return im.crop((x * K, y * K, (x + w) * K, (y + h) * K))


def stretch(dst, piece, x, y, w=None, h=None):
    w = w * K if w else piece.width
    h = h * K if h else piece.height
    if w <= 0 or h <= 0:
        return
    dst.alpha_composite(piece.resize((w, h), Image.NEAREST), (x * K, y * K))


def vstack(frames):
    w, h = frames[0].size
    out = Image.new("RGBA", (w, h * len(frames)))
    for i, f in enumerate(frames):
        out.paste(f, (0, i * h))
    return out


def boosted(frames):
    """VLC's volume runs 0-200%. Winamp's ran 0-100%, so the art fills over the
    first half of the range and stays full for the boost half."""
    n = len(frames) - 1
    return frames + [frames[-1]] * n


def text_image(text, ttf, ppem, color=NAVY, smooth=False):
    """Aliased Arial text, as Winamp 3 drew it (or anti-aliased, if smooth).
    Returns (image, ascent)."""
    font = ImageFont.truetype(ttf, ppem)
    ascent, descent = font.getmetrics()
    w = math.ceil(font.getlength(text)) + 1 if smooth else round(font.getlength(text, mode="1"))
    im = Image.new("L" if smooth else "1", (w, ascent + descent))
    d = ImageDraw.Draw(im)
    d.fontmode = "L" if smooth else "1"
    d.text((0, ascent), text, font=font, fill=255 if smooth else 1, anchor="ls")
    out = Image.new("RGBA", (im.width + 4, im.height), color + (0,))
    a = Image.new("L", out.size)
    a.paste(im.convert("L"), (2, 0))  # 2 px clear margins: VLC may tile an edge column
    out.putalpha(a)
    return out, ascent


# ---------------------------------------------------------------- main window

VOL_BOX = (7, 8, 20, 36)  # crescent bounding box in the main window


def clickable(im, where=None):
    """VLC ignores clicks on fully transparent pixels. Like Winamp's near-invisible
    "mold" layers, give the empty part of a slider 1/255 alpha so it can be clicked."""
    a = np.asarray(im).copy()
    m = np.ones(a.shape[:2], bool) if where is None else where
    a[m & (a[..., 3] == 0), 3] = 1
    return Image.fromarray(a, "RGBA")


def crescent_frames(lit, vmap, box):
    """One frame per map level: lit where the volume map is below the level."""
    box = tuple(v * K for v in box)
    lit = lit.crop(box)
    vmap = np.asarray(vmap.convert("L").crop(box))
    alpha = np.asarray(lit)[..., 3] > 0
    levels = sorted(set(vmap[alpha].tolist()))
    frames = []
    for k in range(len(levels) + 1):
        on = alpha & (vmap < (levels[k] if k < len(levels) else 256))
        f = Image.new("RGBA", lit.size)
        f.paste(lit, (0, 0), Image.fromarray((on * 255).astype(np.uint8)))
        frames.append(clickable(f, alpha))
    return frames


def bar_frames(lit, box):
    """Horizontal bar filling left to right, one frame per (1x) pixel."""
    lit = lit.crop(tuple(v * K for v in box))
    frames = []
    for k in range(lit.width // K + 1):
        f = Image.new("RGBA", lit.size)
        f.paste(lit.crop((0, 0, k * K, lit.height)), (0, 0))
        frames.append(clickable(f))
    return frames


DRAWER_Y = 3  # open drawer sits where the shade ticker is


def build_main(p, out):
    t = lambda rel, g: tint(load(rel), p, g)

    bg = load("player/background.png")
    put(bg, t("player/lcd.png", "Display Backgrounds"), 4, 4)
    put(bg, t("player/seek-layer.png", "Slider Backgrounds"), 32, 27)
    bg.save(out / "main_bg.png")

    # Winamp buttons use rectrgn="1": the whole rectangle is clickable. Image
    # controls (the status icon) need a copy without that, as VLC draws them unblended.
    btn = t("player/player-buttons.png", "Buttons")
    clickable(btn).save(out / "buttons.png")
    crop(btn, 8, 16, 24, 8).save(out / "status.png")

    vol = crescent_frames(t("player/volume.png", "Buttons"),
                          load("player/volume-map.png"), VOL_BOX)
    vol = boosted(vol)
    vstack(vol).save(out / "volume.png")
    clickable(t("player/progress-level.png", "Sliders")).save(out / "seek.png")

    # windowshade (player-shade.xml)
    sh = load("player/winshade-background.png")
    put(sh, t("player/winshade-lcd.png", "Display Backgrounds"), 2, 2)
    put(sh, tint(crop(load("player/player-buttons.png"), 48, 32, 6, 3), p,
                 "Slider Backgrounds"), 147, 11)  # drawer toggle bg
    sh.save(out / "shade_bg.png")

    # the drawer slides up over the ticker; cover.png hides its lower edge
    dr = sh.copy()
    drawer = new(90, 12)
    drawer.alpha_composite(crop(t("player/drawer-bg.png", "Display Backgrounds"), 0, 0, 90, 12))
    seekbg = t("player/seek-layer.png", "Slider Backgrounds")
    put(drawer, seekbg, 4, 10)
    put(drawer, seekbg, 56, 10)
    put(dr, drawer, 52, DRAWER_Y)
    put(dr, load("player/cover.png"), 49, 15)
    dr.save(out / "drawer_bg.png")
    dvol = boosted(bar_frames(t("player/volume-shade.png", "Buttons"), (56, 10, 86, 12)))
    vstack(dvol).save(out / "drawer_volume.png")
    return {"VOLFRAMES": len(vol), "DVOLFRAMES": len(dvol)}


# ---------------------------------------------------------------- equalizer

EQ_X = [34] + [54 + 6 * i for i in range(10)]  # preamp, then 10 bands (eq-normal.xml)


def build_eq(p, out):
    eq = load("eq/eq-elements.png")
    e = lambda x, y, w, h, g: tint(crop(eq, x, y, w, h), p, g)

    bg = load("player/background.png")
    put(bg, tint(load("player/lcd.png"), p, "Display Backgrounds"), 4, 4)
    for x in (29, 49, 112):  # eqplusminus groups
        put(bg, e(44, 0, 3, 3, "Sliders"), x, 11)
        put(bg, e(44, 11, 3, 1, "Slider Backgrounds"), x, 22)
        put(bg, e(44, 22, 3, 1, "Sliders"), x, 32)
    put(bg, e(36, 0, 7, 5, "Sliders"), 39, 10)  # eqscale: 20 / 0 / 20
    put(bg, e(36, 10, 7, 5, "Slider Backgrounds"), 39, 20)
    put(bg, e(36, 0, 7, 5, "Sliders"), 39, 31)
    put(bg, e(22, 14, 7, 12, "Buttons"), 14, 18)  # "bb" (opacity menu)
    put(bg, e(0, 24, 18, 5, "Buttons"), 128, 20)  # AUTO (no VLC equivalent)
    bg.save(out / "eq_bg.png")

    # bands fill up from the bottom of a 22 px track; 0 dB is half way
    track, fill = e(50, 0, 2, 22, "Slider Backgrounds"), e(50, 24, 2, 1, "Sliders")
    frames = []
    for k in range(22):
        f = track.copy()
        stretch(f, fill, 0, 21 - k, 2, k + 1)
        frames.append(f)
    vstack(frames).save(out / "eq_band.png")

    eqb = new(33, 32)
    put(eqb, e(0, 12, 9, 5, "Buttons"), 0, 0)   # ON
    put(eqb, e(0, 18, 9, 5, "Buttons"), 0, 6)   # ON (enabled)
    put(eqb, e(0, 0, 33, 5, "Buttons"), 0, 12)  # PRESETS
    put(eqb, e(0, 6, 33, 5, "Buttons"), 0, 18)  # PRESETS (pressed)
    clickable(eqb).save(out / "eq_buttons.png")
    return {"EQFRAMES": len(frames)}


def eq_sliders_xml():
    names = ["Preamp", "60 Hz", "170 Hz", "310 Hz", "600 Hz", "1 kHz",
             "3 kHz", "6 kHz", "12 kHz", "14 kHz", "16 kHz"]
    out = []
    for i, (x, name) in enumerate(zip(EQ_X, names)):
        value = "equalizer.preamp" if i == 0 else "equalizer.band(%d)" % (i - 1)
        out.append(
            '      <Slider x="%d" y="12" up="blank" points="(1,21),(1,0)" thickness="5" '
            'value="%s" tooltiptext="%s">\n'
            '        <SliderBackground image="eq_band" nbvert="{EQFRAMES}"/>\n'
            '      </Slider>' % (x, value, name))
    return "\n".join(out)


# ---------------------------------------------------------------- standard frame

FRAME_L, FRAME_R, FRAME_T, FRAME_B = 22, 22, 22, 30


def wa3_frame(p, W, H):
    """Winamp 3 'wasabi.standardframe.statusbar' (system/xml/window-frame.xml)."""
    disp = lambda im: tint(im, p, "Display Backgrounds")
    outer, inner = load("system/window/border.png"), disp(load("system/window/border-inner.png"))
    mask_src = load("system/window/border-mask.png")
    base = disp(Image.new("RGBA", (1, 1), (100, 100, 100, 255))).getpixel((0, 0))
    dot128 = disp(load("system/window/128dot.png"))
    dot48 = disp(load("system/window/48dot.png"))

    img = new(W, H, base)
    mask = new(W, H)
    Hf = H - 19  # frame.layout group height

    stretch(img, dot128, 9, 9, W - 20, Hf - 20)
    for src in (outer, inner):
        stretch(img, crop(src, 0, 0, 22, 22), 0, 0)
        stretch(img, crop(src, 20, 0, 15, 22), 22, 0, W - 44, 22)
        stretch(img, crop(src, 33, 0, 22, 22), W - 22, 0)
        stretch(img, crop(src, 0, 23, 22, 10), 0, 22, 22, Hf - 22)
        stretch(img, crop(src, 33, 23, 22, 10), W - 22, 22, 22, Hf - 22)
    stretch(mask, crop(mask_src, 0, 0, 22, 22), 0, 0)
    stretch(mask, crop(mask_src, 20, 0, 15, 22), 22, 0, W - 44, 22)
    stretch(mask, crop(mask_src, 33, 0, 22, 22), W - 22, 0)
    stretch(mask, crop(mask_src, 0, 23, 22, 10), 0, 22, 22, Hf - 22)
    # Winamp's frame XML puts the right and bottom mask edges 1 px out, which
    # leaves a 1 px strip of frame color outside the outline. 1x keeps that, as
    # Winamp drew it; high-quality builds line the mask up with the art.
    out_ = 21 if K == 1 else 22
    stretch(mask, crop(mask_src, 33, 23, 22, 10), W - out_, 22, 22, Hf - 22)
    stretch(img, dot48, 15, 21, W - 30, 1)
    stretch(img, dot48, 14, 21, 1, Hf - 32)
    stretch(img, dot48, W - 15, 21, 1, Hf - 32)

    for src in (outer, inner):
        stretch(img, crop(src, 0, 33, 22, 22), 0, H - 22)
        stretch(img, crop(src, 20, 33, 10, 22), 22, H - 22, W - 44, 22)
        stretch(img, crop(src, 33, 33, 22, 22), W - 22, H - 22)
    stretch(mask, crop(mask_src, 0, 33, 22, 22), 0, H - 22)
    stretch(mask, crop(mask_src, 20, 33, 10, 22), 22, H - out_, W - 44, 22)
    stretch(mask, crop(mask_src, 33, 33, 22, 22), W - 22, H - 22)
    stretch(img, dot48, 15, H - 15, W - 30, 1)
    stretch(img, dot48, 14, H - 30, 1, 16)
    stretch(img, dot48, W - 15, H - 30, 1, 16)

    a = np.asarray(img).copy()
    m = np.asarray(mask)[..., 3].astype(np.uint32)  # all or nothing at 1x; soft enlarged
    a[..., 3] = a[..., 3] * (255 - m) // 255
    return Image.fromarray(a, "RGBA")


def frame_pieces(p, out):
    """Slice a rendered frame into 9 pieces that VLC stretches when resizing."""
    W = H = 200
    f = wa3_frame(p, W, H)
    a = np.asarray(f)
    # the middle rows are uniform, so stretching them is exact; the top edge has
    # a few faint (alpha < 50) anti-aliasing pixels Winamp smeared when stretching
    assert (a[FRAME_T * K:(H - FRAME_B) * K] == a[FRAME_T * K]).all()
    xs = [(0, FRAME_L), (W // 2, W // 2 + 1), (W - FRAME_R, W)]
    ys = [(0, FRAME_T), (FRAME_T, FRAME_T + 1), (H - FRAME_B, H)]
    for r, (y0, y1) in zip("tmb", ys):
        for c, (x0, x1) in zip("lmr", xs):
            crop(f, x0, y0, x1 - x0, y1 - y0).save(out / ("frame_%s%s.png" % (r, c)))
    return f


def frame_xml(win, W, H, title_id, title_w):
    """XML for a resizable standard frame plus its titlebar and buttons."""
    L, R, T, B = FRAME_L, FRAME_R, FRAME_T, FRAME_B
    cw, ch = W - L - R, H - T - B
    rows = [
        ("tl", 0, 0, L, T, "lefttop", "lefttop", "move"),
        ("tm", L, 0, cw, T, "lefttop", "righttop", "move"),
        ("tr", W - R, 0, R, T, "righttop", "righttop", "move"),
        ("ml", 0, T, L, ch, "lefttop", "leftbottom", "move"),
        ("mm", L, T, cw, ch, "lefttop", "rightbottom", "move"),
        ("mr", W - R, T, R, ch, "righttop", "rightbottom", "resizeE"),
        ("bl", 0, H - B, L, B, "leftbottom", "leftbottom", "resizeS"),
        ("bm", L, H - B, cw, B, "leftbottom", "rightbottom", "resizeS"),
        ("br", W - R, H - B, R, B, "rightbottom", "rightbottom", "resizeSE"),
    ]
    xml = ['      <Image x="%d" y="%d" width="%d" height="%d" image="frame_%s" resize="scale" '
           'lefttop="%s" rightbottom="%s" action="%s"/>' % (x, y, w, h, n, lt, rb, act)
           for n, x, y, w, h, lt, rb, act in rows]
    # titlebar: bold Arial "14" (11 px), centred, baseline 17 (system-groups.xml)
    xml.append('      <Image x="%d" y="%d" image="%s" action="move" xkeepratio="true"/>'
               % (round((W - title_w) / 2), round(17 - TITLE_ASCENT), title_id))
    xml.append('      <Button x="18" y="12" up="menu" down="menu.d" action="dialogs.popup()" '
               'tooltiptext="Menu"/>')
    xml.append('      <Button x="%d" y="12" up="close" down="close.d" action="%s.hide()" '
               'lefttop="righttop" rightbottom="righttop" tooltiptext="Close Window"/>' % (W - 25, win))
    return "\n".join(xml)


TITLE_ASCENT = 0  # set in build_frames


def build_frames(p, out):
    global TITLE_ASCENT
    frame = frame_pieces(p, out)
    titles = {}
    for key, text in (("title_pl", "Playlist Editor"), ("title_video", "Video")):
        # drawn at the final size (not pixel-scaled) so the text stays crisp
        if K > 1:
            im, asc = text_image(text, FONTS[FONT]["bold"], S(11), smooth=True)
            # VLC darkens half-transparent pixels, which would outline smooth
            # text in black: draw it onto the titlebar behind it instead (the
            # same in every column there) so the image is opaque
            col = upscale.reduce(crop(frame, FRAME_L, 0, 1, FRAME_T), (1, S(FRAME_T)))
            y = S(round(17 - asc / SCALE))
            bg = col.crop((0, y, 1, y + im.height)).resize(im.size, Image.NEAREST)
            bg.alpha_composite(im)
            im = bg
        elif SCALE == int(SCALE):
            im, asc = text_image(text, FONTS[FONT]["bold"], 11)
            im = im.resize((im.width * int(SCALE), im.height * int(SCALE)), Image.NEAREST)
            asc *= int(SCALE)
        else:
            im, asc = text_image(text, FONTS[FONT]["bold"], S(11))
        im.save(out / (key + ".png"))
        titles[key] = im.width / SCALE
        TITLE_ASCENT = asc / SCALE

    we = load("system/window/window-elements.png")
    s = lambda x, y, w, h, g: tint(crop(we, x, y, w, h), p, g)
    # the track is 50% black over the list; VLC tiles it opaque, so pre-blend
    sb = tint(new(13, 41, (128, 128, 128, 255)), p, "Display Backgrounds")
    sb.alpha_composite(s(39, 55, 13, 41, "Scrollbar Backgrounds"))
    sb.save(out / "sb_bg.png")
    s(0, 55, 13, 41, "Scrollbar Buttons").save(out / "sb_thumb.png")
    s(26, 55, 13, 41, "Scrollbar Buttons").save(out / "sb_thumb_d.png")
    s(0, 38, 13, 17, "Scrollbar Buttons").save(out / "sb_up.png")
    s(0, 96, 13, 17, "Scrollbar Buttons").save(out / "sb_down.png")

    # video window: wasabi.panel border, horizontal sliders, big buttons
    pw, ph = VID_W - 30, 45
    panel = new(pw, ph)
    stretch(panel, s(19, 114, 2, 2, "Display Backgrounds"), 0, 0)
    stretch(panel, s(21, 114, 16, 2, "Display Backgrounds"), 2, 0, pw - 4, 2)
    stretch(panel, s(37, 114, 2, 2, "Display Backgrounds"), pw - 2, 0)
    stretch(panel, s(19, 116, 2, 16, "Display Backgrounds"), 0, 2, 2, ph - 4)
    stretch(panel, s(37, 116, 2, 16, "Display Backgrounds"), pw - 2, 2, 2, ph - 4)
    stretch(panel, s(19, 132, 2, 2, "Display Backgrounds"), 0, ph - 2)
    stretch(panel, s(21, 132, 16, 2, "Display Backgrounds"), 2, ph - 2, pw - 4, 2)
    stretch(panel, s(37, 132, 2, 2, "Display Backgrounds"), pw - 2, ph - 2)
    # seek bar track (y=-38 in the content group, i.e. 7 px into the panel)
    stretch(panel, s(106, 149, 8, 8, "Big Slider Backgrounds"), 6, 7)
    stretch(panel, s(115, 149, 10, 8, "Big Slider Backgrounds"), 14, 7, pw - 26, 8)
    stretch(panel, s(126, 149, 8, 8, "Slider Backgrounds"), pw - 12, 7)
    # volume track (y=-19)
    stretch(panel, s(106, 149, 8, 8, "Big Slider Backgrounds"), pw - 83, 26)
    stretch(panel, s(115, 149, 10, 8, "Big Slider Backgrounds"), pw - 75, 26, 63, 8)
    stretch(panel, s(126, 149, 8, 8, "Slider Backgrounds"), pw - 12, 26)
    # slice: left part (fixed), stretchable middle column, right part (volume)
    crop(panel, 0, 0, 140, ph).save(out / "vpanel_l.png")
    crop(panel, 140, 0, 1, ph).save(out / "vpanel_m.png")
    crop(panel, pw - 90, 0, 90, ph).save(out / "vpanel_r.png")
    s(106, 136, 15, 13, "Big Sliders").save(out / "vthumb.png")
    s(121, 136, 15, 13, "Big Sliders").save(out / "vthumb_d.png")
    clickable(tint(load("video/video-elements.png"), p, "Buttons")).save(out / "video_buttons.png")

    return {
        "PL_FRAME": frame_xml("playlist", PL_W, PL_H, "title_pl", titles["title_pl"]),
        "VIDEO_FRAME": frame_xml("video", VID_W, VID_H, "title_video", titles["title_video"]),
        "LISTBG": tint_rgb((128, 128, 128), p, "Display Backgrounds"),
    }


# ---------------------------------------------------------------- package

def build_fonts(out):
    """Aliased text at Winamp's 9 px (ticker) and 11 px (timer) Arial sizes.

    At whole-number scales the 1x pixels are simply drawn bigger. Otherwise
    Arial is rendered natively at the scaled size, which stays crisp where
    stretching 1x pixels by e.g. 1.25 would make strokes uneven. High-quality
    builds (K > 1) use smooth text instead, to match the smooth art.
    Returns the point sizes VLC must use."""
    f = FONTS[FONT]
    if K > 1:  # high-quality builds: smooth text, drawn natively at full size
        pixelfont.smooth(f["regular"], S(9), str(out / "apill9.ttf"), "Apill9", names=f["names"])
        pixelfont.smooth(f["regular"], S(11), str(out / "apill11.ttf"), "Apill11",
                         {":": S(7)}, names=f["names"])
        return {"FONT9": S(9), "FONT11": S(11)}
    k = int(SCALE) if SCALE == int(SCALE) else 1
    ppem9, ppem11 = (9, 11) if k > 1 or SCALE == 1 else (S(9), S(11))
    hint = lambda ppem: f["hinting"].get(ppem, "native")
    pixelfont.build(f["regular"], ppem9, str(out / "apill9.ttf"), "Apill9", names=f["names"],
                    hinting=hint(ppem9))
    # Winamp's timer gives the colon a 7 px slot (timecolonwidth="7")
    pixelfont.build(f["regular"], ppem11, str(out / "apill11.ttf"), "Apill11",
                    {":": (0, 7 if k > 1 or SCALE == 1 else S(7))}, names=f["names"],
                    hinting=hint(ppem11))
    return {"FONT9": ppem9 * k, "FONT11": ppem11 * k}


# Vertical frame strips (SliderBackground images): scaled one frame at a time.
STRIPS = {"volume.png": "VOLFRAMES", "drawer_volume.png": "DVOLFRAMES",
          "seek.png": 43, "eq_band.png": "EQFRAMES"}
NOT_SCALED = {"blank.png", "title_pl.png", "title_video.png"}


def work_factor():
    """K for this build: 1 (draw at 1x, then enlarge pixels), or the size the
    art is composed at before reducing to SCALE. A whole multiple of SCALE
    where possible (3 for 1.5x), so the reduction is an even average."""
    if SCALE == 1 or UPSCALE == "nearest" or (UPSCALE == "auto" and SCALE < 1.5):
        return 1
    ks = [k for k in (2, 3, 4, 6, 8, 9, 12) if k >= SCALE - 1e-9]
    return next((k for k in ks if abs(k / SCALE - round(k / SCALE)) < 1e-9), ks[0])


def scale_images(out, vars_):
    """Bring each image from K times 1x to its final size."""
    if SCALE == K:
        return
    for f in out.glob("*.png"):
        if f.name in NOT_SCALED:
            continue
        im = Image.open(f)
        n = STRIPS.get(f.name, 1)
        n = vars_[n] if isinstance(n, str) else n
        w, h = im.width, im.height // n
        size = (S(w // K), S(h // K))
        resize = (lambda fr: fr.resize(size, Image.NEAREST)) if K == 1 else \
            (lambda fr: upscale.reduce(fr, size))
        vstack([resize(im.crop((0, i * h, w, (i + 1) * h))) for i in range(n)]).save(f)


GEOMETRY = ("x", "y", "width", "height", "minwidth", "minheight", "thickness", "range")


def scale_xml(xml, sizes):
    """Scale every position and size in the finished theme.xml.
    sizes: the 1x size of each image, by name."""
    if SCALE == 1:
        return xml

    def tag(m):
        t = m.group(0)
        if t.startswith(("<Font", "<Bitmap ", "<Theme", "<?", "<!")):
            return t
        attrs = dict(re.findall(r'\b([a-z]+)="([^"]*)"', t))
        new = {}
        for a in GEOMETRY:
            if a in attrs and re.fullmatch(r"-?\d+", attrs[a]):
                new[a] = S(int(attrs[a]))
        for a, o in (("width", "x"), ("height", "y")):  # keep shared edges aligned
            if a in new and o in attrs and not t.startswith("<Layout"):
                new[a] = S(int(attrs[o]) + int(attrs[a])) - S(int(attrs[o]))
        up = attrs.get("up")
        if K > 1 and "points" in attrs and t.startswith("<Slider") and up in sizes and up != "blank":
            # VLC centres the thumb on the point, rounding down: scale where
            # its edges go, so it lines up with the art around it (in
            # high-quality builds; smaller scales keep their old positions)
            w, h = sizes[up]
            at = lambda p, d: S(p - d // 2) + S(d) // 2
            new["points"] = re.sub(r"\((-?\d+),(-?\d+)\)", lambda n: "(%d,%d)" % (
                at(int(n.group(1)), w), at(int(n.group(2)), h)), attrs["points"])
        elif "points" in attrs:
            new["points"] = re.sub(r"-?\d+", lambda n: str(S(int(n.group(0)))), attrs["points"])
        for a, v in new.items():
            t = re.sub(r'\b%s="[^"]*"' % a, '%s="%s"' % (a, v), t, count=1)
        return t

    return re.sub(r"<[^>]+>", tag, xml)


def geometry():
    """Numbers the theme.xml template needs for the resizable windows."""
    g = {"PL_W": PL_W, "PL_H": PL_H, "VID_W": VID_W, "VID_H": VID_H}
    # playlist content area (standardframe param "15,22,-30,-52")
    cx, cy, cw, ch = 15, 22, PL_W - 30, PL_H - 52
    g.update(PL_TREE_W=cw - 13, PL_TREE_H=ch, PL_SB_X=cx + cw - 13,
             PL_SB_BG_Y=cy + 17, PL_SB_BG_H=ch - 34, PL_SB_DOWN_Y=cy + ch - 17,
             PL_SB_PTS="(6,%d),(6,%d)" % (ch - 34 - 20, 20))
    # video content: video area on top, 45 px control panel below
    cw, ch = VID_W - 30, VID_H - 52
    py = 22 + ch - 45
    g.update(VID_CW=cw, VID_VH=ch - 45, VID_PY=py, VID_PM_W=cw - 230,
             VID_PR_X=15 + cw - 90, VID_BTN_Y=py + 25,
             VID_SEEK_Y=py + 6, VID_SEEK_W=cw - 9, VID_SEEK_PTS="(7,6),(%d,6)" % (cw - 9 - 8),
             VID_VOL_X=15 + cw - 84, VID_VOL_Y=py + 25)
    return g


# VLC's skin DTD ships with VLC. Override with the VLC_SKIN_DTD environment variable.
DTD_PATHS = [os.environ.get("VLC_SKIN_DTD", ""),
             "C:/Program Files/VideoLAN/VLC/skins/skin.dtd",
             "C:/Program Files (x86)/VideoLAN/VLC/skins/skin.dtd",
             "/usr/share/vlc/skins2/skin.dtd",
             "/Applications/VLC.app/Contents/MacOS/share/skins2/skin.dtd"]


def validate(path):
    """VLC refuses skins that don't match its DTD, so check before packaging."""
    from lxml import etree
    found = next((p for p in DTD_PATHS if p and Path(p).is_file()), None)
    if not found:
        if not getattr(validate, "warned", False):
            print("warning: VLC's skin.dtd not found; skipping validation (set VLC_SKIN_DTD)")
            validate.warned = True
        return
    dtd = etree.DTD(found)
    doc = etree.parse(str(path))
    if not dtd.validate(doc):
        raise SystemExit("theme.xml does not match skin.dtd:\n%s" % dtd.error_log.filter_from_errors())


FONTS_BUILT = {}


def build(preset, dest=None):
    global K
    K = work_factor()
    out = BUILD / preset
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    vars_ = {"PRESET": preset}
    vars_.update(build_main(preset, out))
    vars_.update(build_eq(preset, out))
    vars_.update(build_frames(preset, out))
    vars_.update(geometry())
    vars_["EQ_SLIDERS"] = eq_sliders_xml()
    Image.new("RGBA", (1, 1)).save(out / "blank.png")
    sizes = {f.stem: (Image.open(f).width // K, Image.open(f).height // K)
             for f in out.glob("*.png")}
    scale_images(out, vars_)

    # attribution and licenses travel inside every skin. Line endings are
    # normalized so the .vlt is identical whatever git's checkout settings.
    texts = {"CREDITS.txt": ROOT / "credits/CREDITS.txt",
             "Apill-original-notes.txt": SRC / "notes.txt"}
    if FONTS[FONT]["license"]:
        texts["OFL.txt"] = FONTS[FONT]["license"]
    for name, src in texts.items():
        lines = src.read_bytes().replace(b"\r\n", b"\n").split(b"\n")
        (out / name).write_bytes(b"\r\n".join(lines))

    fonts = BUILD / ("_fonts-%s@%g%s" % (FONT, SCALE, "-hd" if K > 1 else ""))
    if (FONT, SCALE, K) not in FONTS_BUILT:  # once per run, so pixelfont.py changes always apply
        shutil.rmtree(fonts, ignore_errors=True)
        fonts.mkdir(parents=True)
        FONTS_BUILT[FONT, SCALE, K] = build_fonts(fonts)
    vars_.update(FONTS_BUILT[FONT, SCALE, K])
    for f in fonts.iterdir():
        shutil.copy(f, out / f.name)

    xml = (ROOT / "theme.xml").read_text(encoding="utf-8")
    for _ in range(2):  # inserted blocks may contain placeholders themselves
        for k, v in vars_.items():
            xml = xml.replace("{%s}" % k, str(v))
    left = re.findall(r"\{[A-Z_]+\}", xml)
    assert not left, left
    xml = scale_xml(xml, sizes)
    (out / "theme.xml").write_text(xml, encoding="utf-8")
    validate(out / "theme.xml")

    if dest:
        vlt = dest / ("Apill-%s.vlt" % preset.replace(" ", ""))
    else:
        suffix = "" if SCALE == DEFAULT_SCALE else "@%gx" % SCALE
        vlt = DIST / ("Apill-%s%s.vlt" % (preset.replace(" ", ""), suffix))
    vlt.parent.mkdir(parents=True, exist_ok=True)
    # fixed timestamps: rebuilding an unchanged skin gives a byte-identical file
    with zipfile.ZipFile(vlt, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.iterdir()):
            info = zipfile.ZipInfo(f.name, date_time=(2002, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes())
    print("built", vlt)
    return vlt


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("presets", nargs="*", help="color presets (default: all)")
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE,
                    help="size multiplier (default %(default)s; 1 = original Winamp size)")
    ap.add_argument("--font", choices=sorted(FONTS), default=DEFAULT_FONT,
                    help="text font (default %(default)s; arial is for personal builds only)")
    ap.add_argument("--upscale", choices=("auto", "hd", "nearest"), default=DEFAULT_UPSCALE,
                    help="how art is enlarged above 1x (default %(default)s)")
    ap.add_argument("--release", action="store_true",
                    help="build every preset at %s into builds/<scale>x/" % ", ".join(
                        "%gx" % s for s in RELEASE_SCALES))
    args = ap.parse_args()
    FONT = args.font
    UPSCALE = args.upscale
    if args.release:
        if not args.presets:
            shutil.rmtree(RELEASE, ignore_errors=True)
        for SCALE in RELEASE_SCALES:
            for p in args.presets or PRESETS:
                build(p, RELEASE / ("%gx" % SCALE))
    else:
        SCALE = args.scale
        for p in args.presets or PRESETS:
            build(p)
