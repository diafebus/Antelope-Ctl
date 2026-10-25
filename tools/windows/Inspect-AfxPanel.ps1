# Read only the focused vendor panel; output stays beside this script.
[CmdletBinding()]
param(
    [ValidateRange(3, 60)][int]$DelaySeconds = 10,
    [string]$PanelName = '',
    [string]$PanelClass = '',
    [switch]$InspectKnobHover,
    [switch]$DiscoverForScan,
    [string[]]$InspectMenuClasses = @()
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
if ($InspectMenuClasses.Count -gt 0) { Add-Type -AssemblyName System.Windows.Forms }
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AfxPanelWindow {
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint owner);
    private delegate bool WindowVisitor(IntPtr window, IntPtr argument);
    [DllImport("user32.dll")] private static extern bool EnumWindows(WindowVisitor visitor, IntPtr argument);
    public static IntPtr[] NativeVisibleWindows(uint owner) {
        var windows = new System.Collections.Generic.List<IntPtr>();
        EnumWindows(delegate(IntPtr window, IntPtr argument) {
            uint actualOwner;
            GetWindowThreadProcessId(window, out actualOwner);
            if (actualOwner == owner && IsWindowVisible(window)) windows.Add(window);
            return true;
        }, IntPtr.Zero);
        return windows.ToArray();
    }
}
'@

function Visible-InspectionPopups($MenuBounds) {
    $found = @()
    foreach ($h in [AfxPanelWindow]::NativeVisibleWindows([uint32]$process.Id)) {
        $node = [System.Windows.Automation.AutomationElement]::FromHandle($h)
        $r = [AfxPanelWindow+Rect]::new(); [uint32]$owner = 0
        if ($h -eq [IntPtr]::Zero -or $node.Current.ClassName -cne 'QComboBoxPrivateContainer' -or
            -not [AfxPanelWindow]::IsWindowVisible($h) -or
            [AfxPanelWindow]::GetWindowThreadProcessId($h, [ref]$owner) -eq 0 -or
            $owner -ne [uint32]$process.Id -or -not [AfxPanelWindow]::GetWindowRect($h, [ref]$r)) { continue }
        $width = $r.Right - $r.Left; $height = $r.Bottom - $r.Top
        if ($width -le 0 -or $width -gt 512 -or $height -le 0 -or
            $height -gt [System.Windows.Forms.SystemInformation]::VirtualScreen.Height -or
            [Math]::Abs($r.Left - $MenuBounds.Left) -gt 32 -or
            $r.Top -gt $MenuBounds.Bottom + 32 -or $r.Bottom -lt $MenuBounds.Top - 32) { continue }
        $found += $node
    }
    return $found
}

