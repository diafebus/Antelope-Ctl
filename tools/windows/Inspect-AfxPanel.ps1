# Read only the focused vendor panel; output stays beside this script.
[CmdletBinding()]
param(
    [ValidateRange(3, 60)][int]$DelaySeconds = 10,
    [string]$PanelName = '',
    [string]$PanelClass = '',
    [switch]$InspectKnobHover
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PanelName)) {
    $PanelName = Read-Host 'Name of the plugin/panel to inspect (for example Instinct)'
}
$PanelName = $PanelName.Trim()
if ([string]::IsNullOrWhiteSpace($PanelClass)) { $PanelClass = $PanelName }
if ([string]::IsNullOrWhiteSpace($PanelName)) { throw 'A panel name is required.' }
# A label names the evidence; it does not establish which window was focused.
$label = [regex]::Replace($PanelName, '[<>:"/\\|?*\x00-\x1f]', '_')
$label = [regex]::Replace($label, '\s+', '-').Trim([char[]]' .')
if ($label.Length -gt 64) { $label = $label.Substring(0, 64).TrimEnd([char[]]' .') }
if ([string]::IsNullOrWhiteSpace($label)) { throw 'Use a panel name with letters or numbers.' }
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AfxPanelWindow {
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int X, Y; }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
}
'@

