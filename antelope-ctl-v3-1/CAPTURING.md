# Capturing USB traffic (Windows VM + USBPcap + tshark)

This project's discipline (see README's "Adding a new param") depends on
getting a **full, untruncated** 320-byte hex dump of a state report from
before and after a single, isolated change in the official Launcher.
This doc is that method, referred to elsewhere as "the Phase 1 doc's method."

Setup used for this project: Antelope Launcher runs in a Windows VM (on a
Linux host), where USBPcap + Wireshark capture the traffic. The control
script itself runs on the Linux host against the passed-through hardware.
tshark ships with Wireshark, so no separate install is needed on the VM.

## 1. Find tshark

Default path: `C:\Program Files\Wireshark\tshark.exe`. Confirm it works:

```
"C:\Program Files\Wireshark\tshark.exe" -v
```

If it's missing, rerun the Wireshark installer -> Modify -> ensure "TShark"
is checked. Add `C:\Program Files\Wireshark` to PATH to avoid typing the
full path every time.

## 2. Capture, then save the whole session

Capture with USBPcap + the Wireshark GUI as usual, changing **only** the
one thing you're investigating in the Launcher. Then **File -> Save As** the
whole capture as `.pcapng` (e.g. `C:\captures\gain_test.pcapng`).

Do NOT use the GUI's *Copy -> ...as text* on individual packets -- that's
Wireshark's plain-text export, and it truncates around ~110 of the 320
report bytes, hiding everything past roughly the first 90-110 bytes. This
is the single most common way to lose the data you actually need. Saving
the raw `.pcapng` and re-reading it with `tshark -x` (below) avoids this
entirely.

## 3. Find the two frame numbers

In the still-open Wireshark GUI packet list, note the `No.` column for the
state report (`0x73`, `URB_INTERRUPT in`) just **before** your action, and
the one just **after**. These `No.` values are the frame numbers tshark
filters on next.

## 4. Extract each as a full hex dump

```
tshark -r C:\captures\gain_test.pcapng -Y "frame.number==20946" -x > before.hex
tshark -r C:\captures\gain_test.pcapng -Y "frame.number==20950" -x > after.hex
```

- `-r` reads the saved capture file
- `-Y` is a display filter (here: just this one frame)
- `-x` prints the full hex+ASCII dump -- this is the part the plain-text
  export skips

Sanity-check by opening `before.hex`: the first line is a harmless one-line
packet summary (`tools/capture_diff.py` ignores non-hex lines automatically),
followed by the real dump, running the full 20 rows / 320 bytes:

```
0000  70 00 00 00 13 00 00 00 00 00 00 00 00 00 00 00   p...............
0010  00 4f 00 0c 00 00 00 00 00 00 00 00 00 00 00 00   .O..............
...
```

## 5. Move the files to Linux and diff

Move `before.hex` / `after.hex` to the Linux side (shared folder, scp, USB --
whatever you already use), then:

```
python3 tools/capture_diff.py before.hex after.hex --known-offset 49 --known-offset 61
```

Cross-check the changed offset(s) against what you actually did in the
Launcher before trusting it -- see README's "Adding a new param" for the
rest of the confirm workflow.

## Optional: dump everything at once

Instead of hunting frame numbers per-change, dump every 320-byte report in
a whole session in one shot, then search the output by timestamp:

```
tshark -r gain_test.pcapng -Y "usb.data_len==320" -x > all_reports.txt
```

## Don't forget the OUTGOING commands, not just the readback

Everything above focuses on the state report (`0x73`, `URB_INTERRUPT in`) --
i.e. what changed. That's enough to find a new byte offset, but it does NOT
tell you the opcode, param_id, or exact frame layout the Launcher used to
*cause* that change. For that you need the outgoing command frames too
(`URB_INTERRUPT out`, magic `0x70`).

This matters more than it sounds like it should: don't assume every new
control uses the same `SET_PARAM` shape (`opcode 0x13`, `param_id@16`,
`channel@17`, `value@18`) as everything discovered so far. The channel-link
feature turned out to use a *different* opcode (`0x14`) with its two
"payload" bytes shifted one position later (`@18`/`@19` instead of
`@17`/`@18`) -- a state-report diff alone never would have revealed that;
only looking at the actual outgoing bytes did.

To capture both directions in one pass, use the same whole-session
`-T fields` dump from the "If your before/after diff comes back empty"
section below, but drop the magic restriction from the `-Y` filter and just
match on size -- `all_reports.tsv` will then contain a mix of `0x73` (state,
in), `0x75` (meter, in), and `0x70` (command, out) rows, all tab-separated
the same way. A quick one-liner to see just the outgoing commands:

```
awk -F'\t' 'substr($3,1,2)=="70"' all_reports.tsv
```

Then decode each row's `param_id`/payload bytes by hand (or with a small
throwaway script) against the frame layout in the profile -- start from
`frame.command`'s offsets, but verify byte-for-byte rather than assuming
they hold for a newly-discovered opcode.

## If your before/after diff comes back empty

The device polls constantly and resends the *same* report at rest -- if
you pick two frame numbers by eye, it's easy to land on two frames from
the same steady state (both before your action actually took effect, or
both after) and get a 0-byte diff even though the write worked.

Instead of hand-picking frame numbers, dump the whole session as
tab-separated fields (sidesteps hex-dump text formatting entirely, so
there's no truncation risk either) and let `tools/scan_capture.py` walk
every report in order and tell you exactly where something changed:

```
tshark -r session.pcapng -Y "usb.data_len==320" \
    -T fields -e frame.number -e frame.time_relative -e usb.capdata \
    > all_reports.tsv

python3 tools/scan_capture.py all_reports.tsv
```

It only looks at state reports (magic `0x73`) by default, since meter
reports (`0x75`, same 320-byte size) change on their own and would
otherwise drown out the real signal -- pass `--magic 0x75` if you're
specifically hunting meter offsets instead. It prints each frame-to-frame
transition with the exact offsets and old/new values; match the timestamp
against when you actually made your change in the Launcher.
