# UI helpers for the throwaway PyCharm under jetbrains\pycharm. Every input action first verifies that the
# foreground window belongs to that PyCharm process, and refuses to send input otherwise.
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Text;
public class W {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
}
'@
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$script:JbRoot = 'C:\Users\USER\Local\apim-harness-test\jetbrains'

function Get-JbWindows {
  $script:wins = @()
  $cb = [W+EnumProc]{ param($h,$l)
    $p=0; [void][W]::GetWindowThreadProcessId($h,[ref]$p)
    if ([W]::IsWindowVisible($h)) {
      $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
      if ($proc -and $proc.Path -like '*apim-harness-test\jetbrains\pycharm*') {
        $sb = New-Object Text.StringBuilder 256; [void][W]::GetWindowText($h,$sb,256)
        $r = New-Object W+RECT; [void][W]::GetWindowRect($h,[ref]$r)
        if (($r.R-$r.L) -gt 60) { $script:wins += [pscustomobject]@{H=$h;Pid=$p;Title=$sb.ToString();L=$r.L;T=$r.T;W=$r.R-$r.L;Ht=$r.B-$r.T} }
      }
    }
    $true }
  [void][W]::EnumWindows($cb,[IntPtr]::Zero)
  $script:wins
}
function Save-JbShot($w, $name) {
  $bmp = New-Object Drawing.Bitmap $w.W,$w.Ht; $g=[Drawing.Graphics]::FromImage($bmp); $hdc=$g.GetHdc()
  [void][W]::PrintWindow($w.H,$hdc,2); $g.ReleaseHdc($hdc); $g.Dispose(); $bmp.Save("$script:JbRoot\$name.png"); $bmp.Dispose(); "$script:JbRoot\$name.png"
}
function Assert-JbForeground($w) {
  $fg = [W]::GetForegroundWindow(); $p0 = 0; $fgTid = [W]::GetWindowThreadProcessId($fg, [ref]$p0)
  $cur = [W]::GetCurrentThreadId()
  [void][W]::AttachThreadInput($cur, $fgTid, $true)
  [void][W]::ShowWindow($w.H, 9); [void][W]::BringWindowToTop($w.H); [void][W]::SetForegroundWindow($w.H)
  [void][W]::AttachThreadInput($cur, $fgTid, $false)
  Start-Sleep -Milliseconds 500
  $fg2 = [W]::GetForegroundWindow(); $p = 0; [void][W]::GetWindowThreadProcessId($fg2, [ref]$p)
  if ($p -ne $w.Pid) { throw "foreground window is not the test PyCharm (pid $p); refusing to send input" }
}
function Click-Jb($w, $x, $y) {
  Assert-JbForeground $w
  [void][W]::SetCursorPos($w.L + $x, $w.T + $y); Start-Sleep -Milliseconds 150
  [W]::mouse_event(2,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 80; [W]::mouse_event(4,0,0,0,[IntPtr]::Zero); Start-Sleep -Milliseconds 400
}
function Type-Jb($w, $text) {
  Assert-JbForeground $w
  $esc = $text -replace '([+^%~(){}\[\]])','{$1}'
  [Windows.Forms.SendKeys]::SendWait($esc); Start-Sleep -Milliseconds 300
}
function Key-Jb($w, $keys) { Assert-JbForeground $w; [Windows.Forms.SendKeys]::SendWait($keys); Start-Sleep -Milliseconds 400 }
