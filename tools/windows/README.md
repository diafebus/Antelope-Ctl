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
starting GUI state. The recorder stops on scan failure so evidence can be
reviewed, and expires after the configured idle period.
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

## Next capture: six Master De-Esser Filter Type choices

Open Master De-Esser on unlinked AFX channel2. Run the same launcher and
enter `Master De-Esser`; press Enter and focus its title bar during the ten-second
countdown. Linux must be waiting. Leave mouse and keyboard alone.

The wheel trials completed HighPass3 → BandPass1 → HighPass3, but the owner
reports skipped entries even with partial notches. The next run uses no wheel.
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
The first Windows execution of named menu selection is pending.

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
