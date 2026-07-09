# Screenshot Recipes

How to capture the Chrome window as evidence and push it to the user's
phone when they are remote. PowerShell + `System.Drawing` captures actual
rendered pixels from the OS framebuffer — perfect fidelity.

## 1. Activate The Chrome Tab Before Capture

**Single most common cause of blank screenshots**: Chrome MCP can read
and write a hidden tab's DOM (via DevTools Protocol), but Chrome pauses
the paint thread on hidden tabs. OS screenshots capture screen pixels,
not DOM — so a hidden SciStudio tab gives you whichever tab IS active in
its place (usually a cream blank from the new-tab page).

```powershell
# Bring the Chrome window to the foreground
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class TF {
    [DllImport("user32.dll")] public static extern void SwitchToThisWindow(IntPtr h, bool fAlt);
}
"@
$chrome = Get-Process chrome | Where-Object MainWindowTitle -Match 'SciStudio' | Select-Object -First 1
[TF]::SwitchToThisWindow($chrome.MainWindowHandle, $true)
Start-Sleep -Milliseconds 300

# If SciStudio is not the active tab, Ctrl+<N> selects it (N depends on tab strip order)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait('^2')
Start-Sleep -Milliseconds 500
```

Verify via JS before capturing:

```javascript
JSON.stringify({ visibilityState: document.visibilityState, hidden: document.hidden });
// Expect {"visibilityState":"visible","hidden":false}
```

If still hidden, try `^1`, `^3`, etc. — tab strip order varies.

## 2. Capture The Screen

The user has two 4K monitors; default PowerShell capture gives you
DPI-scaled (logical) pixels, not physical. To get the full 7680×2160,
mark the process as DPI-aware **before** any `System.Drawing` or
`System.Windows.Forms` type loads.

```powershell
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DpiAwareness {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[DpiAwareness]::SetProcessDPIAware() | Out-Null

# Load imaging assemblies AFTER DPI awareness is set
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Multi-monitor virtual bounds (covers both screens)
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$gr = [System.Drawing.Graphics]::FromImage($bmp)
$gr.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)

$sessionId = "<session-id-from-frontmatter>"
$step = "<step-N>"
$path = "C:\Users\<user>\Downloads\scistudio-e2e-$sessionId-$step.png"
$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
$gr.Dispose(); $bmp.Dispose()
$path
```

### Resolution Check

After saving, verify the dimensions:

```powershell
$bmp = [System.Drawing.Image]::FromFile($path)
"$($bmp.Width)x$($bmp.Height)"  # expect 7680x2160 on this user's setup
$bmp.Dispose()
```

If it is still 4388×1234, the DPI awareness call was either skipped or
applied too late (after a type that triggered DPI virtualization
loaded). Restart the PowerShell with awareness first.

### Single-Monitor Capture

If multi-monitor capture is overkill:

```powershell
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$gr = [System.Drawing.Graphics]::FromImage($bmp)
$gr.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
# ... save as above
```

## 3. Push Screenshot To User's Phone

When the user is remote (mobile, in transit) and needs to see what you
saw without manually pulling the file:

```
SendUserFile(
  files=["C:/Users/<user>/Downloads/scistudio-e2e-<session-id>-step<N>.png"],
  status="proactive",
  caption="<step label> — <pass/fail> — <observed state>"
)
```

`status: proactive` triggers a phone notification — user sees it
without polling. The caption must describe the scene because the user
may receive many in sequence: which step, which affordance, what was
observed.

## 4. Filename Convention

`scistudio-e2e-<session-id>-step<N>.png` where `<session-id>` matches the
frontmatter and `<N>` is the step number. Examples:

- `scistudio-e2e-2026-05-20-pr-1300-step3.png`
- `scistudio-e2e-2026-05-20-hotfix-869-launch.png`
- `scistudio-e2e-2026-05-20-hotfix-869-after-fix.png`

Section 7.4 of the scenario file lists every screenshot path so the
user can navigate the gallery in order.

## 5. When To Use A GIF Instead

For multi-step interactions where the user needs to see the sequence
of state changes, prefer an animated GIF:

```
mcp__claude-in-chrome__gif_creator(
  filename: "login_process.gif",
  ...
)
```

Per the Chrome MCP system prompt, always capture extra frames before
and after the action for smooth playback. Save to Downloads, push the
same way.

## 6. Capturing An Element, Not The Viewport

Chrome MCP `computer.zoom` accepts a region rectangle but the
`save_to_disk` path is unreliable as of 2026-05-15. Workaround: scroll
the element into view, capture the whole viewport, crop in PowerShell:

```powershell
# After full-screen capture above
$src = [System.Drawing.Image]::FromFile($path)
$crop = New-Object System.Drawing.Rectangle 100, 200, 800, 600
$cropped = $src.Clone($crop, $src.PixelFormat)
$cropped.Save($path.Replace('.png', '-crop.png'))
$src.Dispose(); $cropped.Dispose()
```

## 7. Cleanup

Downloads piles up across sessions. At end of session:

```powershell
Remove-Item C:\Users\<user>\Downloads\scistudio-e2e-<session-id>-*.png
```

Skip this if any screenshot was pushed to the user's phone — the user
may want to revisit them later from Downloads.

## Related

- `chrome-mcp-recipes.md` — driving the page before capture
- `report-template.md` — how to reference captures in Section 7
