# AFX capture on the Windows VM

Use one launcher: `Z:\antelope-afx-tools\Run-AfxCapture.cmd`.
Enter the plugin name. It chooses the prepared stage from
`afx-capture-workflows.json`; no script names or plan IDs need to be remembered.

## Next capture: V12 Chorus

1. Open V12 Chorus on unlinked AFX channel2 in the Orion control panel.
2. Set Space above zero so Colorize and Clr Shifter are available.
3. Double-click `Run-AfxCapture.cmd` and enter `V12 Chorus`.
4. During the ten-second countdown, focus the plugin's title bar.
5. Leave mouse and keyboard alone until the console returns, then report done.

The prepared V12 stage inventories control classes, knob hover labels and
selector metadata. No Linux USB recorder is needed for this stage. Files are
saved automatically in `results/panel-V12-Chorus-TIMESTAMP/`; Linux reads the
same folder directly. There is no manual screenshot or transfer step.
Existing type70 raw offsets/ranges are retained; no repeated INIT test is
needed. After reviewing this inventory, the same launcher will select V12's
range plan, with Space before the dependent color controls.

## Capture stages

Inventory is read-only: no clicks, drags, value edits or HID commands.
It saves visible names/classes, supported patterns, selected values, bounds,
hover screenshots and selector candidates. When display and internal class
names differ, a bounded search finds the lowest common ancestor of visible
Pot controls. Panel identity and selectors still need review before a plan
is enabled. Password/offscreen controls are skipped. Startup errors remain
visible and are logged privately under `results/`.

Reviewed range batches use the same helper for every plugin. A Linux listener
must be waiting before running a range stage. It records passive usbmon traffic
and gates each GUI action. Continuous held vertical sweeps capture both
endpoints; numeric status and full-panel screenshots label each phase. Range
tests leave knobs at maximum, as requested. Repeated equal labels do not prove
wire endpoints; offline review retains unknown fields and ambiguous labels.
Infinity labels are stored as JSON strings. Button round trips are also
supported. Wrong targets, unrelated writes, missing labels or changed focus
stop the capture, retain evidence and release the mouse button.

Cabinet/speaker/model selectors are included in inventory. Enumerated-option
gestures are not implemented yet: each needs a reviewed option list and wire
changes per choice. Custom cycling controls need a known finite cycle. The
inspector does not click selector options. Knob ranges alone do not complete
a plugin with selectors or switches.

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
