# Read only the focused vendor panel; output stays beside this script.
[CmdletBinding()]
param([ValidateRange(3, 60)][int]$DelaySeconds = 10)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AfxPanelWindow {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@

Write-Host "Focus the Instinct plugin panel within $DelaySeconds seconds."
Write-Host 'This reads controls and saves a screenshot. It does not click or change settings.'
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
$folder = Join-Path $PSScriptRoot ('results\panel-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $folder -ErrorAction Stop | Out-Null
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
$rows = [System.Collections.Generic.List[object]]::new()
foreach ($element in $elements) {
    try {
        $current = $element.Current
        if ($current.IsPassword) { continue }
        $rect = $current.BoundingRectangle
        $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
        $values = [ordered]@{}
        foreach ($name in @('Value', 'RangeValue', 'Toggle', 'SelectionItem', 'ExpandCollapse')) {
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
$result = [ordered]@{ version = 1; created_utc = [DateTime]::UtcNow.ToString('o');
    device_writes = $false; source = 'Windows UI Automation; not device readback';
    window_title = $root.Current.Name; process_name = $process.ProcessName;
    window_size = @{ width = $bounds.Width; height = $bounds.Height };
    controls = @($rows.ToArray()) }
$result | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $folder 'controls.json')
$bitmap = New-Object System.Drawing.Bitmap ([int][Math]::Ceiling($bounds.Width)), ([int][Math]::Ceiling($bounds.Height))
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen([int]$bounds.X, [int]$bounds.Y, 0, 0, $bitmap.Size)
    $bitmap.Save((Join-Path $folder 'panel.png'), [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
Write-Host "Saved $($rows.Count) control records and panel.png to $folder"
Write-Host 'Leave the results here; Linux can read them directly.'
