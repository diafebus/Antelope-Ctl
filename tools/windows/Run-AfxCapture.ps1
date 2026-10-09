# One entry point; reviewed workflow data chooses the prepared capture stage.
$ErrorActionPreference = 'Stop'
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$log = Join-Path $results ('AFX-capture-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $log | Out-Null
$recording = $true
try {
    $name = (Read-Host 'Plugin name (for example V12 Chorus)').Trim()
    if ([string]::IsNullOrWhiteSpace($name)) { throw 'A plugin name is required.' }
    $workflows = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-capture-workflows.json') | ConvertFrom-Json
    $matches = @($workflows.plugins | Where-Object { $_.name -eq $name })
    if ($matches.Count -gt 1) { throw 'Ambiguous plugin workflow.' }
    if ($matches.Count -eq 1 -and $matches[0].next_step -eq 'ranges') {
        if ([string]::IsNullOrWhiteSpace($matches[0].range_plan)) { throw 'No reviewed range plan is ready.' }
        Write-Host "${name}: automatic range batch, AFX $($workflows.channel)."
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
        & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -PanelName $name -InspectKnobHover
        Write-Host 'Inventory saved. Linux can read it and prepare the reviewed sweep/selector plan.'
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