[void][AfxPanelWindow]::SetProcessDPIAware()
Write-Host "Focus the $PanelName panel within $DelaySeconds seconds."
Write-Host 'This reads controls and saves a screenshot.'
if ($InspectMenuClasses.Count -gt 0) {
    Write-Host 'Reviewed dropdowns will be opened, photographed and closed with Escape. No options are selected.'
} else {
    Write-Host 'It does not click or change settings.'
}
Write-Host 'The inspection console will minimize so it cannot cover the panel.'
if ($InspectKnobHover) {
    Write-Host 'After focusing the panel, leave the mouse alone. Knobs will be hovered automatically.'
    Write-Host 'No clicks, drags, wheel events or value edits are sent. Escape stops the inspection.'
}
if ($DiscoverForScan) { Write-Host 'Leave the panel focused. Supported controls will be scanned after Linux prepares the plan.' }
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
if ($InspectKnobHover -or $DiscoverForScan) {
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
        if ($DiscoverForScan) {
            $pb = $panel.Current.BoundingRectangle
            $scoped = @($rows.ToArray() | Where-Object {
                $r = $_.window_relative_bounds
                $null -ne $r -and $r.x -ge ($pb.X - $bounds.X) -and
                $r.y -ge ($pb.Y - $bounds.Y) -and
                ($r.x + $r.width) -le ($pb.Right - $bounds.X) -and
                ($r.y + $r.height) -le ($pb.Bottom - $bounds.Y)
            })
            $inventory = @{ version = 1; panel_name = $PanelName; panel_class = $panel.Current.ClassName;
                panel_identity_status = $identityStatus; process_name = $process.ProcessName;
                panel_bounds = @{ x = $pb.X - $bounds.X; y = $pb.Y - $bounds.Y; width = $pb.Width; height = $pb.Height };
                window_size = @{ width = $bounds.Width; height = $bounds.Height }; controls = $scoped }
            $inventory | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $folder 'inventory.json')
            Write-Output $folder
            return
        }
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
        if (-not $DiscoverForScan -and $console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
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
if ($InspectMenuClasses.Count -gt 0) {
    if ($process.ProcessName -ne 'orionstudioiii' -or $InspectMenuClasses.Count -gt 4) {
        throw 'Menu inspection requires the Orion panel and at most four reviewed classes.'
    }
    $menuPanels = @($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, $PanelClass)) | Where-Object {
                -not $_.Current.IsOffscreen -and $bounds.Contains($_.Current.BoundingRectangle)
            })
    if ($menuPanels.Count -ne 1) { throw 'Menu inspection requires one exact reviewed panel.' }
    $menuRows = [System.Collections.Generic.List[object]]::new()
    try {
        foreach ($menuClass in $InspectMenuClasses) {
            if ([AfxPanelWindow]::GetForegroundWindow() -ne $handle -or $root.Current.BoundingRectangle -ne $bounds -or
                [AfxPanelWindow]::GetAsyncKeyState(27) -lt 0) { throw 'Focus/bounds changed or Escape pressed.' }
            $menus = @($menuPanels[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.PropertyCondition]::new(
                    [System.Windows.Automation.AutomationElement]::ClassNameProperty, $menuClass)) | Where-Object {
                        $_.Current.IsEnabled -and -not $_.Current.IsOffscreen -and
                        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::ComboBox -and
                        $menuPanels[0].Current.BoundingRectangle.Contains($_.Current.BoundingRectangle)
                    })
            if ($menus.Count -ne 1) { throw "Missing or ambiguous reviewed dropdown: $menuClass" }
            $menu = $menus[0]
            $valuePattern = $null; $invokePattern = $null
            if (-not $menu.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern) -or
                -not $menu.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokePattern)) {
                throw 'Dropdown lacks reviewed Value/Invoke patterns; no guessed clicks.'
            }
            $initialValue = $valuePattern.Current.Value
            $desktop = [System.Windows.Automation.AutomationElement]::RootElement
            $ownerCondition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$process.Id)
            $menuBounds = $menu.Current.BoundingRectangle
            if (@(Visible-InspectionPopups $menuBounds).Count -ne 0) {
                throw 'A native dropdown is already open; no inspection invocation sent.'
            }
            $optionCondition = [System.Windows.Automation.OrCondition]::new(
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem),
                [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::MenuItem))
            $openedOptionIds = @(); $popupIds = @(); $popupRoots = @()
            $openAttempted = $false
            try {
                $openAttempted = $true
                $invokePattern.Invoke()
                Start-Sleep -Milliseconds 700
                $foreground = [System.Windows.Automation.AutomationElement]::FromHandle([AfxPanelWindow]::GetForegroundWindow())
                if ($null -eq $foreground -or $foreground.Current.ProcessId -ne $process.Id -or
                    $root.Current.BoundingRectangle -ne $bounds -or [AfxPanelWindow]::GetAsyncKeyState(27) -lt 0) {
                    throw 'Owner focus changed while opening dropdown.'
                }
                $popupRoots = @(Visible-InspectionPopups $menuBounds)
                $popupIds = @($popupRoots | ForEach-Object { $_.GetRuntimeId() -join ':' })
                if ($popupRoots.Count -ne 1) { throw 'Expected one native-visible dropdown popup; stopped.' }
                $nodes = [System.Collections.Generic.List[object]]::new()
                $seenOptions = @{}
                $captureRect = [System.Drawing.Rectangle]::new([int]$bounds.X, [int]$bounds.Y,
                    [int][Math]::Ceiling($bounds.Width), [int][Math]::Ceiling($bounds.Height))
                foreach ($popup in $popupRoots) {
                    $pr = $popup.Current.BoundingRectangle
                    if (-not $pr.IsEmpty) {
                        $captureRect = [System.Drawing.Rectangle]::Union($captureRect,
                            [System.Drawing.Rectangle]::new([int]$pr.X, [int]$pr.Y,
                                [int][Math]::Ceiling($pr.Width), [int][Math]::Ceiling($pr.Height)))
                    }
                    $children = $popup.FindAll([System.Windows.Automation.TreeScope]::Descendants, $optionCondition)
                    foreach ($child in $children) {
                        $c = $child.Current; $r = $c.BoundingRectangle
                        $optionId = $child.GetRuntimeId() -join ':'
                        if ($c.IsPassword -or $c.IsOffscreen -or $r.IsEmpty -or $c.ProcessId -ne $process.Id -or
                            -not $pr.Contains($r) -or $seenOptions.ContainsKey($optionId) -or
                            $r.Right -le [System.Windows.Forms.SystemInformation]::VirtualScreen.Left -or
                            $r.Left -ge [System.Windows.Forms.SystemInformation]::VirtualScreen.Right -or
                            $r.Bottom -le [System.Windows.Forms.SystemInformation]::VirtualScreen.Top -or
                            $r.Top -ge [System.Windows.Forms.SystemInformation]::VirtualScreen.Bottom) { continue }
                        if ($nodes.Count -ge 512) { throw 'Visible dropdown options exceed inventory bound.' }
                        $seenOptions[$optionId] = $true
                        $nodes.Add(@{ class_name = $c.ClassName; name = $c.Name; control_type = $c.ControlType.ProgrammaticName;
                            runtime_id = $optionId; enabled = $c.IsEnabled;
                            bounds = @{ x = $r.X - $bounds.X; y = $r.Y - $bounds.Y; width = $r.Width; height = $r.Height } })
                    }
                }
                $options = @($nodes | Where-Object {
                    $_.control_type -in @('ControlType.ListItem', 'ControlType.MenuItem') -and
                    -not [string]::IsNullOrWhiteSpace($_.name)
                })
                $openedOptionIds = @($options | ForEach-Object { $_.runtime_id })
                $captureRect = [System.Drawing.Rectangle]::Intersect($captureRect, [System.Windows.Forms.SystemInformation]::VirtualScreen)
                if ($captureRect.Width -le 0 -or $captureRect.Height -le 0) { throw 'Popup screenshot bounds are empty.' }
                $menuFile = ($menuClass -replace '[^a-zA-Z0-9_-]', '_') + '-open.png'
                $bitmap = [System.Drawing.Bitmap]::new($captureRect.Width, $captureRect.Height)
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                try {
                    $graphics.CopyFromScreen($captureRect.X, $captureRect.Y, 0, 0, $bitmap.Size)
                    $bitmap.Save((Join-Path $folder $menuFile), [System.Drawing.Imaging.ImageFormat]::Png)
                } finally { $graphics.Dispose(); $bitmap.Dispose() }
                $menuRows.Add(@{ class_name = $menuClass; selected_before = $initialValue;
                    screenshot = $menuFile; popup_windows = $popupRoots.Count; opening_verified = ($options.Count -gt 0);
                    options = $options; option_visibility = 'visible options only; hidden or virtualized entries remain unknown'; controls = @($nodes.ToArray()) })
                if ($options.Count -eq 0) { throw 'No newly visible dropdown options; opening was not verified. Screenshot and tree retained.' }
            } finally {
                if ($openAttempted -and ($popupRoots.Count -gt 0 -or $openedOptionIds.Count -gt 0)) {
                    $foreground = [System.Windows.Automation.AutomationElement]::FromHandle([AfxPanelWindow]::GetForegroundWindow())
                    if ($null -ne $foreground -and $foreground.Current.ProcessId -eq $process.Id) {
                        [System.Windows.Forms.SendKeys]::SendWait('{ESC}')
                        Start-Sleep -Milliseconds 300
                    } else { throw 'Owner focus lost; Escape was not sent to another application.' }
                }
            }
            if ([AfxPanelWindow]::GetForegroundWindow() -ne $handle -or $root.Current.BoundingRectangle -ne $bounds -or
                $valuePattern.Current.Value -ne $initialValue) { throw 'Dropdown changed selection/focus; stopped without repair writes.' }
            if (@(Visible-InspectionPopups $menuBounds).Count -ne 0) { throw 'Dropdown popup remained visible after Escape.' }
            $menuRows[$menuRows.Count - 1].closure_verified = $true
            $menuRows[$menuRows.Count - 1].selected_after = $valuePattern.Current.Value
            $menuRows[$menuRows.Count - 1].selection_unchanged = $true
        }
    } finally {
        @{ version = 1; panel_name = $PanelName; panel_class = $PanelClass;
            status = 'dropdown inventory only; no options selected'; expected_count = $InspectMenuClasses.Count;
            count = $menuRows.Count; complete = ($menuRows.Count -eq $InspectMenuClasses.Count -and
                @($menuRows | Where-Object { $_.selection_unchanged -ne $true -or $_.opening_verified -ne $true -or $_.closure_verified -ne $true }).Count -eq 0); menus = @($menuRows.ToArray()) } | ConvertTo-Json -Depth 12 |
            Set-Content -Encoding UTF8 (Join-Path $folder ($label + '-menus.json'))
        if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
    }
}
Write-Host "Saved $($rows.Count) control records and $label-panel.png to $folder"
Write-Host 'Leave the results here; Linux can read them directly.'
if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
