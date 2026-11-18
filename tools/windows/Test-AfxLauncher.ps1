# Exercise the real launcher and exit codes without operating plugin controls.
param([string]$Report = '')
$ErrorActionPreference = 'Stop'
$workflow = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-capture-workflows.json') | ConvertFrom-Json
$registry = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-dropdown-options.json') | ConvertFrom-Json
$completed = @($workflow.plugins | Where-Object { $_.effect_id -eq 'bbdchorus' })
$excluded = @($registry.plugins | Where-Object { $_.effect_id -eq 'antares_autotune' })
if ($completed.Count -ne 1 -or $completed[0].next_step -ne 'complete' -or
    $excluded.Count -ne 1 -or $excluded[0].hardware_testing -ne 'excluded') {
    throw 'No-gesture test prerequisites changed. No launcher was executed.'
}
$missingJob = 'scan-launcher-test-' + [Guid]::NewGuid().ToString('N')
$cases = @(
    @{ name = 'completed'; args = '-PluginName "BBD Chorus"'; input = ''; code = 0; text = 'No rescan needed' },
    @{ name = 'excluded'; args = '-PluginName "Auto-Tune"'; input = ''; code = 1; text = 'excluded from capture' },
    @{ name = 'wrong-effect-plan'; args = '-PluginName "BBD Chorus" -CapturePlan deesser-filter-keys'; input = ''; code = 1; text = 'reviewed plan for this plugin' },
    @{ name = 'unknown-plan'; args = '-PluginName "BBD Chorus" -CapturePlan nonexistent-plan'; input = ''; code = 1; text = 'reviewed plan for this plugin' },
    @{ name = 'blank-name'; args = ''; input = ''; code = 1; text = 'plugin name is required' },
    @{ name = 'missing-resume'; args = '-PluginName "resume ' + $missingJob + '"'; input = ''; code = 1; text = 'prepare-resume' }
)
$results = @()
foreach ($case in $cases) {
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'cmd.exe'
    $launcher = Join-Path $PSScriptRoot 'Run-AfxCapture.cmd'
    $start.Arguments = '/d /s /c ""' + $launcher + '" ' + $case.args + '"'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($start)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.WriteLine($case.input)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) {
            $process.Kill()
            throw "Launcher test timed out: $($case.name)"
        }
        $output = $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne $case.code -or $output -notmatch $case.text) {
            throw "Launcher test failed: $($case.name), exit $($process.ExitCode).`n$output"
        }
        $results += @{ name = $case.name; exit_code = $process.ExitCode; status = 'ok' }
        Write-Host "Launcher check passed: $($case.name)"
    } finally { $process.Dispose() }
}
if (-not [string]::IsNullOrWhiteSpace($Report)) {
    @{ status = 'ok'; settings_written = $false; tests = $results } |
        ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $Report
}
