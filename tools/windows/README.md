# AFX capture on the Windows VM

Use one launcher: `Z:\antelope-afx-tools\Run-AfxCapture.cmd`.
Enter the plugin name. It chooses the prepared stage from
`afx-capture-workflows.json`; no script names or plan IDs need to be remembered.
Known GUI dropdown choices and aliases live in `afx-dropdown-options.json`.
Their order is UI evidence, not a device encoding or a license inventory.

For fingerprinted queues, compact offline evidence reports and the reviewed-stage
contract, see [the batch runner guide](../../docs/orion-afx-batch-runner.md).
Windows validation and reviewed setup/cleanup recipes are required before its
first unattended use.

## Cached tool preflight and prepared capture

Ordinary launches cache successful syntax, native-helper and reviewed-plan
validation in `results/preflight-cache.json`. Reuse requires matching SHA256
hashes for all three capture scripts and all three JSON registries, together
with the PowerShell/.NET/OS/process architecture context. Missing, malformed,
failed or mismatched reports trigger full validation. Full validation checks
that the kit did not change during the check; reports are published through
same-directory atomic file replacement rather than an in-place overwrite.
Filesystems that cannot perform that replacement fail the launch before gestures.

`-ValidateOnly` always performs the complete check, even when a cache exists.
`-PreflightReport <path>` still writes an explicit report for that check.
The cache contains no device availability, selected-channel, focus, instance,
parameter or restoration state: each capture still runs the normal current GUI
and host evidence guards.

For a prepared batch stage, `Run-AfxCapture.ps1 -Prepared -PluginName <name>
-CapturePlan <reviewed-plan-id>` forwards prepared mode only after the plugin,
plan and channel match the reviewed registry. It avoids the manual readiness
prompt/delay in `Run-AfxScan.ps1`; the caller must already have the correct panel
in the foreground. It retains tool preflight and all actual gesture checks.
Prepared mode rejects missing plugin/plan arguments and cannot invoke discovery
or a reviewed resume.

## BBD Chorus capture completed

The original range scan and short resume cover four knob ranges, the
Chorus/Vibrato footswitch, Basic/Wide/Split/Cross and Power. The selector and
Power returned to their starting appearance. The resume's final host error was
a decoder offset mistake; offline review with the measured BBD packet layout
confirms the same instance across both Power actions. No rerun is required.
Entering `BBD Chorus` now reports completion without moving controls.

Run the same launcher with the next plugin name. With the Linux recorder
running, unfamiliar plugins now proceed from inventory to an automatically
generated batch in the same launch. Supported controls are uniquely identified,
enabled Pot knobs and binary CheckBox TogglePattern switches inside a matching
Orion effect panel. No per-plugin numeric label parser or guessed wire offset
is needed. The inventory, generated plan, screenshots and USB evidence stay in
`results/`; there are no manual image transfers.

Keep the recorder available between plugins with:

```sh
python3 tools/afx_vm_pilot.py --shared '/run/media/diafebus/4TB Linux/VirtualBox/SharedFolder/antelope-afx-tools' --serve --wait-seconds 1800
```

Enter the catalog plugin name, focus its title bar during the ten-second delay
and leave the mouse alone. Discovery continues into the scan without another
Enter or launch. Knobs remain at maximum; binary switches return to their
starting GUI state. A failed batch stops immediately and retains its evidence.
With `--serve`, the recorder stays available for a newly launched batch or a
reviewed resume; it never retries the failed job. It expires after the
configured idle period. Review an interrupted control's state before launching
another batch that could affect it.
Only one Linux recorder can serve a shared folder. A second listener exits
before reading jobs or writing their capture/handshake files. Its exclusive
lock releases automatically when the owning process exits.

Discovery produces endpoint **candidates**, not numerical range or readback
proof. It requires captured movement after priming, then two further completed
sweeps without parameter-block changes while capture continues advancing.
Evidence distinguishes fresh unchanged writes from suppressed OUT reports.
The complete executed plan must match the host-generated plan before capture
readiness is granted.

