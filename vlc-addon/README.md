# Publishing on VLC's add-ons site

VLC can install skins from its add-ons site, [api.addons.videolan.org](https://api.addons.videolan.org/). This folder holds what the listing needs:

| File | What it is |
|---|---|
| `listing.md` | The text for each field of the site's "Create new addon" form. |
| `apill-default-1x.png` | The thumbnail: the Default 1x main window at its original size (180×46). |
| `apill-default-1x-enlarged3x.png` | The same thumbnail 3 times larger, if the form shrinks small images. |
| `Apill-Default.vlp` | The add-on package, made by `tools/make_vlp.py`. Not committed: its manifest holds your add-ons site username and email. |

The listing is the original 1x skin in Default colors, `builds/1x/Apill-Default.vlt`. Its description points to GitHub for the other colors and sizes.

## Submit through the form

1. Sign in at [api.addons.videolan.org](https://api.addons.videolan.org/) and choose **Create new addon**.
2. Fill in each field from `listing.md`.
3. Upload `builds/1x/Apill-Default.vlt` as the skin file and `apill-default-1x.png` as the image.

## Or upload a package

`tools/make_vlp.py` builds a `.vlp`: a zip of the skin plus a `manifest.xml` that carries the same name, summary, description, thumbnail and source link.

```bash
python build.py --release
python tools/make_vlp.py --creator YOUR_SITE_USERNAME --email YOUR_SITE_EMAIL
```

It writes `vlc-addon/Apill-Default.vlp`. `--creator` and `--email` are your add-ons site account's details. The site records them in the manifest, so they're never stored in this repository.

Options:
- `--version 1.1`: the version for an update. Keep the default add-on ID (`--id`) so the upload replaces the existing listing instead of making a new one.
- `--skin`, `--thumbnail`, `--out`: package a different build, image or output path.

## Updating the listing

The summary and description live in two places: `listing.md` for the form, and `SUMMARY` and `DESCRIPTION` in `tools/make_vlp.py` for packages. Change both together.

## A separate HD listing

The high-quality builds (1.5x and up) could get a listing of their own, such as "Apill HD" with `builds/2x/Apill-Default.vlt`. It would need:
- Its own add-on ID: the site gives one when you create the listing. Pass it with `--id`, so the original listing isn't replaced.
- Its own name, summary and description in `listing.md` and `make_vlp.py`. The text can't say "original size" anymore.
- A 2x thumbnail: crop the main window out of a VLC capture (`tools/capture_presets.ps1 -Scale 2`).
