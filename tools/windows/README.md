# AFX capture on the Windows VM

Use one launcher: `Z:\antelope-afx-tools\Run-AfxCapture.cmd`.
Enter the plugin name. It chooses the prepared stage from
`afx-capture-workflows.json`; no script names or plan IDs need to be remembered.

## Next capture: V12 Chorus

1. Open V12 Chorus on unlinked AFX channel2 in the Orion control panel.
2. Leave its panel open; the batch scans Space first to enable the color controls.
3. Double-click `Run-AfxCapture.cmd` and enter `V12 Chorus`.
4. Press Enter when ready, then focus its title bar during the ten-second countdown.
5. Leave mouse and keyboard alone until the console returns, then report done.

The prepared V12 stage captures ten knob ranges and Humanize in22 labelled
phases. The Linux listener must be waiting. Files are saved automatically in
`results/scan-V12-Chorus-TIMESTAMP/`, shared directly with Linux. The actual
`TurboEnsembler` panel and ten visible knob classes were reviewed from the
inventory; hidden PresetIndex is excluded. Existing type70 raw mappings are
reused, with no repeated INIT. Power/bypass remains outside this plan.
Humanize is clicked twice to restore its starting state; range knobs stay
at maximum. Physical values displayed inside V12 knobs are saved in screenshots.

## Next capture: resume BBD Chorus

The capture `scan-BBD-Chorus-20261009T192357505Z` completed the four knob
ranges and Chorus/Vibrato. These results are retained. Stereo Type stopped:
centre clicks select Split repeatedly, rather than cycling. Power was not reached.

Open BBD Chorus on unlinked AFX channel2, run the same launcher, enter
`BBD Chorus`, press Enter and focus its title bar within ten seconds. Linux
must be waiting. This resume captures only Stereo Type and Power in seven
phases; no knob or mode rescans. Leave mouse and keyboard alone.

The direct-position method clicks the four visible rows separately. Each phase
primes a different row before selecting its target to establish fresh OUT even
when the target was already selected. It saves four distinct labelled screenshots
and learns the raw values; it does not assume numeric enum order. After the
four rows, the initial screenshot must match exactly one captured position.
That learned visual/raw correspondence selects the restore row. If a preceding
parameter block exists, it must agree. Newer edits, repeated/ambiguous positions,
wrong bytes or failed restoration stop the run without blind repair clicks.
Direct row-hit execution is still pending this first Windows run.

The complete `bbd-controls` JSON plan remains available: four knob endpoint
pairs, Chorus/Vibrato round trip, four Stereo Type positions plus restoration,
and Power round trip (17phases). The workflow currently selects its reviewed
`bbd-remaining` resume plan. Successful partial evidence is kept; adding a new
gesture does not require repeating the completed controls.

Power records opcode0x14/selector0x98 for the same effect instance and all0/1
events; persistent state and polarity are unverified. Chorus/Vibrato uses measured
byte24 feedback because the nearby red indicator is animated. Clip/meters are
read-only. V12's older plan still excludes power/bypass and remains partial.

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
still run inventory only and explicitly report that no values were scanned.
Completed jobs carry declared coverage; completing a plan does not prove
unplanned controls or device readback. No plugin-specific script is needed.

Instinct has all21 knob endpoint observations and three mapped switches.
Its model selector, power, interpolation laws and runtime reader/writer remain
unverified. The full Instinct range plan remains available through the same
launcher. Older diagnostic/pilot launchers have been removed; captures remain.

## Shared files

Keep `Run-AfxCapture.cmd`, its PowerShell driver, `Inspect-AfxPanel.ps1`,
`Run-AfxScan.ps1`, the two JSON data files and this README together. `results/`
contains private local evidence and stays out of Git. The Linux listener is
`tools/afx_vm_pilot.py`; it uses the active Orion profile's transport and opens
no competing HID controller. PowerShell runtime verification happens in the
Windows VM; the Linux host has no PowerShell runtime.
