"""Package a built skin as a VLC addon archive (.vlp) for api.addons.videolan.org.

    python tools/make_vlp.py --creator USER --email ADDRESS
    python tools/make_vlp.py --creator USER --email ADDRESS --version 1.1

--creator and --email are your api.addons.videolan.org account's username and
email; the site records them in the manifest's <authorship> block. The .vlp
is not committed for that reason. See vlc-addon/README.md for the whole
submission process.

A .vlp is a zip with manifest.xml at its root plus the packaged files. The
manifest follows the layout api.addons.videolan.org itself exports:
<videolan><addons><addon type id version> with name, summary, a CDATA
description, <image format="png"> (base64 PNG), an <authorship> block
(creator, email, sourceurl) and one <resource type> per packaged file. VLC
installs each resource into its skins2 folder under the resource's path.
"""
import argparse
import base64
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/rspilk/vlc-skin-rpill"
# The addon's id on api.addons.videolan.org. Uploads with the same id replace the
# existing listing, so keep this fixed for future versions.
ADDON_ID = "a663392d-9849-fddc-897c-77d2cfd5df40"

SUMMARY = ("Brian Bryce's tiny pill-shaped Winamp 3 skin (2001-2002), ported to VLC. "
           "Original size, Default colors.")
DESCRIPTION = """\
Apill is a small, pill-shaped Winamp 3 skin made by Brian Bryce (drwho9437) in 2001-2002, ported to VLC. All of the artwork, layout and colors are his; this port only recolors, rearranges and repackages them for VLC's skin engine.

History: Apill began as "Bluple", a small blue skin. It became "Apple" when he added color themes, since "it no longer has to be blue", and then "Apill" for the final release of Winamp 3. He made it to sit docked at the top of the screen, because most people use their media player while doing something else.

This listing is the original 1x size in the skin's Default (blue) colors.

Included:
- Main window with the crescent volume control, seek bar, shuffle, repeat and repeat-one
- Windowshade mode, with a slide-out drawer of playback controls
- 10-band equalizer
- Resizable playlist editor and video window in the original Winamp 3 frame

More colors and sizes: all seven of the original color presets (Default, More Contrast, Atmoteal, Graple, PEI Sand, Ripple, Yelp) are available on GitHub at 1x and 1.25x, and in high quality, with smooth curves and text, at 1.5x, 2x, 3x and 4x. 1x is very small on modern high-resolution screens, so the larger sizes are worth a look:
{repo}

Build instructions, for any color at any size, are in the README there.

Notes:
- The timer shows 00:07 rather than Winamp's 0:07, because VLC only offers zero-padded time.
- Winamp's crossfade button is repeat-one, and TH shows or hides the video window.
- The equalizer's PRESETS and AUTO buttons are decorative; VLC skins can't reach those features.

Credits: original Winamp 3 skin (c) 2001-2002 Brian Bryce. This is an unofficial port, not endorsed by the original author; see CREDITS.txt inside the skin. The original is on Winamp Heritage: https://winampheritage.com/skin/apill/118660 The text uses fonts generated from Liberation Sans (SIL Open Font License). Tested with VLC 3.0.23 on Windows.""".format(repo=REPO)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skin", default=str(ROOT / "builds/1x/Apill-Default.vlt"))
    ap.add_argument("--thumbnail", default=str(ROOT / "vlc-addon/apill-default-1x.png"))
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--id", default=ADDON_ID, help="addon UUID (default: the published listing)")
    ap.add_argument("--creator", required=True, help="your addons-site username")
    ap.add_argument("--email", required=True, help="your addons-site account email")
    ap.add_argument("--out", default=str(ROOT / "vlc-addon/Apill-Default.vlp"))
    args = ap.parse_args()

    skin = Path(args.skin)
    addon_id = uuid.UUID(args.id)  # validates the format
    image = base64.b64encode(Path(args.thumbnail).read_bytes()).decode("ascii")

    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<videolan xmlns="http://videolan.org/ns/vlc/addons/1.0">
  <addons>
    <addon type="skin" id="{addon_id}" version="{escape(args.version)}">
      <name>Apill</name>
      <summary>{escape(SUMMARY)}</summary>
      <description><![CDATA[{DESCRIPTION}]]></description>
      <image format="png">{image}</image>
      <authorship>
        <creator>{escape(args.creator)}</creator>
        <email>{escape(args.email)}</email>
        <sourceurl>{REPO}</sourceurl>
      </authorship>
      <resource type="skin">{escape(skin.name)}</resource>
    </addon>
  </addons>
</videolan>
"""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("manifest.xml", manifest.encode("utf-8")), (skin.name, skin.read_bytes())):
            info = zipfile.ZipInfo(name, date_time=(2002, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    print("wrote", out, "id", addon_id)


if __name__ == "__main__":
    main()