Disabled or ambiguous controls, unrecognized panel identities, dropdowns,
presets, cabinet/speaker/model selectors and nonstandard switches remain
pending. Presets can replace many parameters and are never swept automatically.
Effects without a captured Orion type retain inventory for review. The pending
list prevents a successful supported-control batch from claiming a full plugin
mapping. Reviewed plans remain available for measured switches, finite selector
positions and Power round trips.
Reviewed resume plans retain successful controls rather than repeating them.

The BBD Power override is instance17/type18/state19 for opcode0x14/selector0x98.
Processing polarity/readback and runtime writes remain unverified. The indicator
above Chorus/Vibrato shows vibrato speed, per owner, and is excluded from
mode/power verification. V12's older plan remains partial (power not captured).

## Interrupted batches and reviewed resume

Each new job records `host-plan.json`, `capture-budget.json`,
`action-windows.json` and `progress.json`. Progress lists accepted phases,
completed controls, the current interrupted action and any failure reason.
Only host-verified phases with an issued ACK count. A whole control is complete
only after all its phases; an interrupted toggle is never treated as restored.

To prepare the remaining controls without accessing a device or VM:

```sh
python3 tools/afx_vm_pilot.py --prepare-resume '/path/to/antelope-afx-tools/results/scan-PLUGIN-JOB'
```

This writes `remaining-plan.json` for review. Inspect the recorded failure,
current effect instance, unlinked AFX channel and interrupted control state.
Reconcile uncertain state before continuing. Then use the waiting Linux recorder
(or start one if it has stopped),
run the same Windows launcher, enter `resume scan-PLUGIN-JOB`, and type
`REVIEWED` only after that review. The runner reacquires current GUI controls
and starts unfinished controls as new full trials in a fresh job directory.
Completed controls are skipped; no saved baseline is replayed or restored.
Knob ranges still intentionally finish at maximum.

The host reconstructs the remaining plan and compares the exact guest request,
current reviewed definitions and original device connection. A changed source
plan, missing ACK, changed device location or mismatched remaining plan blocks
gestures. A fresh inspection/review is needed in those cases. Jobs from older
kits that lack host checkpoints remain evidence; do not fabricate completion
records to make them resumable.

Capture time and file-size caps now scale with the reviewed plan. These are
maximum failure bounds, not extra delays. The host shares bounded handshake
and final-analysis deadlines with Windows; a stopped decoder reports its own
failure instead of leaving a ten-second guest timeout as the only explanation.
Full-PCAP decoding still grows with capture size and is capped at twenty
seconds per pass. If that limit is reached, inspect the retained progress and
use a smaller reviewed remaining batch rather than removing the guard.
Generic knob discovery primes in both directions so an initially maximum knob
does not fail solely because upward motion produces no write. All target
controls are checked for visibility, enabled state and usable knob drag room
before the first gesture. Linking remains an operator precondition: the GUI
channel check establishes selection, not that the link flag is off.

Keep the KVM viewer open during captures when it owns USB redirection. Leaving
the VM running after closing that viewer can still disconnect the redirected
Orion. Moving the viewer to another workspace is suitable for unattended work;
leave the vendor AFX window open inside Windows.

PowerGate's reviewed `powergate-knobs` plan targets six observed `Pan` controls.
Their accessibility bounds extend up to11pixels beyond the parent panel, so the
plan permits12pixels with `panel_overflow_px`. VEQ-4K PINK's measured lower-row
bounds need14pixels. Explicit reviewed knob plans may specify1–14pixels;
invalid types, bounds and non-knob use fail during host and Windows preflight.
The entire control must remain inside the AFX window and its central16pixel
square inside the panel. Other controls retain full parent containment. The processing lever
`PowerGateBypassPot` is excluded from knob discovery and needs a separate trial.

## Further visible-control captures completed

