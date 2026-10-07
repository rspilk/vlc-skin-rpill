# Capture every visible top-level window of the running VLC process to PNGs.
param([string]$Out = "$PSScriptRoot\..\build\snap", [switch]$KeepTop)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Collections.Generic;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  public struct RECT { public int L, T, R, B; }
  public static List<IntPtr> For(uint pid) {
    var l = new List<IntPtr>();
    EnumWindows((h, x) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) l.Add(h); return true; }, IntPtr.Zero);
    return l;
  }
}
"@
[W]::SetProcessDPIAware() | Out-Null
New-Item -ItemType Directory -Force $Out | Out-Null
$p = Get-Process vlc -ErrorAction Stop | Select-Object -First 1
$i = 0
foreach ($h in [W]::For([uint32]$p.Id)) {
  $r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
  $w = $r.R - $r.L; $hh = $r.B - $r.T
  if ($w -le 1 -or $hh -le 1) { continue }
  [W]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x13) | Out-Null; Start-Sleep -Milliseconds 300
  $bmp = New-Object System.Drawing.Bitmap $w, $hh
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
  $f = Join-Path $Out ("win{0}_{1}x{2}_at{3},{4}.png" -f $i, $w, $hh, $r.L, $r.T)
  $bmp.Save($f); $g.Dispose(); $bmp.Dispose()
  if (-not $KeepTop) { [W]::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x13) | Out-Null }
  Write-Output $f; $i++
}
