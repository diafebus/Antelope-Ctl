# Reviewed AFX capture queues

The batch runner moves repeated stage dispatch, evidence checks and reporting
into local scripts. It requires no model turn per gesture. It does not discover
unknown controls, authorize runtime writes or promote endpoint candidates into
verified ranges. Meter work remains the separate native oscillator/routing and
actual-card-telemetry session described in the display inventory.

## Current implementation status

`tools/afx_capture_batch.py` prepares and validates queues offline. Explicit
execution uses a fresh Windows bridge and one owned passive Linux recorder.
`Invoke-AfxCaptureStage.ps1` adapts existing reviewed capture plans. There is no
five-plugin cap: a manifest accepts up to 100 plugins, subject to the bridge
lease and each plugin's full setup/capture/cleanup timeout budget.

Setup and cleanup require reviewed per-plugin recipe scripts. These are not
generated or supplied by this change. They must verify the intended channel,
instance, unlinked state and trial insertion/removal using the existing measured
capture process, preserve owner changes and emit correlated evidence. A receipt
is an assertion by a reviewed recipe, not an independent device readback.
Unknown UI geometry, selector labels or restoration state require review.

The new Windows bridge and native cancellation helper require Windows
`Run-AfxCapture.ps1 -ValidateOnly` and a supervised bounded trial before an
unattended session. Linux tests do not compile or execute PowerShell.

## Offline preparation

Create a fresh directory directly under the shared kit's `results/`. Copy the
reviewed scripts and immutable JSON inputs into it. A draft manifest has this
shape (the setup/cleanup filenames below are placeholders for reviewed recipes):

```json
{
  "version": 1,
  "plugins": [{
    "effect_id": "effect_id_from_catalog",
    "steps": [
      {"phase": "setup", "script": "Reviewed-Setup.ps1", "input": "setup.json", "timeout_seconds": 300},
      {"phase": "capture", "script": "Invoke-AfxCaptureStage.ps1", "input": "capture.json", "timeout_seconds": 1800},
      {"phase": "cleanup", "script": "Reviewed-Cleanup.ps1", "input": "cleanup.json", "timeout_seconds": 300}
    ]
  }]
}
```

Prepare and validate on Linux; neither command accesses hardware or dispatches
a bridge command:

```sh
python3 tools/afx_capture_batch.py --prepare draft.json --session /path/to/kit/results/session-NEW --output reviewed.json
python3 tools/afx_capture_batch.py --plan reviewed.json --session /path/to/kit/results/session-NEW --output /tmp/unused-validation-output
```

Preparation removes effects already marked complete in the workflow manifest,
adds SHA256 fingerprints of every script/input and refuses to overwrite an
existing reviewed manifest. Review the scripts, inputs and resulting manifest.
Auto-Tune remains excluded. Execution rejects stale completed-effect entries.

The capture adapter input includes `effect_id`, `plugin_name`, `plan_id`,
Windows-native `kit_path`, and `kit_sha256`. The latter maps these six kit
basenames to SHA256 values: `Run-AfxCapture.ps1`, `Inspect-AfxPanel.ps1`,
`Run-AfxScan.ps1`, `afx-scan-plans.json`, `afx-capture-workflows.json`, and
`afx-dropdown-options.json`. Successful preflight cache reports contain these
hashes. The adapter checks them and the actual executed plan, then invokes
prepared mode without discovery or interactive prompts.

## Execution in a later session

After the Windows preflight, supervised trial and recipe review, start a fresh
bridge on the Windows desktop (adapt paths and lease):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\kit\Run-AfxSessionBridge.ps1 -SessionDirectory C:\kit\results\session-NEW -LeaseMinutes 120
```

Then explicitly execute the reviewed manifest from Linux:

```sh
python3 tools/afx_capture_batch.py --plan reviewed.json --session /path/to/kit/results/session-NEW --output /path/to/run-NEW --shared /path/to/kit --stop-file /path/to/STOP --execute-reviewed
```

The runner starts and owns its passive recorder. Do not separately start another
recorder or legacy GUI bridge. A desktop mutex, recorder lock, session generation,
expiry and fresh handshake prevent normal competing/replayed sessions. The bridge
also rejects existing capture workers. Files are rehashed before each stage.
The bridge remains idle until its lease expires; it never repeats commands.

Only a compact JSON result goes to stdout. Detailed state, the immutable plan,
verified receipts and capture summaries stay in the output directory; recorder
output goes to the adjacent `*-recorder.log`. Original scan artifacts remain in
the shared kit's local `results/`. These files and captures stay out of Git.

## Stage contract and failure handling

Each reviewed script accepts `InputPath`, `ReceiptPath`, `CommandId`,
`Generation`, `EffectId`, `Phase`, `CancellationPath` and `DeadlineEpoch`.
It must check cancellation/deadline before input and during waits, stop at a safe
boundary and release any held input in `finally`. The supplied scanner checks
cancellation during native sweeps and releases its mouse button in `finally`.

A fresh receipt requires `status: "verified"`, `continuation_safe: true`,
matching command/generation/effect/phase, and nonempty `evidence` entries with
session-local `file` and `sha256`. Cleanup additionally requires
`trial_removed: true`. Capture requires `capture_jobs` referencing fresh `scan-*`
jobs. The host checks saved action ACKs, progress, decoded evidence, zero-drop
logs and the analysis hash binding to the capture. Missing or mismatched evidence
stops advancement. Setup/cleanup receipts still depend on the reviewed recipe's
verification logic; never emit a success receipt just because clicks completed.

Touch the chosen stop file to stop advancement. A pending action receives a
cancel marker on stop, timeout or interruption. The bridge gives its child a
cooperative grace period and reports if it remains active, retaining its desktop
mutex until the child exits. No automatic cleanup, repair or retry follows an
uncertain stage. Inspect saved state, pending command, logs and actual trial state
before preparing a new session. Do not replay an old manifest into a failed
session; output directories and bridge sessions cannot be resumed blindly.

For offline reporting of existing jobs:

```sh
python3 tools/afx_capture_summary.py /path/to/kit/results/scan-JOB --output /tmp/afx-evidence-report.json
```

This reads saved artifacts without tshark, HID or GUI access and prints one count
line. Evidence completeness and semantic review are separate: labels, physical
scales, independent readback and runtime contracts may remain pending after a
successful acquisition. Historical captures without an analysis SHA256 binding
can be reported, but cannot authorize advancement in a new queue.