PowerGate, PowerEx, VEQ-1A and VMEQ-5 also have completed visible-control
workflows as of 2026-10-25. The launcher reports completion without repeating
them. Their [power dynamics](../../docs/orion-afx-power-dynamics.md) and
[EQ findings](../../docs/orion-afx-eq.md) distinguish endpoint candidates from
full stepped-selector maps and retain unverified readback/scaling/runtime limits.

## Master De-Esser capture completed

The 2026-10-25 pass covers eight knob endpoint candidates, Q under both BandPass
modes and its HighPass disable/reset dependency, five visible Filter Type choices,
four Monitor/Out states, a processing-button round trip and six preset names
inventoried without selection. Entering `Master De-Esser` now reports completion
without replaying these controls. Physical scaling, independent readback/runtime
writes and audible/stereo behavior remain unverified. See
[the findings](../../docs/orion-afx-deesser.md) for exact coverage and frames.
The earlier six-filter-choice report remains a historical discrepancy.

Monitor/Out exposes a checkbox but cycles through four raw states. Its measured
class is excluded from automatic binary discovery; use its reviewed selector
method. Qt can also retain false-visible menu rows after closing: menu operations
now require actual native-visible ComboBox popup roots.

### Reviewed Page key method

Open Master De-Esser on unlinked AFX channel2 with the dropdown closed.
Run `Run-AfxCapture.cmd`, enter `Master De-Esser`, press Enter and focus its
title bar during the ten-second countdown. Linux must be waiting.

The registry retains the five choices actually visible in the last recorded
menu: HighPass 1/2/3 and BandPass 1/2. Full choice count remains unresolved;
no sixth choice or raw value is guessed. The runner clicks Filter Type open,
checks the owned native popup's visibility/bounds, and closes it with a click
on the same dropdown without changing its selection. It does not traverse or
screenshot menu rows during activation. It then verifies keyboard focus on
that exact ComboBox and sends one Page Down,
waits **five seconds**, saves the selected value and screenshot, then waits for
host verification before one Page Up returns to the starting value. No wheel
events or preset changes are used. Start at a choice with a following row,
such as HighPass1; starting at the last visible choice stops before any key.

Host checks reject activation writes, skipped choices, unexpected effect or
instance, parameter changes outside byte26, unstable blocks and newer edits
before restoration. This is an adjacent-choice method trial; the total count
discrepancy and full parameter coverage remain unresolved. The owner reports
that keys require clicking the dropdown first. The native click-open/click-close activation and paced key round trip passed
in `scan-Master-De-Esser-20261025T002640258Z`. An opening detector initially
accepted a non-ComboBox window; the current guard checks the actual popup class.

## Previous direct menu attempt

Open Master De-Esser on unlinked AFX channel2. Run the same launcher and
enter `Master De-Esser`; press Enter and focus its title bar during the ten-second
countdown. Linux must be waiting. Leave mouse and keyboard alone.

The wheel trials completed HighPass3 → BandPass1 → HighPass3, but the owner
reports skipped entries even with partial notches. The direct-selection plan uses no wheel.
It opens Filter Type, reads the six visible named entries, clicks each entry
explicitly and holds each selected value for **five seconds**. Menu and panel
screenshots plus passive USB evidence are saved. The final step restores the
starting menu choice. Only an already-selected target is primed through a
different named entry to obtain fresh OUT evidence.

The script requires six distinct names, clear visible rows beside the reviewed
dropdown, exact selected labels, closed popups and one captured effect instance.
The host checks isolated byte26 changes and six distinct raw values before
allowing the final restore. Labels/raw order are learned from evidence, not
guessed. Input is allowed only with the original panel or its verified popup
in the foreground. Failure stops the batch; an unverified popup may remain open.
The first named-selection attempt stopped during discovery: unrelated vendor
menu rows reached the64-item limit. Its capture contains no outbound HID reports.
Discovery now searches the active effect panel and nearby separate popup windows,
filters rows by the live dropdown bounds before counting, and accepts reused Qt
popup containers only when their options become visible in this opening.
Before/open screenshots and discovery metadata survive validation failures.
Open-menu screenshots use screen copying without moving the pointer or changing
focus; parameter screenshots follow selection and verified popup closure.
The corrected discovery opened the menu in scan214921898Z but stopped before
selection: screenshot and UIA both exposed five distinct choices against the
plan's expected six. No OUT reports were captured. This plan is retained for
reference; the current launcher uses the Page key method trial above.

