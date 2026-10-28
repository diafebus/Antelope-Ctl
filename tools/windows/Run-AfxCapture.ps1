# One entry point; reviewed workflow data chooses the prepared capture stage.
param([switch]$ValidateOnly, [string]$PreflightReport = '',
      [string]$PluginName = '', [string]$CapturePlan = '')
$ErrorActionPreference = 'Stop'
if ($ValidateOnly) {
    try {
        foreach ($file in @('afx-scan-plans.json', 'afx-capture-workflows.json', 'afx-dropdown-options.json')) {
            $data = Get-Content -Raw (Join-Path $PSScriptRoot $file) | ConvertFrom-Json
            if ($data.version -ne 1) { throw "$file has an unsupported version." }
        }
        $sources = @('Run-AfxCapture.ps1', 'Inspect-AfxPanel.ps1', 'Run-AfxScan.ps1')
        $scanAst = $null
        foreach ($file in $sources) {
            $tokens = $null; $parseErrors = $null
            $ast = [System.Management.Automation.Language.Parser]::ParseFile(
                (Join-Path $PSScriptRoot $file), [ref]$tokens, [ref]$parseErrors)
            if ($parseErrors.Count -gt 0) { throw "$file syntax: $($parseErrors.Message -join '; ')" }
            if ($file -ceq 'Run-AfxScan.ps1') { $scanAst = $ast }
            $nativeSources = @($ast.FindAll({ param($node)
                $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
                $node.Value -match 'public static class Afx(PanelWindow|ScanInput)'
            }, $true))
            foreach ($source in $nativeSources) {
                Add-Type -ReferencedAssemblies 'System.Drawing.dll' -TypeDefinition $source.Value
            }
        }
        [AfxScanInput]::ValidateDropdownClassifier()
        [AfxScanInput]::ValidateKnobPoints()
        [AfxScanInput]::ValidateSweepAxes()
        [AfxScanInput]::ValidateControlBounds()
        # Define only these pure metadata helpers, without running the scan script.
        $axisFunctions = @($scanAst.FindAll({ param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -cin @('Get-PlanDragAxis','Get-PlanSweepDelta','Get-PlanBoundsShiftX')
        }, $true))
        if ($axisFunctions.Count -ne 3) { throw 'Missing drag-axis metadata guards.' }
        foreach ($function in $axisFunctions) { . ([scriptblock]::Create($function.Extent.Text)) }
        $vertical = [pscustomobject]@{kind='knob_range';drag_axis='vertical'}
        $horizontal = [pscustomobject]@{kind='knob_range';drag_axis='horizontal'}
        if ((Get-PlanDragAxis ([pscustomobject]@{kind='knob_range'})) -cne 'vertical' -or
            (Get-PlanDragAxis $horizontal) -cne 'horizontal' -or
            (Get-PlanSweepDelta $vertical 800) -ne 800 -or
            (Get-PlanSweepDelta $vertical -800) -ne -800 -or
            (Get-PlanSweepDelta $horizontal 800) -ne -800 -or
            (Get-PlanSweepDelta $horizontal -800) -ne 800) { throw 'Drag-axis direction fixtures failed.' }
        $badAxes = @(
            [pscustomobject]@{kind='knob_range';drag_axis=$null},
            [pscustomobject]@{kind='knob_range';drag_axis=$true},
            [pscustomobject]@{kind='knob_range';drag_axis=1},
            [pscustomobject]@{kind='knob_range';drag_axis='Horizontal'},
            [pscustomobject]@{kind='knob_range';drag_axis=[object[]]@('horizontal')},
            [pscustomobject]@{kind='binary_button';drag_axis='vertical'}
        )
        foreach ($bad in $badAxes) {
            $rejected = $false
            try { $null = Get-PlanDragAxis $bad } catch { $rejected = $true }
            if (-not $rejected) { throw 'Unsafe drag-axis metadata accepted.' }
        }
        foreach ($allowed in @(0,1)) {
            $definition = [pscustomobject]@{kind='knob_range';drag_axis='horizontal';bounds_shift_x_px=$allowed}
            if ((Get-PlanBoundsShiftX $definition) -ne $allowed) { throw 'Bounds allowance fixture failed.' }
        }
        if ((Get-PlanBoundsShiftX $horizontal) -ne 0) { throw 'Default control bounds must remain exact.' }
        $badShifts = @(
            [pscustomobject]@{kind='knob_range';drag_axis='horizontal';bounds_shift_x_px=$null},
            [pscustomobject]@{kind='knob_range';drag_axis='horizontal';bounds_shift_x_px=$true},
            [pscustomobject]@{kind='knob_range';drag_axis='horizontal';bounds_shift_x_px=2},
            [pscustomobject]@{kind='knob_range';drag_axis='horizontal';bounds_shift_x_px=-1},
            [pscustomobject]@{kind='knob_range';drag_axis='vertical';bounds_shift_x_px=1},
            [pscustomobject]@{kind='binary_button';drag_axis='horizontal';bounds_shift_x_px=1}
        )
        foreach ($bad in $badShifts) {
            $rejected = $false
            try { $null = Get-PlanBoundsShiftX $bad } catch { $rejected = $true }
            if (-not $rejected) { throw 'Unsafe control bounds allowance accepted.' }
        }
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        Add-Type -AssemblyName System.Windows.Forms
        $reviewedPlans = (Get-Content -Raw (Join-Path $PSScriptRoot 'afx-scan-plans.json') | ConvertFrom-Json).plans
        $checkedPlans = @()
        foreach ($candidate in $reviewedPlans) {
            $loaded = & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -PlanId $candidate.id -ValidatePlanOnly | ConvertFrom-Json
            if ($loaded.id -cne $candidate.id -or @($loaded.controls).Count -ne @($candidate.controls).Count) {
                throw "Plan metadata failed to load: $($candidate.id)"
            }
            $checkedPlans += $loaded
        }
        if (-not [string]::IsNullOrWhiteSpace($PreflightReport)) {
            $hashes = @{}
            foreach ($file in $sources + @('afx-scan-plans.json', 'afx-capture-workflows.json', 'afx-dropdown-options.json')) {
                $hashes[$file] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $file)).Hash
            }
            @{ status = 'ok'; checked_utc = [DateTime]::UtcNow.ToString('o'); hashes = $hashes;
                checked_plans = $checkedPlans; drag_axis_checks = 'metadata, direction and native geometry passed';
                control_bounds_checks = 'fixed anchor and metadata passed'; settings_written = $false } |
                ConvertTo-Json -Depth 16 | Set-Content -Encoding UTF8 $PreflightReport
        }
        Write-Host 'Windows preflight passed: PowerShell syntax, native helper compilation and UI Automation assemblies.'
        exit 0
    } catch {
        if (-not [string]::IsNullOrWhiteSpace($PreflightReport)) {
            @{ status = 'failed'; error = $_.Exception.Message; settings_written = $false } |
                ConvertTo-Json | Set-Content -Encoding UTF8 $PreflightReport
        }
        Write-Host ($_ | Out-String)
        exit 1
    }
}
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$log = Join-Path $results ('AFX-capture-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $log | Out-Null
$recording = $true
$exitCode = 0
try {
    # A child process compiles helpers without moving the pointer and avoids
    # loading their types twice in the actual capture process.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -ValidateOnly
    if ($LASTEXITCODE -ne 0) { throw 'Windows preflight failed; no capture actions started.' }
    $name = $PluginName.Trim()
    if ([string]::IsNullOrWhiteSpace($name)) {
        $name = ([string](Read-Host 'Plugin name (for example V12 Chorus), or resume scan-JOB')).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($name)) { throw 'A plugin name is required.' }
    if ($name -match '^resume\s+(scan-[A-Za-z0-9_-]+)$') {
        if (-not [string]::IsNullOrWhiteSpace($CapturePlan)) { throw 'Resume cannot combine with CapturePlan.' }
        $resumeDirectory = Join-Path $results $Matches[1]
        $remainingFile = Join-Path $resumeDirectory 'remaining-plan.json'
        if (-not (Test-Path -LiteralPath $remainingFile)) {
            throw 'Ask the Linux coordinator to --prepare-resume this job first. No gestures sent.'
        }
        $remaining = Get-Content -Raw -LiteralPath $remainingFile | ConvertFrom-Json
        Write-Host "Resume $($remaining.panel): $(@($remaining.controls).Count) remaining control(s)."
        Write-Host 'Completed controls will be skipped. Interrupted controls start a new full trial from current state.'
        Write-Host 'Review the saved failure and current plugin/effect instance, unlinked AFX channel and control state.'
        Write-Host 'No old baseline will be restored. Knob trials intentionally leave knobs at maximum.'
        if ((Read-Host 'Type REVIEWED after reconciling current state, or Enter to cancel') -cne 'REVIEWED') {
            throw 'Resume cancelled; no gestures sent.'
        }
        Stop-Transcript | Out-Null
        $recording = $false
        & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -ResumeDirectory $resumeDirectory -ResumeReviewed
        exit $LASTEXITCODE
    }
    $dropdownData = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-dropdown-options.json') | ConvertFrom-Json
    $lookup = ($name.ToLowerInvariant() -replace '[^a-z0-9]', '')
    $definitions = @($dropdownData.plugins | Where-Object {
        $keys = @($_.effect_id, $_.name) + @($_.aliases)
        @($keys | Where-Object { ($_.ToLowerInvariant() -replace '[^a-z0-9]', '') -ceq $lookup }).Count -gt 0
    })
    if ($definitions.Count -gt 1) { throw 'Plugin name is ambiguous in the dropdown registry.' }
    if ($definitions.Count -eq 1) {
        if ($definitions[0].hardware_testing -eq 'excluded') { throw 'This plugin is excluded from capture.' }
        $name = $definitions[0].name
        foreach ($dropdown in $definitions[0].dropdowns) {
            $labels = @($dropdown.options | ForEach-Object { $_.label })
            if ($labels.Count -gt 0) { Write-Host "$($dropdown.label): $($labels -join ', ') [$($dropdown.status)]" }
        }
        foreach ($gap in $definitions[0].unresolved) { Write-Host "Pending dropdown evidence: $gap" }
    }
    $workflows = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-capture-workflows.json') | ConvertFrom-Json
    $canonical = ($name.ToLowerInvariant() -replace '[^a-z0-9]', '')
    $matches = @($workflows.plugins | Where-Object { ($_.name.ToLowerInvariant() -replace '[^a-z0-9]', '') -ceq $canonical })
    if ($matches.Count -gt 1) { throw 'Ambiguous plugin workflow.' }
    if (-not [string]::IsNullOrWhiteSpace($CapturePlan)) {
        $plans = (Get-Content -Raw (Join-Path $PSScriptRoot 'afx-scan-plans.json') | ConvertFrom-Json).plans
        $selectedPlans = @($plans | Where-Object { $_.id -ceq $CapturePlan })
        if ($matches.Count -ne 1 -or $selectedPlans.Count -ne 1 -or
            $selectedPlans[0].effect_id -cne $matches[0].effect_id -or
            $selectedPlans[0].channel -ne $workflows.channel) {
            throw 'CapturePlan must identify one reviewed plan for this plugin and channel. No gestures sent.'
        }
        $matches[0].next_step = 'ranges'
        $matches[0] | Add-Member -NotePropertyName range_plan -NotePropertyValue $CapturePlan -Force
    }
    if ($matches.Count -eq 1 -and $matches[0].next_step -eq 'complete') {
        Write-Host "${name}: prepared GUI capture work is complete. No rescan needed."
        if ($matches[0].completion_limits) { Write-Host $matches[0].completion_limits }
        Write-Host 'Device readback and runtime writes remain unverified. Run the launcher with the next plugin name.'
    } elseif ($matches.Count -eq 1 -and $matches[0].next_step -eq 'ranges') {
        if ([string]::IsNullOrWhiteSpace($matches[0].range_plan)) { throw 'No reviewed range plan is ready.' }
        Write-Host "${name}: automatic control batch, AFX $($workflows.channel)."
        Write-Host 'Linux recorder must be waiting. The next screen lists this batch and its coverage.'
        Stop-Transcript | Out-Null
        $recording = $false
        & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -PlanId $matches[0].range_plan
        $exitCode = $LASTEXITCODE
    } else {
        Write-Host "Preparing the control inventory for $name."
        Write-Host "Open it on unlinked AFX $($workflows.channel)."
        if ($name -eq 'V12 Chorus') { Write-Host 'Set Space above zero so its color controls are available.' }
        Write-Host 'Focus its title bar during the ten-second delay, then leave mouse and keyboard alone.'
        Write-Host 'Controls and screenshots are saved automatically. Automatic discovery needs the Linux recorder waiting.'
        $panelClass = $name
        if ($matches.Count -eq 1 -and -not [string]::IsNullOrWhiteSpace($matches[0].panel_class)) {
            $panelClass = $matches[0].panel_class
        }
        if ($matches.Count -eq 1 -and $matches[0].next_step -eq 'menus') {
            Write-Host 'Existing knob inventory retained. This pass opens and closes the two reviewed dropdowns without selecting options.'
            & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -PanelName $name -PanelClass $panelClass -InspectMenuClasses $matches[0].menu_classes
            Write-Host 'Dropdown lists saved automatically. Parameter ranges and filter choices have not been scanned yet.'
        } else {
            Write-Host 'The Linux recorder prepares supported knob actions from the inventory automatically.'
            $directory = & (Join-Path $PSScriptRoot 'Inspect-AfxPanel.ps1') -PanelName $name -PanelClass $panelClass -DiscoverForScan
            if (@($directory).Count -ne 1 -or -not (Test-Path (Join-Path $directory 'inventory.json'))) {
                throw 'No scoped discovery inventory was saved.'
            }
            # Publish only after the complete inventory exists.
            @{ version = 1 } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $directory 'discovery-request.json')
            $deadline = [DateTime]::UtcNow.AddSeconds(30)
            while (-not (Test-Path (Join-Path $directory 'generated-plan.json'))) {
                if (Test-Path (Join-Path $directory 'host-error.json')) {
                    throw (Get-Content -Raw (Join-Path $directory 'host-error.json'))
                }
                if ([DateTime]::UtcNow -ge $deadline) { throw 'Linux recorder did not prepare a plan. Inventory retained; no settings changed.' }
                Start-Sleep -Milliseconds 200
            }
            Stop-Transcript | Out-Null
            $recording = $false
            & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -DiscoveryDirectory $directory -Prepared
            $exitCode = $LASTEXITCODE
        }
    }
} catch {
    $exitCode = 1
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
exit $exitCode
