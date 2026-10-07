# Left-click screen points (physical pixels): click.ps1 132,34 144,34
param([Parameter(ValueFromRemainingArguments)][string[]]$Points)
Add-Type @"
using System; using System.Runtime.InteropServices;
public class M {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int x, int y, uint d, IntPtr e);
}
"@
[M]::SetProcessDPIAware() | Out-Null
foreach ($p in $Points) {
  $x, $y = $p -split ','
  [M]::SetCursorPos([int]$x, [int]$y) | Out-Null
  Start-Sleep -Milliseconds 150
  [M]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 80
  [M]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 600
}
[M]::SetCursorPos(1000, 700) | Out-Null