This captures Filter Type only. Knobs and the remaining plugin controls are
outside this focused batch.

Presets remain untouched: scrolling them replaces many parameter values.
The previous popup attempt stopped because the entire UI tree exceeded512nodes;
inspection now filters menu/list items and caps visible options instead. Escape
is only sent when a popup/options prove opening, to avoid closing the panel after
a failed Invoke. The full parameter plan still needs Filter Type choices and
Q dependency review; known knob inventory is retained.

## Capture stages

Inventory is read-only: no clicks, drags, value edits or HID commands.
It saves visible names/classes, supported patterns, selected values, bounds,
hover screenshots and selector candidates. When display and internal class
names differ, a bounded search finds the lowest common ancestor of visible
Pot controls. Panel identity and selectors still need review before a plan
is enabled. Password/offscreen controls are skipped. Startup errors remain
visible and are logged privately under `results/`. Before prompting, the
launcher runs a Windows preflight in a separate PowerShell process: parse the
three helpers, compile their native C# sources and load UI Automation
assemblies. No mouse/device calls occur in that preflight. Actual capture
execution is still checked on the first Windows run.

Reviewed range batches use the same helper for every plugin. A Linux listener
must be waiting before running a range stage. It records passive usbmon traffic
and gates each GUI action. Continuous held vertical sweeps capture both
endpoints; full-panel screenshots label each phase. Known byte/float fields
use captured-write feedback: reach the catalog's raw endpoint, repeat a
sweep and require the complete parameter payload to remain identical.
The host rejects stale prior-phase writes, wrong instances and changes outside
the reviewed field, and rechecks the final block before acknowledging.
Minimum is primed away from the clamp to establish fresh write evidence.
Twelve sweeps per phase and600seconds/100MB bound a full batch. Captured
writes are distinct from verified device readback. Range
tests leave knobs at maximum, as requested. Repeated equal labels do not prove
wire endpoints; offline review retains unknown fields and ambiguous labels.
Infinity labels are stored as JSON strings. Button round trips are also
supported. Wrong targets, unrelated writes, missing labels or changed focus
stop the capture, retain evidence and release the mouse button.

Cabinet/speaker/model selectors are included in inventory. The generic
`selector_cycle` gesture supports reviewed finite cycles of2–8positions, with
separate images, fresh wire evidence, uniqueness and starting-state checks.
Plans declare their candidate field and visual region. Reviewed `selector_positions` plans support direct row hits and learned
restoration. Menu controls still need a reviewed gesture before capture. Unknown plugins
without a captured Orion identity or supported controls retain inventory only
and explicitly report that no values were scanned. Successful older captures
do not establish that all plugins can already be captured consecutively.
Completed jobs carry declared coverage; completing a plan does not prove
unplanned controls or device readback. No plugin-specific script is needed.

Instinct has all21 knob endpoint observations and three mapped switches.
Its model selector, power, interpolation laws and runtime reader/writer remain
unverified. The full Instinct range plan remains available through the same
launcher. Older diagnostic/pilot launchers have been removed; captures remain.

## Shared files

Keep `Run-AfxCapture.cmd`, its PowerShell driver, `Inspect-AfxPanel.ps1`,
`Run-AfxScan.ps1`, the three JSON data files and this README together. `results/`
contains private local evidence and stays out of Git. The Linux listener is
`tools/afx_vm_pilot.py`; it uses the active Orion profile's transport and opens
no competing HID controller. PowerShell runtime verification happens in the
Windows VM; the Linux host has no PowerShell runtime.

## Native launcher checks and reviewed batch selection

