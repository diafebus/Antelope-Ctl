# One reversible vendor-UI button trial, with capture coordinated by Linux.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
public static class InstinctPilotInput {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
    [StructLayout(LayoutKind.Sequential)] public struct Mouse {
        public int dx, dy;
        public uint data, flags, time;
        public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Input {
        public uint type;
        public Mouse mouse;
    }
    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint SendInput(uint count, Input[] inputs, int size);
    public static void Click() {
        Input[] inputs = new Input[2];
        inputs[0].mouse.flags = 2;
        inputs[1].mouse.flags = 4;
        if (SendInput(2, inputs, Marshal.SizeOf(typeof(Input))) != 2)
            throw new Exception("Mouse injection failed; no retry permitted.");
    }
    public static double Difference(Bitmap a, Bitmap b) {
        if (a.Size != b.Size) return 1;
        int changed = 0;
        for (int y=0; y<a.Height; y++) for (int x=0; x<a.Width; x++) {
            Color p=a.GetPixel(x,y), q=b.GetPixel(x,y);
            if (Math.Abs(p.R-q.R)>20 || Math.Abs(p.G-q.G)>20 || Math.Abs(p.B-q.B)>20) changed++;
        }
        return (double)changed/(a.Width*a.Height);
    }
}
'@

function Write-Record($Path, $Value) {
    $temporary = $Path + '.tmp'
    $Value | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $temporary
    Move-Item -LiteralPath $temporary -Destination $Path
}
function Wait-HostFile($Name, $Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath (Join-Path $job 'host-error.json')) {
            throw (Get-Content -Raw (Join-Path $job 'host-error.json'))
        }
        $path = Join-Path $job $Name
        if (Test-Path -LiteralPath $path) {
            return (Get-Content -Raw -LiteralPath $path | ConvertFrom-Json)
        }
        Start-Sleep -Milliseconds 100
    }
    throw "No host response: $Name. No further clicks will be sent."
}
function Assert-Panel {
    if ([InstinctPilotInput]::GetAsyncKeyState(27) -lt 0) { throw 'Escape pressed; stopped.' }
    if ([InstinctPilotInput]::GetForegroundWindow() -ne $handle) { throw 'Panel focus changed; stopped.' }
    $now = $root.Current.BoundingRectangle
    if ($now -ne $windowBounds) { throw 'Panel moved or resized; stopped.' }
    $tabs = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'AfxTabButton'))
    $selected = @()
    foreach ($tab in $tabs) {
        $pattern = $null
        if ($tab.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern) -and
            $pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) {
            $selected += $tab.Current.Name.Trim()
        }
    }
    if ($selected.Count -ne 1 -or $selected[0] -ne '2') {
        throw 'Select unlinked AFX channel 2 with Instinct open before running the pilot.'
    }
    if ($button.Current.BoundingRectangle -ne $buttonBounds) { throw 'Control moved; stopped.' }
}
function Save-Button($Name) {
    Assert-Panel
    $bitmap = New-Object System.Drawing.Bitmap ([int]$crop.Width), ([int]$crop.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen([int]$crop.X, [int]$crop.Y, 0, 0, $bitmap.Size)
        $bitmap.Save((Join-Path $job $Name), [System.Drawing.Imaging.ImageFormat]::Png)
    } catch { $bitmap.Dispose(); throw }
    finally { $graphics.Dispose() }
    return $bitmap
}

