# Reusable GUI knob, binary switch and finite selector capture from reviewed plans.
param([string]$PlanId = '')
$ErrorActionPreference = 'Stop'
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$launchLog = Join-Path $results ('AFX-scan-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $launchLog | Out-Null
try {
$plans = (Get-Content -Raw (Join-Path $PSScriptRoot 'afx-scan-plans.json') | ConvertFrom-Json).plans
if ([string]::IsNullOrWhiteSpace($PlanId)) {
    Write-Host 'Available reviewed control plans:'
    foreach ($candidate in $plans) {
        Write-Host "$($candidate.id): $($candidate.panel), $($candidate.controls.Count) control(s), AFX $($candidate.channel)"
    }
    $PlanId = Read-Host 'Enter the plan ID to scan (for example instinct-filters)'
}
$matchingPlans = @($plans | Where-Object { $_.id -eq $PlanId })
if ($matchingPlans.Count -ne 1) { throw 'Choose one of the listed reviewed plans.' }
$plan = $matchingPlans[0]
$controlLimit = 3
if (@($plan.controls | Where-Object { $_.kind -eq 'knob_range' }).Count -gt 0) { $controlLimit = 24 }
if (@($plan.controls).Count -lt 1 -or @($plan.controls).Count -gt $controlLimit -or
    @($plan.controls | Where-Object { $_.kind -notin @('binary_button', 'knob_range', 'selector_cycle', 'selector_positions') }).Count -ne 0) {
    throw 'Choose a reviewed button or knob range plan.'
}
$panelLabel = $plan.panel -replace '[^a-zA-Z0-9_-]', '_'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies 'System.Drawing.dll' -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Threading;
public static class AfxScanInput {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
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
        if (SendInput(2, inputs, Marshal.SizeOf(typeof(Input))) != 2) {
            try { Held(false); } finally {
                throw new Exception("Mouse injection failed; release attempted, no retry permitted.");
            }
        }
    }
    public static void Held(bool down) {
        Input[] inputs = new Input[1];
        inputs[0].mouse.flags = down ? 2u : 4u;
        if (SendInput(1, inputs, Marshal.SizeOf(typeof(Input))) != 1)
            throw new Exception("Mouse button injection failed.");
    }
    public static void Sweep(int x, int y, int delta, IntPtr window) {
        int top = GetSystemMetrics(77), height = GetSystemMetrics(79);
        if (height <= 8) throw new Exception("Cannot determine desktop bounds.");
        int end = Math.Max(top + 4, Math.Min(top + height - 5, y + delta));
        int distance = end - y;
        if (Math.Abs(distance) < 16) throw new Exception("Insufficient screen room for drag.");
        int samples = Math.Max(2, (int)Math.Ceiling(Math.Abs(distance) / 4.0));
        try {
            Held(true);
            Thread.Sleep(100);
            for (int i=1; i<=samples; i++) {
                if (GetForegroundWindow() != window || GetAsyncKeyState(27) < 0)
                    throw new Exception("Focus changed or Escape pressed during sweep.");
                if (!SetCursorPos(x, y + (int)Math.Round(distance * (double)i / samples)))
                    throw new Exception("Pointer sweep failed.");
                Thread.Sleep(12);
            }
            Thread.Sleep(100);
        } finally { Held(false); }
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
    # JSON has no numeric infinity. Preserve the displayed endpoint explicitly
    # as a string instead of PowerShell's nonstandard -Infinity token.
    foreach ($key in @($Value.Keys)) {
        if ($Value[$key] -is [double] -and [double]::IsInfinity($Value[$key])) {
            if ($Value[$key] -lt 0) { $Value[$key] = '-Infinity' } else { $Value[$key] = 'Infinity' }
        }
    }
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
    if ([AfxScanInput]::GetAsyncKeyState(27) -lt 0) { throw 'Escape pressed; stopped.' }
    if ([AfxScanInput]::GetForegroundWindow() -ne $handle) { throw 'Panel focus changed; stopped.' }
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
    if ($selected.Count -ne 1 -or $selected[0] -ne [string]$plan.channel) {
        throw "Select unlinked AFX channel $($plan.channel) with $($plan.panel) open."
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

function Read-Knob {
    Assert-Panel
    $labels = $visible[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'NameLabel'))
    $texts = @($labels | Where-Object { -not $_.Current.IsOffscreen -and $_.Current.Name -match $control.status_pattern })
    if ($texts.Count -ne 1) {
        $observed = @($labels | ForEach-Object { $_.Current.Name }) -join '; '
        throw "Expected knob status is missing or ambiguous. Observed: $observed"
    }
    $text = $texts[0].Current.Name
    if ($text -notmatch $control.status_pattern) { throw 'Numeric knob label changed.' }
    $token = $Matches[1]
    if ($token -match '^-(inf(?:inity)?|\u221e)$') { return [double]::NegativeInfinity }
    if ($token -match '^(inf(?:inity)?|\u221e)$') { return [double]::PositiveInfinity }
    return [double]::Parse($token, [System.Globalization.CultureInfo]::InvariantCulture)
}
function Drag-Knob([int]$Delta, [bool]$ReadStatus = $true) {
    Assert-Panel
    $x = [int]($buttonBounds.X + $buttonBounds.Width / 2)
    $y = [int]($buttonBounds.Y + $buttonBounds.Height / 2)
    if (-not [AfxScanInput]::SetCursorPos($x, $y)) { throw 'Cannot position pointer.' }
    # One continuous held sweep. Some controls limit each move event, so a
    # single pointer jump is insufficient even when its distance is large.
    # Native motion avoids expensive UI Automation traversal at every point.
    [AfxScanInput]::Sweep($x, $y, $Delta, $handle)
    Assert-Panel
    # Re-enter the knob after the large sweep so its numeric status is visible.
    [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Left + 8), [int]($windowBounds.Bottom - 8))
    Start-Sleep -Milliseconds 200
    [void][AfxScanInput]::SetCursorPos($x, $y)
    if (-not $ReadStatus) { Start-Sleep -Milliseconds 300; return }
    for ($retry = 0; $retry -lt 6; $retry++) {
        Start-Sleep -Milliseconds 300
        Assert-Panel
        try { return Read-Knob } catch {
            if ($retry -eq 5) { throw }
        }
    }
}
function Run-WireKnobRange {
    foreach ($phase in @('minimum', 'maximum')) {
        $script:index++
        Assert-Panel
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        # Prime away from the lower clamp so the minimum has a fresh captured
        # parameter block even when this knob starts at its minimum.
        if ($phase -eq 'minimum') { Drag-Knob -800 $false }
        $finished = $false
        for ($sweep = 1; $sweep -le 12; $sweep++) {
            $delta = 800
            if ($phase -eq 'maximum') { $delta = -800 }
            Drag-Knob $delta $false
            Write-Record (Join-Path $job "action-$index-sweep-$sweep-done.json") @{ status = 'ok'; sweep = $sweep }
            $feedback = Wait-HostFile "action-$index-sweep-$sweep-feedback.json" 10
            if (-not $feedback.continue) {
                if (-not $feedback.endpoint_verified) { throw 'Host did not verify the captured endpoint.' }
                $finished = $true; break
            }
        }
        if (-not $finished) { throw 'Captured endpoint not reached within the bounded sweeps.' }
        $image = Save-Button ($filePrefix + '-' + $phase + '.png')
        $image.Dispose()
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = 'ok'; phase = $phase; observed_raw = $feedback.observed_raw;
            source = 'captured write endpoint; physical value in screenshot; not device readback'; restored = $false
        }
        $null = Wait-HostFile "action-$index-ack.json" 10
    }
}
function Run-KnobRange {
    # Range-only scan: owner authorized leaving knobs at the final endpoint.
    [void][AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2), [int]($buttonBounds.Y + $buttonBounds.Height/2))
    Start-Sleep -Milliseconds 2200
    $startValue = Read-Knob
    $currentValue = $startValue
    $rangeValues = @()
    foreach ($phase in @('minimum', 'maximum')) {
        $script:index++
        Assert-Panel
        if ((Read-Knob) -ne $currentValue) { throw 'Knob changed outside the trial; stopped.' }
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        $stable = 0; $finished = $false
        $stepLimit = 4
        for ($step = 0; $step -lt $stepLimit; $step++) {
            $delta = 800
            if ($phase -eq 'maximum') { $delta = -800 }
            $next = Drag-Knob $delta
            if (($phase -eq 'minimum' -and $next -gt $currentValue) -or
                ($phase -eq 'maximum' -and $next -lt $currentValue)) { throw 'Drag direction differs from the reviewed gesture.' }
            if ($next -eq $currentValue) { $stable++ } else { $stable = 0 }
            if ($stable -ge 1 -and $step -ge 1) { $finished = $true; $currentValue = $next; break }
            $currentValue = $next
        }
        if (-not $finished) { throw 'Large sweeps did not establish a stable endpoint; stopped.' }
        $labelStatus = 'endpoint label observed'
        if ($phase -eq 'maximum' -and $currentValue -eq $rangeValues[0]) {
            $labelStatus = 'unchanged label; wire range needs review'
        }
        $rangeValues += $currentValue
        $image = Save-Button ($filePrefix + '-' + $phase + '.png')
        $image.Dispose()
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = 'ok'; phase = $phase; starting_value = $startValue; displayed_value = $currentValue;
            source = 'numeric vendor status; rounded display, not device readback'; restored = $false;
            range_label_status = $labelStatus
        }
        $null = Wait-HostFile "action-$index-ack.json" 10
    }
}

