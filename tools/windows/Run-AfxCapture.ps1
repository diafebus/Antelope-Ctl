# One entry point; reviewed workflow data chooses the prepared capture stage.
param([switch]$ValidateOnly, [string]$PreflightReport = '',
      [string]$PluginName = '', [string]$CapturePlan = '', [switch]$Prepared,
      [string]$CancellationPath = '', [long]$DeadlineEpoch = 0)
$ErrorActionPreference = 'Stop'
if ($Prepared -and ($ValidateOnly -or [string]::IsNullOrWhiteSpace($PluginName) -or
    [string]::IsNullOrWhiteSpace($CapturePlan))) {
    throw 'Prepared capture requires explicit PluginName and reviewed CapturePlan; no discovery or resume.'
}
# Cache only pure tool/plan validation. Device, focus and gesture guards run afresh.
$script:AfxPreflightFiles = @('Run-AfxCapture.ps1', 'Inspect-AfxPanel.ps1', 'Run-AfxScan.ps1',
    'afx-scan-plans.json', 'afx-capture-workflows.json', 'afx-dropdown-options.json')
function Get-AfxKitHashes([string]$Root = $PSScriptRoot) {
    $hashes = @{}
    foreach ($file in $script:AfxPreflightFiles) {
        $hashes[$file] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $file)).Hash
    }
    return $hashes
}
function Get-AfxPreflightContext {
    return ([ordered]@{
        powershell = $PSVersionTable.PSVersion.ToString()
        clr = [Environment]::Version.ToString()
        os = [Environment]::OSVersion.VersionString
        process_64bit = [Environment]::Is64BitProcess
    } | ConvertTo-Json -Compress)
}
function Test-AfxKitHashes($Expected, [hashtable]$Current) {
    if ($null -eq $Expected -or $Current.Count -ne $script:AfxPreflightFiles.Count) { return $false }
    $keys = @($Expected.PSObject.Properties.Name)
    if ($keys.Count -ne $script:AfxPreflightFiles.Count) { return $false }
    foreach ($file in $script:AfxPreflightFiles) {
        if (-not $Current.ContainsKey($file) -or $keys -cnotcontains $file) { return $false }
        $hash = $Expected.$file
        if ($hash -isnot [string] -or $hash -cnotmatch '^[A-F0-9]{64}$' -or $hash -cne $Current[$file]) {
            return $false
        }
    }
    return $true
}
function Test-AfxPreflightCache([string]$Path, [hashtable]$Hashes, [string]$Context) {
    try {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
        $report = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
        if (-not ($report.cache_schema -is [int] -or $report.cache_schema -is [long]) -or
            $report.cache_schema -ne 1 -or $report.status -isnot [string] -or $report.status -cne 'ok' -or $report.validation_complete -isnot [bool] -or
            -not $report.validation_complete -or $report.settings_written -isnot [bool] -or
            $report.settings_written -or $report.validation_context -isnot [string] -or
            $report.validation_context -cne $Context -or
            $report.drag_axis_checks -isnot [string] -or
            $report.control_bounds_checks -isnot [string] -or
            $report.drag_axis_checks -cne 'metadata, direction and native geometry passed' -or
            $report.control_bounds_checks -cne 'fixed anchor and metadata passed') { return $false }
        return (Test-AfxKitHashes $report.hashes $Hashes)
    } catch {
        return $false
    }
}
function Write-AfxPreflightReport([string]$Path, $Report) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $directory = [System.IO.Path]::GetDirectoryName($full)
    [void][System.IO.Directory]::CreateDirectory($directory)
    $temporary = $full + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [System.IO.File]::WriteAllText($temporary, ($Report | ConvertTo-Json -Depth 20),
            [System.Text.UTF8Encoding]::new($false))
        # Same-directory replacement publishes a complete file; never truncate a live cache.
        if ([System.IO.File]::Exists($full)) {
            # PowerShell 5 binds $null to an empty string for this overload;
            # NullString passes the actual null backup filename to .NET.
            [System.IO.File]::Replace($temporary, $full, [NullString]::Value)
        } else {
            [System.IO.File]::Move($temporary, $full)
        }
    } finally {
        if ([System.IO.File]::Exists($temporary)) { [System.IO.File]::Delete($temporary) }
    }
}
if ($ValidateOnly) {
    try {
        $initialHashes = Get-AfxKitHashes
        $context = Get-AfxPreflightContext
        foreach ($file in @('afx-scan-plans.json', 'afx-capture-workflows.json', 'afx-dropdown-options.json')) {
            $data = Get-Content -Raw (Join-Path $PSScriptRoot $file) | ConvertFrom-Json
            if ($data.version -ne 1) { throw "$file has an unsupported version." }
        }
        $sources = @('Run-AfxCapture.ps1', 'Inspect-AfxPanel.ps1', 'Run-AfxScan.ps1')
        # Optional queue scripts are parsed during explicit validation when deployed.
        # Their execution fingerprints belong to the reviewed batch manifest.
        foreach ($optional in @('Run-AfxSessionBridge.ps1', 'Invoke-AfxCaptureStage.ps1')) {
            if (Test-Path -LiteralPath (Join-Path $PSScriptRoot $optional)) { $sources += $optional }
        }
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
        [AfxScanInput]::ValidateCancellationGuards()
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
        $hashes = Get-AfxKitHashes
        $initialObject = $initialHashes | ConvertTo-Json | ConvertFrom-Json
        if (-not (Test-AfxKitHashes $initialObject $hashes)) {
            throw 'Capture kit changed during preflight; no result may be reused.'
        }
        if (-not [string]::IsNullOrWhiteSpace($PreflightReport)) {
            Write-AfxPreflightReport $PreflightReport @{
                cache_schema = 1; status = 'ok'; validation_complete = $true;
                validation_context = $context; checked_utc = [DateTime]::UtcNow.ToString('o'); hashes = $hashes;
                checked_plans = $checkedPlans; drag_axis_checks = 'metadata, direction and native geometry passed';
                control_bounds_checks = 'fixed anchor and metadata passed'; settings_written = $false
            }
        }
        Write-Host 'Windows preflight passed: PowerShell syntax, native helper compilation and UI Automation assemblies.'
        exit 0
    } catch {
        if (-not [string]::IsNullOrWhiteSpace($PreflightReport)) {
            Write-AfxPreflightReport $PreflightReport @{
                cache_schema = 1; status = 'failed'; validation_complete = $false;
                error = $_.Exception.Message; settings_written = $false
            }
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
    $cache = Join-Path $results 'preflight-cache.json'
    $currentHashes = Get-AfxKitHashes
    $context = Get-AfxPreflightContext
    if (Test-AfxPreflightCache $cache $currentHashes $context) {
        Write-Host 'Tool/plan preflight cache matched; current device and GUI guards still apply.'
    } else {
        # Compile only on cache miss, in a child process so native helper types stay isolated.
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -ValidateOnly -PreflightReport $cache
        if ($LASTEXITCODE -ne 0 -or
            -not (Test-AfxPreflightCache $cache (Get-AfxKitHashes) (Get-AfxPreflightContext))) {
            throw 'Windows preflight failed or kit changed; no capture actions started.'
        }
    }
    $name = $PluginName.Trim()
    if ([string]::IsNullOrWhiteSpace($name)) {
        $name = ([string](Read-Host 'Plugin name (for example V12 Chorus), or resume scan-JOB')).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($name)) { throw 'A plugin name is required.' }
    if ($name -match '^resume\s+(scan-[A-Za-z0-9_-]+)$') {
        if ($Prepared) { throw 'Prepared capture cannot resume a previous job.' }
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
    } elseif ($matches.Count -eq 1 -and $matches[0].next_step -eq 'review') {
        Write-Host "${name}: existing capture evidence needs review. No automatic rescan."
        if ($matches[0].review_reason) { Write-Host $matches[0].review_reason }
        Write-Host 'Inspect the saved evidence and prepare the remaining directed trial before continuing.'
    } elseif ($matches.Count -eq 1 -and $matches[0].next_step -eq 'ranges') {
        if ([string]::IsNullOrWhiteSpace($matches[0].range_plan)) { throw 'No reviewed range plan is ready.' }
        Write-Host "${name}: automatic control batch, AFX $($workflows.channel)."
        Write-Host 'Linux recorder must be waiting. The next screen lists this batch and its coverage.'
        Stop-Transcript | Out-Null
        $recording = $false
        & (Join-Path $PSScriptRoot 'Run-AfxScan.ps1') -PlanId $matches[0].range_plan -Prepared:$Prepared -CancellationPath $CancellationPath -DeadlineEpoch $DeadlineEpoch
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
