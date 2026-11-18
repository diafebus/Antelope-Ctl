# Orion Master De-Esser observations

These findings come from owner-authorized Windows GUI captures on Orion Studio
Synergy Core, reviewed on 2026-10-25. The shared effect identifier remains
`deesser`; model-local knowledge lives in [its plugin file](../profiles/afx/deesser.json).
Parameter and processing commands remain observation-only. No runtime writer,
parameter reader, audible result, stereo behavior or power-cycle retention was
established by this pass.

## Parameter block

The observed family is `0x70 / 0x20`, selector `0xd5`, subcommand `0x0e`,
type27 at report byte18 and instance at byte19. Directed trials used instance0
on unlinked AFX2. Offsets below are absolute HID report offsets.

| Control | Offset / width | Captured endpoint candidates | Displayed endpoint labels |
| --- | --- | --- | --- |
| Threshold | 21 / 1 | 0–80 | 0–80; unit unresolved |
| Frequency | 22 / 2, little endian | 150–20000 | 150–20k |
| Q, under either BandPass mode | 24 / 2, little endian | 1–400 | 0.01–4.00 |
| Dry/Wet | 27 / 1 | 0–100 | No numeric endpoint display recorded |
| Ratio | 28 / 1 | 10–200 | 1.0–20.0 |
| Attack | 29 / 1 | 1–200 | 0.1–20.0 |
| Release | 30 / 1 | 10–200 | 10–200 |
| Soft Knee | 31 / 1 | 0–30 | 0–30; unit unresolved |

Each knob has two accepted stable-block phases, with all other parameter bytes
unchanged during its isolated windows. Repeated completed sweeps distinguish
plateaus from a stalled capture. These are endpoint associations, not proofs of
an interpolation law, display units not shown by the UI, or a device-verified
write range. Knobs intentionally finished at maximum. The catalog records the
individual frames and capture hashes in `labelled_gui_observations`.

Sources are `scan-Master-De-Esser-20261025T003349239Z` for Threshold,
Frequency and Dry/Wet; accepted knob phases in
`scan-Master-De-Esser-20261025T003655397Z` for Ratio, Attack, Release and
Soft Knee; and `scan-Master-De-Esser-20261025T004418330Z` /
`scan-Master-De-Esser-20261025T005043532Z` for Q under BandPass1 / BandPass2.
The second job's subsequent Monitor/Out binary trial failed; this does not
invalidate its separately accepted knob phases or make that whole job complete.

## Selectors and dependencies

Filter Type occupies byte26. A native five-row traversal maps HighPass1/2/3 to
0/1/2 and BandPass1/2 to 3/4, returning to HighPass1. The captured rows and
source frames are in [PROTOCOL.md section12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls).
The earlier report of a sixth filter choice remains a historical discrepancy;
no sixth name or raw value is invented.

Q is editable in both BandPass modes and disabled in all three HighPass modes.
The additional HighPass2/3 enabled-state checks are recorded in
`unattended-20261025-highpass-q-dependencies/Orion.pcapng` at frames2181/4949;
frame7569 returns to HighPass1. Returning from either mode's captured
Q maximum400 to HighPass1 emits both filter byte26=0 and Q bytes24–25=71,
and disables the Q control. The coupled reset is vendor GUI behavior. A consumer
must not force a former BandPass Q value back into the disabled HighPass1 state.
The reset witnesses are frame3099 in
`unattended-20261025-q-filter-restore/Orion.pcapng` and frame2156 in
`unattended-20261025-q-bandpass2-restore/Orion.pcapng`.

Monitor/Out is a **four-state selector**, despite exposing a checkbox and
binary-looking Windows TogglePattern labels. Byte20 traverses 0→1→2→3→0;
multiple nonzero states report `On`. The corrected native selector plan in
`scan-Master-De-Esser-20261025T005043532Z` captures frames
16347/17151/17857/18613, checks isolated byte20 changes and restores the
preceding full parameter block. Four distinct indicator images accompany it.
The [manufacturer description](https://en.antelopeaudio.com/products/master-de-esser/)
also describes four monitoring modes; individual mode meanings remain unmapped.
The WebUI therefore shows an explicitly unverified, disabled Monitor/Out
selector. This is partial semantic coverage; four captured positions do not
establish four usable mode names.

## Processing button and presets

A bounded processing-button round trip emits `0x14 / 0x98` with instance at17,
type at18 and state at19. De-Esser therefore needs its own catalog override
for the older unresolved generic layout. Instance0/type27 emits state0 at
frame2589 in `unattended-20261025-deesser-bypass-first/Orion.pcapng` and state1
at frame751 in `unattended-20261025-deesser-bypass-return/Orion.pcapng`.
The two reports differ only at19, and the restored button's RGB pixels match
the baseline exactly. Independent processing-state readback and polarity remain
unverified; no runtime bypass writer is enabled.

Preset inspection `panel-Master-De-Esser-20261025T010018355Z` records six visible
names: BV Elec Hi Hat, BV Female S 2, BV Reduce High Freq, BV Slap Bass,
BV Subtle Female S and BV Typical S. Opening and Escape-closing the menu leaves
BV Elec Hi Hat selected and produces no outbound control report. Presets were
not swept; the inventory does not establish hidden or virtualized entries or
parameter vectors for those names.
