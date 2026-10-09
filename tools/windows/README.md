# Windows AFX panel inspection

First stage of the VM gesture runner: inspect actual UI Automation support
before choosing semantic selectors or calibrated panel coordinates. This is
read-only. It does not load effects, click buttons, query HID or change settings.

Copy this directory into the existing shared folder as `antelope-afx-tools`.
In Windows, open the desired plugin panel, then double-click
`Z:\antelope-afx-tools\Inspect-AfxPanel.cmd`.
The script first asks which plugin/panel you will inspect; enter its name.
Then, during the ten-second delay,
focus the plugin panel and keep it unobscured until inspection completes.
The console minimizes during the delay. Click the plugin's own title bar (not
the rack); keep other windows away from it. The screenshot is taken before
control enumeration, with DPI awareness enabled. Controls outside the captured
window are skipped even when the provider incorrectly marks them onscreen.
The inspector writes, for example,
`results/panel-Instinct-TIMESTAMP/Instinct-controls.json` and `Instinct-panel.png`
beside the scripts. Linux reads those same files directly; there is no export,
packet selection or transfer step. Each run uses a new results directory.
The original name is also stored as `panel_name` in the JSON; characters invalid
in Windows filenames are replaced in filenames. The entered label does not
prove the selected window's identity: verify the captured title and image.

Inspect Instinct first: its existing Orion capture has parameter changes but
unresolved labels. Memory Cat remains useful as an optional known-map pilot;
there is no need to repeat its manual mapping.

The JSON contains visible control names, automation IDs, supported patterns,
UI values and positions relative to the selected window. UI values are not
device readbacks and do not prove wire ranges. Custom-drawn controls may expose
no useful names or patterns; the screenshot then supports a one-time coordinate
calibration. Windows may expose the whole control-panel window rather than a
separate plugin window. Review the selected title and screenshot before using
any result. This inspector is not yet a gesture runner or USB batch recorder.

Keep results and screenshots local in the shared folder or ignored `captures/`.
Password controls are skipped, but any other visible text in the selected
window can appear in local evidence. Do not focus account/activation windows.

No extra Windows package is required: the script uses Windows PowerShell,
.NET UI Automation and System.Drawing. It must run in the interactive guest
session. The `.cmd` launcher bypasses execution policy for this invocation only;
it does not change the machine's execution policy.

API reference: Microsoft's [UI Automation element inspection](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/obtaining-ui-automation-elements).

## First automated button pilot

The executor is now **one shared runner**, `Run-AfxScan.ps1`, reading
`afx-scan-plans.json`. Panel name/class, channel, labels, selectors and optional
panel-relative regions come from that JSON. Linux checks the selected plan
against its repository copy before allowing gestures. A new plugin needs
reviewed inspector data, not a new script. The current plans cover binary
buttons only; knobs and multi-position selectors need additional shared methods
and restoration evidence.

For the next batch, double-click `Run-AfxScan.cmd`, enter `instinct-filters`,
then press Enter when Instinct is open on unlinked AFX2. This exercises Filter
enable and Post-filter enable in one recording, restoring each visually before
moving to the next. Model selection and power are excluded from that batch.

`Run-InstinctPilot.cmd` is a fixed two-click trial for **ALT Morph** on
**unlinked AFX channel 2**. It uses the inspected live `Instinct`/`AltMorphButton`
UI classes and current bounds; it does not load an effect, change the selected
channel, operate a preset or guess a raw HID command. Start with Instinct open
on channel 2. The pilot fails before any click if that selection or the target
control is missing. Knobs and the remaining buttons are not included yet.

Linux must first run the listener from the repository:

```sh
python3 tools/afx_vm_pilot.py --shared '/path/to/shared/antelope-afx-tools'
```

Load `usbmon` once with `sudo modprobe usbmon` if necessary, and use a user with
dumpcap permissions. The listener waits up to 15 minutes for one new guest job.
Then double-click `Z:\antelope-afx-tools\Run-InstinctPilot.cmd` in Windows and
read the instructions and press Enter when the panel is ready. The console
minimizes, rather than closing. Focus Instinct using its title bar during the
ten-second countdown; do not manually click any plugin buttons. Leave the mouse and
keyboard alone until completion; Escape or loss of focus stops subsequent
actions. Closing Windows, restarting the host listener or retrying a completed
job does not replay its gestures. Start a fresh run for a new trial.
Every launch also saves `results/Instinct-pilot-launch-TIMESTAMP.log`, including
startup/preflight errors that occur before a trial directory exists. Linux can
read this directly, so there is no need to copy terminal messages manually.
With the common runner, new launch logs use `AFX-scan-launch-TIMESTAMP.log`
and new jobs use `results/scan-PANEL-TIMESTAMP/`. Earlier pilot files are retained.

Each trial creates `results/pilot-Instinct-TIMESTAMP/` in the shared folder.
Linux starts a bounded passive usbmon capture and proves complete matching
Orion IN reports before allowing a click. After each click it requires an
Instinct parameter OUT witness for one instance. Missing traffic, linked
mirroring, another command or a changed instance stops the pilot for review.
Capture limits are 60 seconds or 100 MB. Check `dumpcap.log` for dropped packets.

The guest saves button crops before, changed, before restoration and restored.
It requires a visible change, checks that nobody changed the button since the
trial, clicks back once, and compares the final image with the original. Pixel
thresholds are provisional and require the first real run. This is a visual
round trip, not verified device parameter readback or audible confirmation.
If a verification fails, it stops without another click or blind repair; inspect
the current button state and retained evidence before deciding what to restore.

The host gates actions through shared-folder files and bounds each action using
recording frame numbers sampled before permission and after completion. Host
timestamps are metadata only: packet timestamps may differ even from the host's
wall clock. This also avoids assuming Windows and Linux clocks agree. Analysis
reuses `scan_afx_capture.py` and records per-action frame witnesses and changed
bytes. The first write has no prior parameter baseline; comparison with the
second write produces candidates. Analysis does not promote writable profiles,
assign button polarity or certify loss-free capture. An IN-only preflight is
not proof that OUT will be recorded; the trial checks actual OUT separately.

For a passive three-second setup check without gestures:

```sh
python3 tools/afx_vm_pilot.py --preflight captures/new-pilot-preflight
```

The output directory must be new. The tool matches the active Orion profile's
VID/PID to the live sysfs USB bus/address and verifies the same connection at
completion. It reads no serial values and opens no HID controller. Endpoints
and report length come from the profile. Shared results and raw traffic remain
local; reviewed protocol facts are a separate step.
