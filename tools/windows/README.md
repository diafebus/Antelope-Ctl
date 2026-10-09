# AFX capture on the Windows VM

Use one launcher: `Z:\antelope-afx-tools\Run-AfxCapture.cmd`.
Enter the plugin name. It chooses the prepared stage from
`afx-capture-workflows.json`; no script names or plan IDs need to be remembered.

## BBD Chorus capture completed

The original range scan and short resume cover four knob ranges, the
Chorus/Vibrato footswitch, Basic/Wide/Split/Cross and Power. The selector and
Power returned to their starting appearance. The resume's final host error was
a decoder offset mistake; offline review with the measured BBD packet layout
confirms the same instance across both Power actions. No rerun is required.
Entering `BBD Chorus` now reports completion without moving controls.

Run the same launcher with the next plugin name. Unknown plugins still get
read-only inventory and require a reviewed control plan; automatic plan
preparation is not implemented. Generic methods now include knob endpoints,
measured mode switches, cycles, direct row selectors and Power round trips.
Reviewed resume plans retain successful controls rather than repeating them.

The BBD Power override is instance17/type18/state19 for opcode0x14/selector0x98.
Processing polarity/readback and runtime writes remain unverified. The indicator
above Chorus/Vibrato shows vibrato speed, per owner, and is excluded from
mode/power verification. V12's older plan remains partial (power not captured).

## Next preparation: Master De-Esser dropdowns

Existing inventory is retained: seven enabled knobs, a Q knob disabled under
HighPass1, Monitor/Out, Bypass, Presets and Filter Type. Open Master De-Esser
on unlinked AFX channel2. Run the same launcher and enter `Master De-Esser`;
focus its title bar during the ten-second delay, then leave mouse and keyboard
alone. This short pass opens Presets and Filter Type separately, saves their
popup screenshots/control records, and closes each with Escape. It does not
select options or sweep knobs; no Linux recorder is required for inventory.
New visible option items must prove opening; disappearance of popup/items must
prove closure. Selected menu values must remain unchanged. Visible option lists
are recorded; hidden/virtualized entries remain unknown. Files save automatically under
`results/panel-Master-De-Esser-TIMESTAMP/`, including `*-menus.json`.

The full parameter plan follows review of Filter Type options and Q dependency.
Preset lists are inventoried separately because selecting a preset replaces many
settings. Current menu invocation is unverified until the first Windows run;
focus/selection failures stop without repair writes. No manual screenshot or
file transfer is required. The same menu inspection method is reusable.

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
