# Log startup separately so syntax/assembly failures in the inspector are visible.
$ErrorActionPreference = 'Stop'
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$log = Join-Path $results ('AFX-knob-inspection-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $log | Out-Null
try {
    Write-Host 'Automatic knob inspection started.'
    Write-Host "Launch log: $log"
    & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -InspectKnobHover
    Write-Host 'Inspection complete. Linux can read the saved results.'
} catch {
    Write-Host 'Inspection stopped:' -ForegroundColor Red
    Write-Host ($_ | Out-String)
    Write-Host $_.ScriptStackTrace
    Write-Host "Details saved to $log"
} finally {
    # The inspector may have minimized the console before an early failure.
    if ('AfxPanelWindow' -as [type]) {
        $console = [AfxPanelWindow]::GetConsoleWindow()
        if ($console -ne [IntPtr]::Zero) { [void][AfxPanelWindow]::ShowWindow($console, 9) }
    }
    Stop-Transcript | Out-Null
}
