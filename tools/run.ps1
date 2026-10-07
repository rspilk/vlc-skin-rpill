# Restart a throwaway VLC (config not loaded or saved) with a built skin, then snapshot it.
param([string]$Preset = "Default", [string]$Media = "Short.wav", [int]$Wait = 4)
$root = Split-Path $PSScriptRoot
Get-Process vlc -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*--ignore-config*" } | Stop-Process
Start-Sleep -Milliseconds 500
$vlt = "$root\dist\Apill-$Preset.vlt"
$m = "$root\testmedia\$Media"
$log = "$root\build\vlc.log"
Remove-Item $log -ErrorAction SilentlyContinue
Start-Process "C:\Program Files\VideoLAN\VLC\vlc.exe" -ArgumentList @(
  '--ignore-config', '-I', 'skins', '--file-logging', "--logfile=`"$log`"", '--log-verbose=2',
  "--skins2-last=`"$vlt`"", "`"$m`"")
Start-Sleep $Wait
Remove-Item "$root\build\snap\*" -ErrorAction SilentlyContinue
& "$PSScriptRoot\snap.ps1" -KeepTop