From Windows, run the optional hardware-free launcher checks:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-AfxLauncher.ps1
```

They execute the real `.cmd` entry point for the completed BBD path, excluded
Auto-Tune, wrong-effect/unknown plans, blank input and a missing resume job.
Prerequisites are checked before execution so the completed path cannot silently
become a live scan. Each invocation preflights PowerShell/C# and plan loading.
The launcher preserves scan failures through PowerShell and the final `.cmd`
`pause`; callers must check its exit status and retained job evidence.

Interactive operation is unchanged. An automation caller can also supply
`-PluginName "Master De-Esser"` and `-CapturePlan REVIEWED-PLAN-ID` to
`Run-AfxCapture.cmd`. The selected plan must match the plugin and AFX channel;
this does not skip panel readiness, focus, enabled-state, host handshake or
restoration guards. Resume and CapturePlan cannot be combined. Use a new job
after reviewing a failure; never infer successful restoration from exit status
alone or replay completed controls merely to exercise the launcher.

### Concentric knob targets

Reviewed `knob_range` controls may declare a normalized
`drag_point: {"x": 0.86, "y": 0.5}` within the original UIA rectangle.
Missing metadata keeps the centre target. This distinguishes screenshot-reviewed
inner/outer hit zones when concentric controls expose the same bounds; the
point alone does not prove which Qt control receives input.

Host and guest reject nonfinite, outside, malformed or non-knob point metadata.
The resolved point needs a16pixel square inside the control, panel, window and
screen, with24pixels of vertical drag room. Hover, drag and reentry use that
same point; focus/channel/bounds/enabled/occlusion checks and bounded mouse
release remain enforced. Point-bearing reviewed jobs use request version5 and
an exact `executed_plan` comparison, so stale guest targeting metadata fails
before gestures. Discovery/resume retain their existing exact-plan contracts.

Verify each new concentric target with an isolated captured gesture before a
full range pass. Review all parameter differences; bounds and native-window
hit testing do not establish the inner/outer parameter mapping. Windows
preflight exercises point geometry without GUI input.

### Horizontal controls

An explicitly reviewed `knob_range` may declare `"drag_axis": "horizontal"`.
Missing metadata retains vertical motion; only the exact strings `vertical`
and `horizontal` are accepted, and other control kinds cannot declare an axis.
Horizontal minimum gestures move left and maximum gestures move right. The
existing vertical directions remain down/up. Start-point, focus, screen bounds,
enabled-state and mouse-release guards remain enforced, with drag room checked
on the selected axis.

Audio / Baton's 40Hz roller was independently probed horizontally: frame2665
in `unattended-20261028T023901Z-audiobaton-band40-horizontal/Orion.pcapng`
changes only byte20 from50 to51 while the paired vertical indicator moves and
other controls remain unchanged. A vertical probe produced no parameter write.
This is measured input routing, not an endpoint or physical gain scale.

Axis-bearing plans require request version5 and the exact executed plan, just
like point-bearing plans. Native preflight checks metadata, direction and
axis-aware geometry without gestures. Trial a new control through the launcher
before expanding its reviewed range plan; class naming alone is insufficient.

The first 40Hz runner pilot stopped when that same roller's native bounds
shifted one pixel horizontally. Its runtime identity, Y, width and height were
unchanged, and only the intended parameter changed. A reviewed horizontal knob
may declare `"bounds_shift_x_px": 1` for this measured case; the default is
exact bounds. Only integer0/1 is accepted. The original anchor and pointer stay
fixed, with no accumulated drift; Y/size/identity remain exact and the16pixel
starting area must fit the live control, panel and window. Other layout, focus
and parameter checks remain enforced. Apply this allowance only after evidence
for that particular control; it is not inferred for sibling rollers. The fresh single-control
`scan-AudioBaton-20261028T034922060Z` pilot then accepted both phases:
byte20 raw0 at frame7489 and raw100 at frame17273, with 24,254 packets and
zero drops. These are endpoint candidates; other controls need their own
routing, bounds and range evidence.