[void][AfxPanelWindow]::SetProcessDPIAware()
Write-Host "Focus the $PanelName panel within $DelaySeconds seconds."
Write-Host 'This reads controls and saves a screenshot. It does not click or change settings.'
Write-Host 'The inspection console will minimize so it cannot cover the panel.'
if ($InspectKnobHover) {
    Write-Host 'After focusing the panel, leave the mouse alone. Knobs will be hovered automatically.'
    Write-Host 'No clicks, drags, wheel events or value edits are sent. Escape stops the inspection.'
}
$console = [AfxPanelWindow]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 6) }
Start-Sleep -Seconds $DelaySeconds
$handle = [AfxPanelWindow]::GetForegroundWindow()
$root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
if ($null -eq $root) { throw 'No foreground window found.' }
$process = Get-Process -Id $root.Current.ProcessId
if ($process.ProcessName -match '^(powershell|pwsh|cmd|explorer|WindowsTerminal)$') {
    throw 'The foreground window is not the plugin. Run again and focus the vendor panel.'
}
$bounds = $root.Current.BoundingRectangle
if ($bounds.IsEmpty -or $bounds.Width -lt 1 -or $bounds.Height -lt 1) {
    throw 'The panel is not visible.'
}
$folder = Join-Path $PSScriptRoot ('results\panel-' + $label + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $folder -ErrorAction Stop | Out-Null
# Save the image immediately, before traversing a potentially large UI tree.
# Screen capture requires an unobscured panel. Never restore the console first.
$bitmap = New-Object System.Drawing.Bitmap ([int][Math]::Ceiling($bounds.Width)), ([int][Math]::Ceiling($bounds.Height))
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen([int]$bounds.X, [int]$bounds.Y, 0, 0, $bitmap.Size)
    $bitmap.Save((Join-Path $folder ($label + '-panel.png')), [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
$rows = [System.Collections.Generic.List[object]]::new()
foreach ($element in $elements) {
    try {
        $current = $element.Current
        if ($current.IsPassword) { continue }
        $rect = $current.BoundingRectangle
        # Qt can report IsOffscreen=false for controls many screens away.
        # Require actual intersection with the captured window as well.
        if ($current.IsOffscreen -or $rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0 -or
            $rect.Right -le $bounds.Left -or $rect.Left -ge $bounds.Right -or
            $rect.Bottom -le $bounds.Top -or $rect.Top -ge $bounds.Bottom) { continue }
        $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
        $values = [ordered]@{}
        foreach ($name in @('Value', 'RangeValue', 'Toggle', 'Selection', 'SelectionItem', 'ExpandCollapse')) {
            $patternType = 'System.Windows.Automation.' + $name + 'Pattern'
            $patternId = ([type]$patternType)::Pattern
            $pattern = $null
            if ($element.TryGetCurrentPattern($patternId, [ref]$pattern)) {
                $state = $pattern.Current
                switch ($name) {
                    'Value' { $values.value = $state.Value; $values.read_only = $state.IsReadOnly }
                    'RangeValue' {
                        $values.range = @{ value = $state.Value; minimum = $state.Minimum;
                            maximum = $state.Maximum; small_change = $state.SmallChange;
                            large_change = $state.LargeChange; read_only = $state.IsReadOnly }
                    }
                    'Toggle' { $values.toggle = $state.ToggleState.ToString() }
                    'Selection' {
                        $values.selection = @($pattern.GetCurrentSelection() | ForEach-Object { $_.Current.Name })
                        $values.can_select_multiple = $state.CanSelectMultiple
                    }
                    'SelectionItem' { $values.selected = $state.IsSelected }
                    'ExpandCollapse' { $values.expansion = $state.ExpandCollapseState.ToString() }
                }
            }
        }
        $position = $null
        if (-not $rect.IsEmpty) {
            $position = @{ x = $rect.X - $bounds.X; y = $rect.Y - $bounds.Y;
                width = $rect.Width; height = $rect.Height }
        }
        $rows.Add(@{ name = $current.Name; automation_id = $current.AutomationId;
            control_type = $current.ControlType.ProgrammaticName; class_name = $current.ClassName;
            enabled = $current.IsEnabled; offscreen = $current.IsOffscreen;
            window_relative_bounds = $position; patterns = $patterns; values = $values })
    } catch {
        $rows.Add(@{ error = 'Control became unavailable during inspection.' })
    }
}
$result = [ordered]@{ version = 2; panel_name = $PanelName; created_utc = [DateTime]::UtcNow.ToString('o');
    device_writes = $false; source = 'Windows UI Automation; not device readback';
    window_title = $root.Current.Name; process_name = $process.ProcessName;
    window_size = @{ width = $bounds.Width; height = $bounds.Height };
    controls = @($rows.ToArray()) }
$result | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $folder ($label + '-controls.json'))
$selectors = @($rows.ToArray() | Where-Object {
    $_.control_type -eq 'ControlType.ComboBox' -or
    $_.patterns -contains 'SelectionPatternIdentifiers.Pattern' -or
    $_.patterns -contains 'ExpandCollapsePatternIdentifiers.Pattern' -or
    $_.class_name -match '(Select|Combo|Model|Cabinet|Speaker|Switch)'
})
[ordered]@{ panel_name = $PanelName; source = 'visible UI metadata; options not exercised';
    controls = $selectors; option_writes_verified = $false } |
    ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $folder ($label + '-selector-inventory.json'))
if ($InspectKnobHover) {
    $cursor = New-Object AfxPanelWindow+Point
    if (-not [AfxPanelWindow]::GetCursorPos([ref]$cursor)) { throw 'Cannot save cursor position.' }
    $hoverRows = [System.Collections.Generic.List[object]]::new()
    try {
        if ($process.ProcessName -ne 'orionstudioiii') { throw 'Focus the Orion control panel.' }
        $panels = @($elements | Where-Object {
            -not $_.Current.IsOffscreen -and $_.Current.ClassName -eq $PanelClass -and
            $_.Current.BoundingRectangle.Left -ge $bounds.Left -and
            $_.Current.BoundingRectangle.Right -le $bounds.Right -and
            $_.Current.BoundingRectangle.Top -ge $bounds.Top -and
            $_.Current.BoundingRectangle.Bottom -le $bounds.Bottom
        })
        $identityStatus = 'class-matched'
        if ($panels.Count -eq 0) {
            $identityStatus = 'heuristic common ancestor; identity requires review'
            # Read-only discovery for panels whose internal class differs from
            # the user-facing name. Use the lowest common ancestor of the
            # fully visible Pot controls; never infer a gesture/write plan.
            $allKnobs = @($elements | Where-Object {
                $_.Current.ClassName -match 'Pot' -and -not $_.Current.IsOffscreen -and
                -not $_.Current.IsPassword -and $bounds.Contains($_.Current.BoundingRectangle)
            })
            if ($allKnobs.Count -gt 0 -and $allKnobs.Count -le 64) {
                $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
                $ancestor = $walker.GetParent($allKnobs[0])
                for ($depth = 0; $depth -lt 16 -and $null -ne $ancestor; $depth++) {
                    if ([System.Windows.Automation.Automation]::Compare($ancestor, $root)) { break }
                    $descendants = @($ancestor.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                        [System.Windows.Automation.Condition]::TrueCondition))
                    $containsAll = $true
                    foreach ($knob in $allKnobs) {
                        $found = $false
                        foreach ($child in $descendants) {
                            if ([System.Windows.Automation.Automation]::Compare($child, $knob)) { $found = $true; break }
                        }
                        if (-not $found) { $containsAll = $false; break }
                    }
                    if ($containsAll -and $bounds.Contains($ancestor.Current.BoundingRectangle)) {
                        $panels = @($ancestor); break
                    }
                    $ancestor = $walker.GetParent($ancestor)
                }
            }
        }
        if ($panels.Count -ne 1) { throw 'Cannot identify one visible plugin. No hover performed; base control inventory was saved.' }
        $panel = $panels[0]
        $knobs = @($panel.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition) | Where-Object {
                $_.Current.ClassName -match 'Pot' -and -not $_.Current.IsOffscreen -and
                $_.Current.IsEnabled -and -not $_.Current.IsPassword
            })
        if ($knobs.Count -eq 0 -or $knobs.Count -gt 64) { throw 'No bounded knob inventory found.' }
        $index = 0
        foreach ($knob in $knobs) {
            if ([AfxPanelWindow]::GetAsyncKeyState(27) -lt 0) { throw 'Escape pressed.' }
            if ([AfxPanelWindow]::GetForegroundWindow() -ne $handle -or $root.Current.BoundingRectangle -ne $bounds) {
                throw 'Panel focus or position changed; stopped.'
            }
            $rect = $knob.Current.BoundingRectangle
            $pb = $panel.Current.BoundingRectangle
            if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0 -or
                $rect.Left -lt $pb.Left -or $rect.Right -gt $pb.Right -or
                $rect.Top -lt $pb.Top -or $rect.Bottom -gt $pb.Bottom) { throw 'Knob bounds are not inside the plugin.' }
            # Clear the preceding hover first. The vendor status strip may lag
            # behind pointer motion, especially through the VM display.
            if (-not [AfxPanelWindow]::SetCursorPos([int]($bounds.Left + 8), [int]($bounds.Bottom - 8))) {
                throw 'Pointer movement failed.'
            }
            Start-Sleep -Milliseconds 500
            if (-not [AfxPanelWindow]::SetCursorPos([int]($rect.X + $rect.Width / 2), [int]($rect.Y + $rect.Height / 2))) {
                throw 'Pointer movement failed.'
            }
            Start-Sleep -Milliseconds 2200
            if ([AfxPanelWindow]::GetForegroundWindow() -ne $handle -or $root.Current.BoundingRectangle -ne $bounds) {
                throw 'Panel changed while hovering; stopped.'
            }
            $index++
            $name = '{0:D2}-{1}' -f $index, ($knob.Current.ClassName -replace '[^a-zA-Z0-9_-]', '_')
            $bitmap = New-Object System.Drawing.Bitmap ([int][Math]::Ceiling($bounds.Width)), ([int][Math]::Ceiling($bounds.Height))
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.CopyFromScreen([int]$bounds.X, [int]$bounds.Y, 0, 0, $bitmap.Size)
                $bitmap.Save((Join-Path $folder ($name + '-hover.png')), [System.Drawing.Imaging.ImageFormat]::Png)
            } finally { $graphics.Dispose(); $bitmap.Dispose() }
            $texts = [System.Collections.Generic.List[object]]::new()
            $visible = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.Condition]::TrueCondition)
            foreach ($element in $visible) {
                try {
                    $c = $element.Current
                    $r = $c.BoundingRectangle
                    if ($c.IsPassword -or $c.IsOffscreen -or $r.IsEmpty -or $r.Right -le $bounds.Left -or
                        $r.Left -ge $bounds.Right -or $r.Bottom -le $bounds.Top -or $r.Top -ge $bounds.Bottom) { continue }
                    $value = $null; $pattern = $null
                    if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
                        $value = $pattern.Current.Value
                    }
                    if (-not [string]::IsNullOrWhiteSpace($c.Name) -or -not [string]::IsNullOrWhiteSpace($value)) {
                        $texts.Add(@{ class_name = $c.ClassName; name = $c.Name; value = $value })
                    }
                } catch { }
            }
            $hoverRows.Add(@{ class_name = $knob.Current.ClassName; screenshot = $name + '-hover.png'; visible_text = @($texts.ToArray()) })
        }
        Write-Host "Saved $($hoverRows.Count) automatic knob hover inspections."
    } finally {
        [void][AfxPanelWindow]::SetCursorPos($cursor.X, $cursor.Y)
        if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
        # The first shared result was malformed after repeated rewrites.
        # Save one complete object to a new file instead.
        $detectedClass = $null
        if ($null -ne $panel) { $detectedClass = $panel.Current.ClassName }
        $hoverResult = [ordered]@{ version = 2; panel_name = $PanelName; panel_class = $detectedClass;
            panel_identity_status = $identityStatus;
            count = $hoverRows.Count; expected_count = $knobs.Count;
            complete = ($hoverRows.Count -eq $knobs.Count -and $knobs.Count -gt 0);
            controls = @($hoverRows.ToArray()) }
        $temporary = Join-Path $folder ($label + '-knob-hover.json.tmp')
        $hoverResult | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $temporary
        Move-Item -LiteralPath $temporary -Destination (Join-Path $folder ($label + '-knob-hover.json'))
    }
}
Write-Host "Saved $($rows.Count) control records and $label-panel.png to $folder"
Write-Host 'Leave the results here; Linux can read them directly.'
if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
