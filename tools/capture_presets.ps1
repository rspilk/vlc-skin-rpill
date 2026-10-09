# Capture every color preset's main window and windowshade mode from VLC, for
# preset_sheet.py. Needs builds in dist/ (python build.py --scale <Scale>).
# Moves the mouse: VLC's main window sits at the screen's top-left corner.
#   tools\capture_presets.ps1 -Scale 2    # -> build\captures\2x\<Preset>-main.png, -shade.png
#   tools\capture_presets.ps1 -Scale 2 -Only Default,Graple
param([double]$Scale = 1, [string[]]$Only, [string]$Media = "Béla Fleck - Punchdrunk.wav")
$root = Split-Path $PSScriptRoot
$snap = "$root\build\snap"
$suffix = if ($Scale -eq 1.25) { "" } else { "@{0}x" -f $Scale }  # dist/ naming
$out = "$root\build\captures\{0}x" -f $Scale
New-Item -ItemType Directory -Force $out | Out-Null
$S = { param($v) [int][math]::Floor($v * $Scale + 0.5) }

# snapshot until a w x h window shows up at the screen's top-left corner
function Grab($w, $h) {
  for ($i = 0; $i -lt 8; $i++) {
    $f = Get-ChildItem $snap | Where-Object Name -like ("*_{0}x{1}_at0,0.png" -f $w, $h)
    if ($f) { return $f }
    Start-Sleep 1
    Remove-Item "$snap\*" -ErrorAction SilentlyContinue
    & "$PSScriptRoot\snap.ps1" -KeepTop | Out-Null
  }
  throw "no ${w}x${h} window captured"
}

$presets = if ($Only) { $Only } else { "Default", "MoreContrast", "Atmoteal", "Graple", "PEISand", "Ripple", "Yelp" }
foreach ($p in $presets) {
  & "$PSScriptRoot\run.ps1" -Preset "$p$suffix" -Media $Media -Wait 6 | Out-Null
  Copy-Item (Grab (& $S 180) (& $S 46)).FullName "$out\$p-main.png"
  # the windowshade button (x 160, y 17, 9x9 in theme.xml): click its middle
  & "$PSScriptRoot\click.ps1" ("{0},{1}" -f (& $S 164.5), (& $S 21.5))
  Remove-Item "$snap\*" -ErrorAction SilentlyContinue
  Copy-Item (Grab (& $S 178) (& $S 18)).FullName "$out\$p-shade.png"
  Write-Output "$p captured"
}
Get-Process vlc -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*--ignore-config*" } | Stop-Process
