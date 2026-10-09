# One entry point; reviewed workflow data chooses the prepared capture stage.
param([switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
if ($ValidateOnly) {
    try {
        $sources = @('Run-AfxCapture.ps1', 'Inspect-AfxPanel.ps1', 'Run-AfxScan.ps1')
        foreach ($file in $sources) {
            $tokens = $null; $parseErrors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile(
                (Join-Path $PSScriptRoot $file), [ref]$tokens, [ref]$parseErrors)
            if ($parseErrors.Count -gt 0) { throw "$file syntax: $($parseErrors.Message -join '; ')" }
            $nativeSources = @($ast.FindAll({ param($node)
                $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
                $node.Value -match 'public static class Afx(PanelWindow|ScanInput)'
            }, $true))
            foreach ($source in $nativeSources) {
                Add-Type -ReferencedAssemblies 'System.Drawing.dll' -TypeDefinition $source.Value
            }
        }
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        Add-Type -AssemblyName System.Windows.Forms
        Write-Host 'Windows preflight passed: PowerShell syntax, native helper compilation and UI Automation assemblies.'
        exit 0
    } catch {
        Write-Host ($_ | Out-String)
        exit 1
    }
}
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$log = Join-Path $results ('AFX-capture-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $log | Out-Null
$recording = $true
try {
    # A child process compiles helpers without moving the pointer and avoids
    # loading their types twice in the actual capture process.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -ValidateOnly
    if ($LASTEXITCODE -ne 0) { throw 'Windows preflight failed; no capture actions started.' }
    $name = (Read-Host 'Plugin name (for example V12 Chorus)').Trim()
    if ([string]::IsNullOrWhiteSpace($name)) { throw 'A plugin name is required.' }
    $workflows = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-capture-workflows.json') | ConvertFrom-Json
    $matches = @($workflows.plugins | Where-Object { $_.name -eq $name })
    if ($matches.Count -gt 1) { throw 'Ambiguous plugin workflow.' }
    if ($matches.Count -eq 1 -and $matches[0].next_step -eq 'complete') {
        Write-Host "${name}: all visible editable controls have been captured and reviewed. No rescan needed."
        Write-Host 'Device readback and runtime writes remain unverified. Run the launcher with the next plugin name.'
    } elseif ($matches.Count -eq 1 -and $matches[0].next_step -eq 'ranges') {
        if ([string]::IsNullOrWhiteSpace($matches[0].range_plan)) { throw 'No reviewed range plan is ready.' }
        Write-Host "${name}: automatic control batch, AFX $($workflows.channel)."
        Write-Host 'Linux recorder must be waiting. Range tests leave knobs at maximum.'
        Stop-Transcript | Out-Null
        $recording = $false
        & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -PlanId $matches[0].range_plan
    } else {
        Write-Host "Preparing the control inventory for $name."
        Write-Host "Open it on unlinked AFX $($workflows.channel)."
        if ($name -eq 'V12 Chorus') { Write-Host 'Set Space above zero so its color controls are available.' }
        Write-Host 'Focus its title bar during the ten-second delay, then leave mouse and keyboard alone.'
        Write-Host 'Knob hovers and selector metadata are saved automatically. No Linux recorder is needed for inventory.'
        $panelClass = $name
        if ($matches.Count -eq 1 -and -not [string]::IsNullOrWhiteSpace($matches[0].panel_class)) {
            $panelClass = $matches[0].panel_class
        }
        if ($matches.Count -eq 1 -and $matches[0].next_step -eq 'menus') {
            Write-Host 'Existing knob inventory retained. This pass opens and closes the two reviewed dropdowns without selecting options.'
            & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -PanelName $name -PanelClass $panelClass -InspectMenuClasses $matches[0].menu_classes
            Write-Host 'Dropdown lists saved automatically. Parameter ranges and filter choices have not been scanned yet.'
        } else {
            & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -PanelName $name -PanelClass $panelClass -InspectKnobHover
            Write-Host 'Inventory only: this plugin has no reviewed action plan yet. Its values and switches have not been scanned.'
            Write-Host 'Linux can read the saved inventory and prepare the knob/switch/selector batch.'
        }
    }
} catch {
    Write-Host 'Capture stopped:' -ForegroundColor Red
    Write-Host ($_ | Out-String)
    Write-Host $_.ScriptStackTrace
} finally {
    if ('AfxPanelWindow' -as [type]) {
        $console = [AfxPanelWindow]::GetConsoleWindow()
        if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
    }
    if ($recording) { Stop-Transcript | Out-Null }
}
