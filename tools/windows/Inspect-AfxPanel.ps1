# Read only the focused vendor panel; output stays beside this script.
[CmdletBinding()]
param(
    [ValidateRange(3, 60)][int]$DelaySeconds = 10,
    [string]$PanelName = ''
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PanelName)) {
    $PanelName = Read-Host 'Name of the plugin/panel to inspect (for example Instinct)'
}
$PanelName = $PanelName.Trim()
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
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@

[void][AfxPanelWindow]::SetProcessDPIAware()
Write-Host "Focus the $PanelName panel within $DelaySeconds seconds."
Write-Host 'This reads controls and saves a screenshot. It does not click or change settings.'
Write-Host 'The inspection console will minimize so it cannot cover the panel.'
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
$result = [ordered]@{ version = 2; panel_name = $PanelName; created_utc = [DateTime]::UtcNow.ToString('o');
    device_writes = $false; source = 'Windows UI Automation; not device readback';
    window_title = $root.Current.Name; process_name = $process.ProcessName;
    window_size = @{ width = $bounds.Width; height = $bounds.Height };
    controls = @($rows.ToArray()) }
$result | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $folder ($label + '-controls.json'))
Write-Host "Saved $($rows.Count) control records and $label-panel.png to $folder"
Write-Host 'Leave the results here; Linux can read them directly.'
if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
