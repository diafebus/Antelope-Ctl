# Fresh-session bridge for reviewed batch stages. Does not open HID or move the pointer.
param([Parameter(Mandatory=$true)][string]$SessionDirectory,
      [ValidateRange(1,480)][int]$LeaseMinutes = 120)
$ErrorActionPreference = 'Stop'
$session = [System.IO.Path]::GetFullPath($SessionDirectory)
New-Item -ItemType Directory -Force -Path $session | Out-Null
$guiMutex=[System.Threading.Mutex]::new($false,'Local\AntelopeAfxCaptureBridge')
$ownsGui=$false
try {$ownsGui=$guiMutex.WaitOne(0)} catch [System.Threading.AbandonedMutexException] {$ownsGui=$true}
if(-not $ownsGui){$guiMutex.Dispose();throw 'Another capture bridge owns this desktop'}
$leaseLock=$null
$activeChild=$null
function Write-AtomicJson($Path,$Value) {
    $temporary=$Path+'.tmp-'+[Guid]::NewGuid().ToString('N')
    [System.IO.File]::WriteAllText($temporary,($Value|ConvertTo-Json -Depth 16))
    Move-Item -LiteralPath $temporary -Destination $Path
}
function Session-File([string]$Name) {
    if($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$'){throw 'Session file must be a basename'}
    $path=Join-Path $session $Name
    $item=Get-Item -LiteralPath $path -ErrorAction Stop
    if($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)){
        throw 'Session file missing or redirected'
    }
    return $path
}
try {
    $leaseLock=[System.IO.File]::Open((Join-Path $session '.bridge.lock'),
        [System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
    $old=@(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'"|Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match '(Session-Bridge|Run-AfxCapture|Run-AfxScan|Invoke-AfxCaptureStage)[.]ps1|[-]CommandId\s+'
    })
    if($old.Count -gt 0){throw 'Existing GUI capture worker found; reconcile it before starting another bridge'}
    # A stopped or crashed bridge must never pick up its predecessor's queue.
    if((Test-Path (Join-Path $session 'bridge-identity.json')) -or
       @(Get-ChildItem -LiteralPath $session -Filter 'command-*.json').Count -gt 0){
        throw 'Use a fresh session directory; old commands must not be replayed'
    }
    $generation=[Guid]::NewGuid().ToString('N')
    $deadline=[DateTimeOffset]::UtcNow.AddMinutes($LeaseMinutes)
    Write-AtomicJson (Join-Path $session 'bridge-identity.json') @{
        version=1;generation=$generation;expires_epoch=$deadline.ToUnixTimeSeconds();pid=$PID
    }
    $stopping=$false
    while(-not $stopping -and [DateTimeOffset]::UtcNow -lt $deadline){
        foreach($file in @(Get-ChildItem -LiteralPath $session -Filter 'command-*.json'|Sort-Object Name)){
            $id=$file.BaseName.Substring(8)
            $result=Join-Path $session ('result-'+$id+'.json')
            if(Test-Path -LiteralPath $result){continue}
            $reply=@{status='failed';command_id=$id;generation=$generation}
            try {
                if($id -notmatch '^[a-f0-9]{32}$'){throw 'Invalid command identity'}
                $q=Get-Content -Raw -LiteralPath (Session-File $file.Name)|ConvertFrom-Json
                if($q.generation -cne $generation){throw 'Stale session generation'}
                if([DateTimeOffset]::UtcNow -ge $deadline){throw 'Bridge lease expired'}
                switch($q.action){
                    'hello' {$reply.status='ok'}
                    'stop' {$reply.status='ok';$stopping=$true}
                    'script' {
                        $script=Session-File $q.file
                        $inputFile=Session-File $q.input
                        if([System.IO.Path]::GetExtension($script) -ine '.ps1' -or
                           [System.IO.Path]::GetExtension($inputFile) -ine '.json'){
                            throw 'A stage needs PowerShell and JSON files'
                        }
                        if((Get-FileHash -Algorithm SHA256 -LiteralPath $script).Hash.ToLowerInvariant() -cne $q.script_sha256 -or
                           (Get-FileHash -Algorithm SHA256 -LiteralPath $inputFile).Hash.ToLowerInvariant() -cne $q.input_sha256){
                            throw 'Reviewed stage content changed'
                        }
                        if($q.receipt -cne ('receipt-'+$id+'.json') -or
                           (Test-Path -LiteralPath (Join-Path $session $q.receipt))){throw 'Receipt must be fresh'}
                        $receipt=Join-Path $session $q.receipt
                        # Stage owns GUI/packet verification and must write a correlated receipt.
                        # It receives immutable per-stage input, never a shared next-action file.
                        if(($q.timeout_seconds -isnot [int] -and $q.timeout_seconds -isnot [long]) -or
                           $q.timeout_seconds -lt 1 -or $q.timeout_seconds -gt 7200 -or
                           $q.effect_id -notmatch '^[a-z0-9_]+$' -or $q.phase -notin @('setup','capture','cleanup')){
                            throw 'Invalid stage timeout or identity'
                        }
                        $cancel=Join-Path $session ('cancel-'+$id)
                        $commandDeadline=[DateTimeOffset]::UtcNow.AddSeconds($q.timeout_seconds)
                        if($commandDeadline -gt $deadline){$commandDeadline=$deadline}
                        $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,
                            '-InputPath',$inputFile,'-ReceiptPath',$receipt,'-CommandId',$id,
                            '-Generation',$generation,'-EffectId',$q.effect_id,'-Phase',$q.phase,
                            '-CancellationPath',$cancel,'-DeadlineEpoch',[string]$commandDeadline.ToUnixTimeSeconds())
                        # Windows filenames cannot contain quotes; all other values are typed/validated.
                        $argumentText=($arguments|ForEach-Object {'"'+$_+'"'}) -join ' '
                        $activeChild=Start-Process powershell.exe -PassThru -WindowStyle Hidden `
                            -ArgumentList $argumentText -RedirectStandardOutput (Join-Path $session ('stage-'+$id+'.log')) `
                            -RedirectStandardError (Join-Path $session ('stage-'+$id+'-error.log'))
                        $cancelling=$false
                        $grace=$null
                        while(-not $activeChild.WaitForExit(200)){
                            if((Test-Path -LiteralPath $cancel) -or [DateTimeOffset]::UtcNow -ge $commandDeadline){
                                if(-not $cancelling){
                                    [System.IO.File]::WriteAllText($cancel,'cancel requested')
                                    $cancelling=$true;$grace=[DateTime]::UtcNow.AddSeconds(15)
                                }
                                if([DateTime]::UtcNow -ge $grace){
                                    $reply.child_running=$true;$reply.child_pid=$activeChild.Id
                                    throw 'Child did not acknowledge cancellation; still active, do not replay'
                                }
                            }
                        }
                        $activeChild.WaitForExit()
                        $exitCode=$activeChild.ExitCode
                        $activeChild=$null
                        if($cancelling -or (Test-Path -LiteralPath $cancel)){throw 'Stage cancelled; reconcile before further input'}
                        if($exitCode -ne 0){throw 'Stage failed; inspect local logs without replay'}
                        if(-not (Test-Path -LiteralPath $receipt)){throw 'Stage returned without receipt'}
                        $proof=Get-Content -Raw -LiteralPath (Session-File $q.receipt)|ConvertFrom-Json
                        if($proof.command_id -cne $id -or $proof.generation -cne $generation -or
                           $proof.effect_id -cne $q.effect_id -or $proof.phase -cne $q.phase -or
                           $proof.status -cne 'verified' -or $proof.continuation_safe -isnot [bool] -or
                           -not $proof.continuation_safe){throw 'Stage receipt is unverified or uncorrelated'}
                        $reply.status='ok'
                    }
                    default {throw 'Unsupported bridge action'}
                }
            } catch {
                $reply.error=$_.Exception.Message
                # On failure this bridge stops. It cannot advance another queued action.
                $stopping=$true
            }
            Write-AtomicJson $result $reply
            if($stopping){break}
        }
        if(-not $stopping){Start-Sleep -Milliseconds 200}
    }
} finally {
    # A non-cooperative child is explicitly reported and keeps the desktop mutex.
    # Never kill a GUI process mid-drag or allow a competing bridge to start.
    if($activeChild){while(-not $activeChild.WaitForExit(500)) {}}
    if($leaseLock){$leaseLock.Dispose()}
    if($ownsGui){$guiMutex.ReleaseMutex()}
    $guiMutex.Dispose()
    if($generation){
        Write-AtomicJson (Join-Path $session 'bridge-closed.json') @{
            generation=$generation;status='closed';utc=[DateTime]::UtcNow.ToString('o')
        }
    }
}