[void][InstinctPilotInput]::SetProcessDPIAware()
Write-Host 'Instinct pilot: AFX channel 2, ALT Morph only, two clicks maximum.'
Write-Host 'Linux recorder must already be waiting. Focus Instinct within 10 seconds.'
Write-Host 'Leave mouse and keyboard alone during the trial. Escape stops before the next action.'
$console = [InstinctPilotInput]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) { [void][InstinctPilotInput]::ShowWindow($console, 6) }
$job = $null
$baseline = $null
$changed = $null
$restored = $null
try {
    Start-Sleep -Seconds 10
    $handle = [InstinctPilotInput]::GetForegroundWindow()
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
    if ((Get-Process -Id $root.Current.ProcessId).ProcessName -ne 'orionstudioiii') {
        throw 'Focus the Orion vendor panel.'
    }
    $windowBounds = $root.Current.BoundingRectangle
    $panels = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'Instinct'))
    $visible = @($panels | Where-Object {
        -not $_.Current.IsOffscreen -and $windowBounds.Contains($_.Current.BoundingRectangle)
    })
    if ($visible.Count -ne 1) { throw 'Exactly one fully visible Instinct panel is required.' }
    $buttons = $visible[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'AltMorphButton'))
    if ($buttons.Count -ne 1) { throw 'ALT Morph selector is missing or ambiguous.' }
    $button = $buttons[0]
    $buttonBounds = $button.Current.BoundingRectangle
    if (-not $button.Current.IsEnabled -or -not $windowBounds.Contains($buttonBounds)) {
        throw 'ALT Morph is not fully visible and enabled.'
    }
    $crop = [System.Drawing.Rectangle]::new([int]$buttonBounds.X - 2, [int]$buttonBounds.Y - 2,
        [int]$buttonBounds.Width + 4, [int]$buttonBounds.Height + 4)
    Assert-Panel
    $job = Join-Path $PSScriptRoot ('results\pilot-Instinct-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
    New-Item -ItemType Directory -Path $job | Out-Null
    # Move away from the target so hover highlighting cannot impersonate a state change.
    [void][InstinctPilotInput]::SetCursorPos([int]($windowBounds.X + 345), [int]($windowBounds.Y + 55))
    Start-Sleep -Milliseconds 500
    $baseline = Save-Button 'Instinct-AltMorph-before.png'
    Write-Record (Join-Path $job 'request.json') @{
        version = 1; panel = 'Instinct'; channel = 2; control = 'AltMorphButton'; actions = 2
    }
    $null = Wait-HostFile 'ready.json' 25
    foreach ($index in @(1, 2)) {
        Assert-Panel
        if ($index -eq 2) {
            $current = Save-Button 'Instinct-AltMorph-before-restore.png'
            try {
                if ([InstinctPilotInput]::Difference($changed, $current) -gt .02) {
                    throw 'Button changed since trial; restoration blocked to preserve newer edits.'
                }
            } finally { $current.Dispose() }
        }
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index }
        $null = Wait-HostFile "action-$index-go.json" 10
        Assert-Panel
        if (-not [InstinctPilotInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
            [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Could not position mouse; stopped.' }
        [InstinctPilotInput]::Click()
        [void][InstinctPilotInput]::SetCursorPos([int]($windowBounds.X + 345), [int]($windowBounds.Y + 55))
        Start-Sleep -Milliseconds 700
        if ($index -eq 1) {
            $changed = Save-Button 'Instinct-AltMorph-changed.png'
            $difference = [InstinctPilotInput]::Difference($baseline, $changed)
            $ok = $difference -gt .05
        } else {
            $restored = Save-Button 'Instinct-AltMorph-restored.png'
            $difference = [InstinctPilotInput]::Difference($baseline, $restored)
            $ok = $difference -le .02
        }
        $status = 'failed'
        if ($ok) { $status = 'ok' }
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = $status; changed_pixel_fraction = $difference;
            source = 'screen comparison; not device readback'; guest_utc = [DateTime]::UtcNow.ToString('o')
        }
        if (-not $ok) { throw 'Visual verification failed; no further clicks.' }
        $null = Wait-HostFile "action-$index-ack.json" 10
    }
    Write-Record (Join-Path $job 'completed.json') @{
        status = 'ok'; visual_restoration = $true; device_readback_verified = $false
    }
    $null = Wait-HostFile 'host-completed.json' 15
    Write-Host "Pilot completed; evidence saved to $job"
} catch {
    if ($null -ne $job) {
        Write-Record (Join-Path $job 'guest-error.json') @{
            error = $_.Exception.Message; stop = $true; restoration = 'inspect screenshots; not assumed'
        }
    }
    Write-Host "Pilot stopped: $($_.Exception.Message)"
    Write-Host 'Review current state and saved screenshots. No blind restoration will be attempted.'
    exit 1
} finally {
    foreach ($bitmap in @($baseline, $changed, $restored)) {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
    }
    if ($console -ne [IntPtr]::Zero) { [void][InstinctPilotInput]::ShowWindow($console, 9) }
}
