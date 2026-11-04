# Reusable range/selector-plan adapter. Setup and verified cleanup are separate reviewed stages.
param([Parameter(Mandatory=$true)][string]$InputPath,
      [Parameter(Mandatory=$true)][string]$ReceiptPath,
      [Parameter(Mandatory=$true)][string]$CommandId,
      [Parameter(Mandatory=$true)][string]$Generation,
      [Parameter(Mandatory=$true)][string]$EffectId,
      [Parameter(Mandatory=$true)][string]$Phase,
      [Parameter(Mandatory=$true)][string]$CancellationPath,
      [Parameter(Mandatory=$true)][long]$DeadlineEpoch)
$ErrorActionPreference='Stop'
if($Phase -cne 'capture'){throw 'This adapter handles capture plans only'}
$c=Get-Content -Raw -LiteralPath $InputPath|ConvertFrom-Json
if($c.effect_id -cne $EffectId -or $c.plan_id -notmatch '^[a-z0-9_-]+$' -or
   [string]::IsNullOrWhiteSpace($c.plugin_name)){throw 'Explicit reviewed effect and plan required'}
$kit=[System.IO.Path]::GetFullPath($c.kit_path)
$files=@('Run-AfxCapture.ps1','Inspect-AfxPanel.ps1','Run-AfxScan.ps1',
         'afx-scan-plans.json','afx-capture-workflows.json','afx-dropdown-options.json')
foreach($name in $files){
    $expected=$c.kit_sha256.PSObject.Properties[$name]
    if($null -eq $expected -or
       (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $kit $name)).Hash.ToLowerInvariant() -cne ([string]$expected.Value).ToLowerInvariant()){
        throw 'Kit changed since stage review; prepare fresh hashes'
    }
}
$plans=(Get-Content -Raw (Join-Path $kit 'afx-scan-plans.json')|ConvertFrom-Json).plans
$plan=@($plans|Where-Object {$_.id -ceq $c.plan_id -and $_.effect_id -ceq $EffectId})
if($plan.Count -ne 1){throw 'Reviewed plan identity changed'}
$results=Join-Path $kit 'results'
$before=@(Get-ChildItem -LiteralPath $results -Directory -Filter 'scan-*'|ForEach-Object {$_.Name})
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kit 'Run-AfxCapture.ps1') `
    -PluginName $c.plugin_name -CapturePlan $c.plan_id -Prepared -CancellationPath $CancellationPath -DeadlineEpoch $DeadlineEpoch
if($LASTEXITCODE -ne 0){throw 'Capture stopped; inspect job evidence without replay'}
$jobs=@(Get-ChildItem -LiteralPath $results -Directory -Filter 'scan-*'|Where-Object {$_.Name -notin $before})
if($jobs.Count -ne 1){throw 'New capture job absent or ambiguous'}
$job=$jobs[0].FullName
$until=[DateTime]::UtcNow.AddSeconds(30)
while(-not (Test-Path (Join-Path $job 'host-completed.json')) -and [DateTime]::UtcNow -lt $until){
    if(Test-Path (Join-Path $job 'host-error.json')){throw 'Host rejected evidence'}
    if((Test-Path -LiteralPath $CancellationPath) -or [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $DeadlineEpoch){throw 'Capture cancelled'}
    Start-Sleep -Milliseconds 200
}
$executed=Get-Content -Raw (Join-Path $job 'host-plan.json')|ConvertFrom-Json
if($executed.id -cne $plan[0].id -or $executed.effect_id -cne $EffectId -or
   $executed.channel -ne $plan[0].channel -or
   (($executed.controls|ConvertTo-Json -Depth 16 -Compress) -cne ($plan[0].controls|ConvertTo-Json -Depth 16 -Compress))){
    throw 'Executed capture plan differs from reviewed plan'
}
$progress=Get-Content -Raw (Join-Path $job 'progress.json')|ConvertFrom-Json
$hostResult=Get-Content -Raw (Join-Path $job 'host-completed.json')|ConvertFrom-Json
$guestResult=Get-Content -Raw (Join-Path $job 'completed.json')|ConvertFrom-Json
if($progress.status -cne 'completed' -or -not $progress.completed -or
   $progress.accepted_count -ne $progress.total_actions -or
   $hostResult.status -cne 'ok' -or $guestResult.status -cne 'ok'){
    throw 'Host and guest completion did not agree'
}
$session=Split-Path -Parent $ReceiptPath
$evidence=@()
foreach($name in @('host-plan.json','progress.json','host-completed.json','completed.json','action-windows.json')){
    $copy=$CommandId+'-'+$name
    Copy-Item -LiteralPath (Join-Path $job $name) -Destination (Join-Path $session $copy)
    $evidence+=@{file=$copy;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $session $copy)).Hash.ToLowerInvariant()}
}
$receipt=@{status='verified';continuation_safe=$true;command_id=$CommandId;generation=$Generation;
    effect_id=$EffectId;phase=$Phase;evidence=$evidence;capture_jobs=@($jobs[0].Name);
    device_readback_verified=$false;coverage=$hostResult.coverage}
$temporary=$ReceiptPath+'.tmp-'+[Guid]::NewGuid().ToString('N')
[System.IO.File]::WriteAllText($temporary,($receipt|ConvertTo-Json -Depth 16))
Move-Item -LiteralPath $temporary -Destination $ReceiptPath