[void][AfxScanInput]::SetProcessDPIAware()
Write-Host "$($plan.panel): AFX $($plan.channel), $($plan.controls.Count) reviewed control(s)."
if ($null -eq $plan.coverage) {
    $plan | Add-Member -NotePropertyName coverage -NotePropertyValue @{ status = 'partial; controls outside plan unknown' }
}
Write-Host "Coverage: $($plan.coverage.status)"
foreach ($pending in $plan.coverage.pending) { Write-Host "Pending outside this batch: $pending" }
Write-Host "Prepare $($plan.panel) on unlinked AFX $($plan.channel). Linux recorder must already be waiting."
Write-Host 'The runner operates the selected controls automatically; do not click plugin buttons yourself.'
Write-Host 'After pressing Enter, the terminal minimizes. Focus the plugin using its title bar within 10 seconds.'
Write-Host 'Then leave mouse and keyboard alone. The terminal returns when finished or stopped.'
if (@($plan.controls | Where-Object { $_.kind -eq 'knob_range' }).Count -gt 0) {
    Write-Host 'Range-only test: knobs are left at maximum. Starting values will not be restored.'
}
Write-Host "Launch log saved automatically: $launchLog"
$null = Read-Host 'Press Enter when the panel is ready'
$console = [AfxScanInput]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) { [void][AfxScanInput]::ShowWindow($console, 6) }
$job = $null
$baseline = $null
$changed = $null
$restored = $null
try {
    Start-Sleep -Seconds 10
    $handle = [AfxScanInput]::GetForegroundWindow()
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
    if ((Get-Process -Id $root.Current.ProcessId).ProcessName -ne $plan.process_name) {
        throw 'Focus the Orion vendor panel.'
    }
    $windowBounds = $root.Current.BoundingRectangle
    $panels = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, $plan.panel_class))
    $visible = @($panels | Where-Object {
        -not $_.Current.IsOffscreen -and $windowBounds.Contains($_.Current.BoundingRectangle)
    })
    if ($visible.Count -ne 1) { throw 'Exactly one fully visible target panel is required.' }
    $targets = @()
    foreach ($control in $plan.controls) {
        $buttons = $visible[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ClassNameProperty, $control.class_name))
        $panelBounds = $visible[0].Current.BoundingRectangle
        $candidates = @($buttons | Where-Object {
            $rect = $_.Current.BoundingRectangle
            $inside = -not $_.Current.IsOffscreen -and $panelBounds.Contains($rect)
            if ($null -ne $control.region) {
                $rx = ($rect.X + $rect.Width/2 - $panelBounds.X)/$panelBounds.Width
                $ry = ($rect.Y + $rect.Height/2 - $panelBounds.Y)/$panelBounds.Height
                $inside = $inside -and $rx -ge $control.region.x[0] -and $rx -le $control.region.x[1] -and
                    $ry -ge $control.region.y[0] -and $ry -le $control.region.y[1]
            }
            $inside
        })
        if ($candidates.Count -ne 1) { throw "Missing or ambiguous control: $($control.label)" }
        $targets += @{ definition = $control; element = $candidates[0] }
    }
    $button = $targets[0].element
    $buttonBounds = $button.Current.BoundingRectangle
    if (-not $button.Current.IsEnabled -or -not $windowBounds.Contains($buttonBounds)) {
        throw 'Target button is not fully visible and enabled.'
    }
    $crop = [System.Drawing.Rectangle]::new([int]$buttonBounds.X - 2, [int]$buttonBounds.Y - 2,
        [int]$buttonBounds.Width + 4, [int]$buttonBounds.Height + 4)
    Assert-Panel
    $job = Join-Path $PSScriptRoot ('results\scan-' + $panelLabel + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
    New-Item -ItemType Directory -Path $job | Out-Null
    # Move away from the target so hover highlighting cannot impersonate a state change.
    [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
    Start-Sleep -Milliseconds 500
    Write-Record (Join-Path $job 'request.json') @{
        version = 2; plan_id = $plan.id; panel = $plan.panel; channel = $plan.channel;
        controls = @($plan.controls | ForEach-Object { $_.id });
        actions = [int](($plan.controls | ForEach-Object { if ($_.kind -eq 'selector_cycle') { [int]$_.positions } elseif ($_.kind -eq 'selector_positions') { [int]$_.positions + 1 } else { 2 } } | Measure-Object -Sum).Sum)
    }
    $null = Wait-HostFile 'ready.json' 25
    $index = 0
    foreach ($target in $targets) {
    foreach ($oldBitmap in @($baseline, $changed, $restored)) {
        if ($null -ne $oldBitmap) { $oldBitmap.Dispose() }
    }
    $baseline = $null; $changed = $null; $restored = $null
    $control = $target.definition
    $button = $target.element
    $buttonBounds = $button.Current.BoundingRectangle
    if (-not $button.Current.IsEnabled -or -not $windowBounds.Contains($buttonBounds)) { throw 'Target is no longer enabled/visible.' }
    $crop = [System.Drawing.Rectangle]::new([int]$buttonBounds.X - 2, [int]$buttonBounds.Y - 2,
        [int]$buttonBounds.Width + 4, [int]$buttonBounds.Height + 4)
    $filePrefix = $panelLabel + '-' + $control.id
    if ($control.kind -eq 'knob_range') {
        $crop = [System.Drawing.Rectangle]::new([int]$windowBounds.X, [int]$windowBounds.Y,
            [int]$windowBounds.Width, [int]$windowBounds.Height)
        if ($control.feedback -eq 'captured_wire') { Run-WireKnobRange } else { Run-KnobRange }
        continue
    }
    if ($null -ne $control.visual_region) {
        # Some switches indicate their state in a separate LED above the button.
        $region = $control.visual_region
        $visualBounds = [System.Windows.Rect]::new(
            $windowBounds.X + [double]$region.x, $windowBounds.Y + [double]$region.y,
            [double]$region.width, [double]$region.height)
        if (-not $windowBounds.Contains($visualBounds) -or -not $visualBounds.Contains($buttonBounds)) {
            throw 'Reviewed visual region must contain the button and stay inside the window.'
        }
        $crop = [System.Drawing.Rectangle]::new([int]$visualBounds.X, [int]$visualBounds.Y,
            [int]$visualBounds.Width, [int]$visualBounds.Height)
    }
    $baseline = Save-Button ($filePrefix + '-before.png')
    $phaseCount = 2
    if ($control.kind -in @('selector_cycle', 'selector_positions')) {
        $phaseCount = [int]$control.positions
        if ($phaseCount -lt 2 -or $phaseCount -gt 8) { throw 'Selector needs a reviewed finite cycle.' }
    }
    $positionCount = $phaseCount
    if ($control.kind -eq 'selector_positions') {
        if (@($control.position_points).Count -ne $positionCount) { throw 'Direct selector points are missing.' }
        $phaseCount++
    }
    $restorePosition = -1
    $startingPosition = -1
    $minimumChange = .05
    if ($null -ne $control.minimum_visual_change) {
        $minimumChange = [double]$control.minimum_visual_change
        if ($minimumChange -le 0 -or $minimumChange -gt .05) { throw 'Invalid visual comparison threshold.' }
    }
    $cycleImages = @()
    foreach ($phase in @(1..$phaseCount)) {
        $index++
        Assert-Panel
        if ($control.feedback -ne 'captured_toggle') {
            $current = Save-Button ($filePrefix + '-before-restore.png')
            try {
                $reference = $changed
                if ($phase -eq 1) { $reference = $baseline }
                if ([AfxScanInput]::Difference($reference, $current) -gt [Math]::Min(.02, $minimumChange)) {
                    throw 'Button changed since trial; restoration blocked to preserve newer edits.'
                }
            } finally { $current.Dispose() }
        }
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        Assert-Panel
        if ($control.kind -eq 'selector_positions') {
            $position = $phase - 1
            if ($phase -eq $phaseCount) { $position = $restorePosition }
            if ($position -lt 0 -or $position -ge $positionCount) { throw 'No verified restore position.' }
            # Prime another position first so an already-selected target has fresh OUT evidence.
            foreach ($pointIndex in @((($position + 1) % $positionCount), $position)) {
                $point = $control.position_points[$pointIndex]
                if ([double]$point.x -le 0 -or [double]$point.x -ge 1 -or [double]$point.y -le 0 -or [double]$point.y -ge 1) {
                    throw 'Direct selector point must stay inside its control.'
                }
                Assert-Panel
                if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width * [double]$point.x),
                    [int]($buttonBounds.Y + $buttonBounds.Height * [double]$point.y))) { throw 'Could not position selector mouse.' }
                [AfxScanInput]::Click()
                Start-Sleep -Milliseconds 200
            }
        } else {
            if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
                [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Could not position mouse; stopped.' }
            [AfxScanInput]::Click()
        }
        [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
        Start-Sleep -Milliseconds 700
        if ($phase -lt $phaseCount) {
            $stateFile = $filePrefix + '-changed.png'
            if ($control.kind -in @('selector_cycle', 'selector_positions')) { $stateFile = $filePrefix + '-position-' + $phase + '.png' }
            $changed = Save-Button $stateFile
            $difference = [AfxScanInput]::Difference($baseline, $changed)
            $ok = $difference -gt $minimumChange
            if ($control.kind -eq 'selector_positions') { $ok = $true }
            if ($control.kind -in @('selector_cycle', 'selector_positions')) {
                foreach ($image in $cycleImages) {
                    if ([AfxScanInput]::Difference($image, $changed) -le $minimumChange) { $ok = $false }
                }
                $cycleImages += $changed
            }
        } else {
            $stateFile = $filePrefix + '-restored.png'
            if ($control.kind -in @('selector_cycle', 'selector_positions')) { $stateFile = $filePrefix + '-position-' + $phase + '.png' }
            $restored = Save-Button $stateFile
            $difference = [AfxScanInput]::Difference($baseline, $restored)
            $ok = $difference -le [Math]::Min(.02, $minimumChange)
        }
        if ($control.kind -eq 'selector_positions' -and $phase -eq $positionCount) {
            $matches = @()
            for ($positionIndex = 0; $positionIndex -lt $cycleImages.Count; $positionIndex++) {
                if ([AfxScanInput]::Difference($baseline, $cycleImages[$positionIndex]) -le $minimumChange) { $matches += $positionIndex }
            }
            if ($matches.Count -ne 1) { throw 'Starting appearance does not match exactly one captured position.' }
            $startingPosition = $matches[0]
        }
        if ($control.feedback -eq 'captured_toggle') { $ok = $true }
        $status = 'failed'
        if ($ok) { $status = 'ok' }
        $verificationSource = 'screen comparison; not device readback'
        if ($control.feedback -eq 'captured_toggle') {
            $verificationSource = 'screenshots only; host must verify measured toggle writes before ACK'
        }
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = $status; changed_pixel_fraction = $difference;
            cycle_position = $phase; starting_position = $startingPosition;
            source = $verificationSource; guest_utc = [DateTime]::UtcNow.ToString('o')
        }
        if (-not $ok) { throw 'Visual verification failed; no further clicks.' }
        $ack = Wait-HostFile "action-$index-ack.json" 10
        if ($control.kind -eq 'selector_positions' -and $phase -eq $positionCount) {
            if ($null -eq $ack.restore_position) { throw 'Host did not verify restore position.' }
            $restorePosition = [int]$ack.restore_position
        }
    }
    foreach ($image in $cycleImages) { $image.Dispose() }
    if ($control.kind -notin @('selector_cycle', 'selector_positions') -and $null -ne $changed) { $changed.Dispose() }
    $changed = $null
    }
    Write-Record (Join-Path $job 'completed.json') @{
        status = 'ok'; coverage = $plan.coverage; visual_restoration = (@($plan.controls | Where-Object { $_.kind -eq 'knob_range' -or $_.feedback -eq 'captured_toggle' }).Count -eq 0);
        device_readback_verified = $false; range_knobs_left_at = 'maximum';
        restoration_source = 'images or measured toggle write feedback; range knobs intentionally not restored'
    }
    $null = Wait-HostFile 'host-completed.json' 15
    Write-Host "Planned controls completed; check coverage for remaining controls. Evidence saved to $job"
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
    if ($console -ne [IntPtr]::Zero) { [void][AfxScanInput]::ShowWindow($console, 9) }
}
} finally {
    Stop-Transcript | Out-Null
}
