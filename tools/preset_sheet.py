"""Compose the preset images from VLC captures (tools/capture_presets.ps1).

    python tools/preset_sheet.py         # apill-color-presets.png: 1x, shown 3x larger
    python tools/preset_sheet.py --hd    # apill-color-presets-hd.png: 1x enlarged to 2x
                                         # next to the high-quality 2x build

Captures are <Preset>-main.png and -shade.png: build/presets/ for the 1x
sheet, build/captures/1x and 2x (same track and volume) for the HD one. The desktop
behind the windows' transparent corners is masked out using the alpha of the
prebuilt skins in builds/.
"""
import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
NAMES = [("Default", "Default (blue)"), ("MoreContrast", "More Contrast (light blue)"),
         ("Atmoteal", "Atmoteal (slate)"), ("Graple", "Graple (khaki)"), ("PEISand", "PEI Sand (brown)"),
         ("Ripple", "Ripple (red)"), ("Yelp", "Yelp (yellow)")]
BG = (236, 233, 216)
lab = ImageFont.truetype("arialbd.ttf", 16)
sub = ImageFont.truetype("arial.ttf", 13)


def alpha(scale, name, binary):
    """The window shape: alpha of an image in the prebuilt Default skin."""
    with zipfile.ZipFile(ROOT / "builds" / ("%gx" % scale) / "Apill-Default.vlt") as z:
        a = Image.open(io.BytesIO(z.read(name))).getchannel("A")
    return a.point(lambda v: 255 if v else 0) if binary else a


def capture(folder, key, part):
    return Image.open(ROOT / "build" / folder / ("%s-%s.png" % (key, part))).convert("RGB")


def big(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def header(d, title, note):
    d.text((10, 10), title, font=lab, fill=(0, 0, 0))
    d.text((10, 30), note + " Original Winamp 3 skin (c) 2001-2002 Brian Bryce.", font=sub, fill=(60, 60, 60))


def original_sheet():
    S = 3
    mmask, smask = big(alpha(1, "main_bg.png", True), S), big(alpha(1, "shade_bg.png", True), S)
    out = Image.new("RGB", ((180 + 178) * S + 60, 50 + len(NAMES) * (46 * S + 40)), BG)
    d = ImageDraw.Draw(out)
    header(d, "Apill for VLC: color presets at 1x (native size), captured from VLC 3",
           "Main window, and windowshade mode.")
    y = 60
    for key, title in NAMES:
        d.text((10, y), title, font=lab, fill=(0, 0, 0))
        y += 22
        out.paste(big(capture("presets", key, "main"), S), (10, y), mmask)
        out.paste(big(capture("presets", key, "shade"), S), (10 + 180 * S + 30, y), smask)
        y += 46 * S + 18
    return out, "apill-color-presets.png"


def hd_sheet():
    """Per preset: the 1x build enlarged pixel for pixel (left) and the
    high-quality 2x build (right), both at the 2x size."""
    masks = {(1, p): big(alpha(1, p + "_bg.png", True), 2) for p in ("main", "shade")}
    masks.update({(2, p): alpha(2, p + "_bg.png", False) for p in ("main", "shade")})
    col = 360 + 40
    out = Image.new("RGB", (10 + 2 * col, 80 + len(NAMES) * (22 + 92 + 10 + 36 + 22)), BG)
    d = ImageDraw.Draw(out)
    header(d, "Apill for VLC: 2x, original pixels vs. high quality, captured from VLC 3",
           "Main window, and windowshade mode.")
    d.text((10, 56), "1x build, every pixel doubled", font=sub, fill=(0, 0, 0))
    d.text((10 + col, 56), "High-quality 2x build", font=sub, fill=(0, 0, 0))
    y = 80
    for key, title in NAMES:
        d.text((10, y), title, font=lab, fill=(0, 0, 0))
        y += 22
        for x, scale in ((10, 1), (10 + col, 2)):
            k = 2 if scale == 1 else 1
            folder = "captures/%dx" % scale  # same track and volume for both
            out.paste(big(capture(folder, key, "main"), k), (x, y), masks[scale, "main"])
            out.paste(big(capture(folder, key, "shade"), k), (x, y + 92 + 10), masks[scale, "shade"])
        y += 92 + 10 + 36 + 22
    return out, "apill-color-presets-hd.png"


if __name__ == "__main__":
    out, name = hd_sheet() if "--hd" in sys.argv[1:] else original_sheet()
    out.save(ROOT / name)
    print("wrote", ROOT / name)
