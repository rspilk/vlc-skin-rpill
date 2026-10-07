"""Compose apill-color-presets.png from VLC captures in build/presets/.

Captures are <Preset>-main.png (180x46) and <Preset>-shade.png (178x18) of
1x builds; transparent corners are masked using build/Default (a 1x build).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "build/presets"
NAMES = [("Default", "Default (blue)"), ("MoreContrast", "More Contrast (light blue)"),
         ("Atmoteal", "Atmoteal (slate)"), ("Graple", "Graple (khaki)"), ("PEISand", "PEI Sand (brown)"),
         ("Ripple", "Ripple (red)"), ("Yelp", "Yelp (yellow)")]
S = 3


def mask(name):
    return Image.open(ROOT / "build/Default" / name).getchannel("A").point(lambda a: 255 if a else 0)


mmask, smask = mask("main_bg.png"), mask("shade_bg.png")
lab = ImageFont.truetype("arialbd.ttf", 16)
sub = ImageFont.truetype("arial.ttf", 13)
out = Image.new("RGB", ((180 + 178) * S + 60, 50 + len(NAMES) * (46 * S + 40)), (236, 233, 216))
d = ImageDraw.Draw(out)
d.text((10, 10), "Apill for VLC: color presets at 1x (native size), captured from VLC 3", font=lab, fill=(0, 0, 0))
d.text((10, 30), "Main window, and windowshade mode. Original Winamp 3 skin (c) 2001-2002 Brian Bryce.",
       font=sub, fill=(60, 60, 60))
y = 60
for key, title in NAMES:
    d.text((10, y), title, font=lab, fill=(0, 0, 0))
    y += 22
    m = Image.open(CAP / f"{key}-main.png").convert("RGB")
    s = Image.open(CAP / f"{key}-shade.png").convert("RGB")
    out.paste(m.resize((180 * S, 46 * S), Image.NEAREST), (10, y), mmask.resize((180 * S, 46 * S), Image.NEAREST))
    out.paste(s.resize((178 * S, 18 * S), Image.NEAREST), (10 + 180 * S + 30, y),
              smask.resize((178 * S, 18 * S), Image.NEAREST))
    y += 46 * S + 18
out.save(ROOT / "apill-color-presets.png")
print("wrote", ROOT / "apill-color-presets.png")
