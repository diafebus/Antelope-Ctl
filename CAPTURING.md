# Capturing USB traffic (Windows VM + USBPcap + tshark)

This project's discipline (see README's "Adding a new param") depends on
getting a **full, untruncated** 320-byte hex dump of a state report from
before and after a single, isolated change in the official Launcher.
This doc is that method, referred to elsewhere as "the Phase 1 doc's method."

Setup used for this project: Antelope Launcher runs in a Windows VM (on a
Linux host), where USBPcap + Wireshark capture the traffic. The control
script itself runs on the Linux host against the passed-through hardware.
tshark ships with Wireshark, so no separate install is needed on the VM.

## Capturing on native macOS instead of the VM

Some Launcher features behave differently under the VM than on a native
host. **The VM Launcher silently no-ops some controls** -- "zero outgoing
frames under the VM" does NOT prove a feature is host-side. Confirmed
2026-08: screen brightness sends nothing under the VM but is a real
`0x12`/`0x0e` device command on native macOS (readback `0x73` @26).
Re-check every "host-side" verdict on native macOS. Capture there:

1. Install Wireshark (its installer adds the ChmodBPF helper for
   non-root capture).
2. Bring up the USB capture interfaces:
   `sudo ifconfig XHC20 up` (also try `XHC0`, `XHC1`, `XHC2` -- the Mac's
   XHCI controllers; the Antelope will be on one of them).
3. In Wireshark, capture on that `XHCxx` interface. **No display/size
   filter** -- capture everything, so nothing like the `0xab` surround-EQ
   frames is missed.
   **Check you are getting BOTH endpoints.** The device's vendor HID
   interface has an IN endpoint (`20.x.2`, carries `0x73`/`0x75`) and an
   OUT/interrupt endpoint (`20.x.1`, carries the host's `0x70` commands
   *and* the `0x74` enumeration). Several 2026-08 macOS matrix captures
   caught only `20.x.2` -- so they have the state reports but **none of
   the outgoing route commands**, making them useless for decoding a
   command frame. After capturing, run
   `tools/scan_macos_capture.py CAP.pcapng` and confirm the summary shows
   an `OUT magic 70 xN` line before you rely on the file.
4. **The macOS (Darwin XHC) frame format is NOT the same as USBPcap.**
   tshark does not populate `usbhid.data` / `usb.capdata` for these, so
   `tools/scan_capture.py` and its TSV recipe do not work directly. Each
   vendor HID report is a **40-byte Darwin pseudo-header + 320-byte
   payload** (`frame.len == 360`); the payload (byte 0 = the usual magic
   `0x70`/`0x73`/`0x74`/`0x75`) is `frame_raw[80:]`. Header byte 30 =
   endpoint (`0x01` OUT / `0x82` IN); VID/PID at header bytes 36-39.
   `usb.src`/`usb.dst` direction labels are unreliable -- identify
   outgoing frames by magic `0x70` + opcode at payload[4] instead.
   Use **`tools/scan_macos_capture.py`** (needs `tshark` on PATH):
   ```
   tools/scan_macos_capture.py CAP.pcapng                # outgoing cmds + 0x73 transitions
   tools/scan_macos_capture.py CAP.pcapng --magic 74     # dump one magic's transitions
   tools/scan_macos_capture.py CAP.pcapng --diff OTHER.pcapng   # per-magic final-state diff
   ```
   It does the 40-byte-header strip and `frame.len==360` filter itself.
   Under the hood: `tshark -r cap.pcapng -Y "frame.len==360" -T json -x`,
   then `bytes.fromhex(_source.layers.frame_raw[0])[40:]`.

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

## When you need more than the 320-byte reports

The `usb.data_len==320` filter is right for params, but it **drops USB
control transfers**. Also note: **keep the raw `.pcapng` files** (see
`captures/raw pcapng captures/`) -- once they're on the Linux side, any
re-filtering (both directions, other endpoints, USB metadata, control
transfers) is a local `tshark` command, no VM round-trip.

String descriptors are the only place the device's channel/bus/category
*names* live (e.g. for the `0x74` init-enumeration categories, `PROTOCOL.md`
section 4). **Heads-up (2026-08): none of the 21 captures on file contain a
single string-descriptor fetch** -- Windows had them cached. To get them,
you may need to remove the device in Device Manager first so Windows
re-enumerates fully, then capture the connect:

```
tshark -r connect.pcapng -Y "usb.transfer_type==2 || usb.descriptor_index" -x > control.txt
```

## Don't forget the OUTGOING commands, not just the readback

Everything above focuses on the state report (`0x73`, `URB_INTERRUPT in`) --
i.e. what changed. That's enough to find a new byte offset, but it does NOT
tell you the opcode, param_id, or exact frame layout the Launcher used to
*cause* that change. For that you need the outgoing command frames too
(`URB_INTERRUPT out`, magic `0x70`).

This matters more than it sounds like it should: don't assume every new
control uses the same `SET_PARAM` shape (`opcode 0x13`, `param_id@16`,
`channel@17`, `value@18`) as everything discovered so far. Several opcodes
are known now, and the payload layout differs per opcode (this table is a
quick copy -- `PROTOCOL.md` section 2 is the canonical version):

| opcode | name | layout | used by |
|---|---|---|---|
| `0x13` | SET_PARAM | `param@16`, `channel@17`, `value@18` | gain, mode, phantom, phase, bus_*, talkback_dest_assign |
| `0x14` | SET_LINK | `param@16` (`0xa2`), `pair_index@18`, `enabled@19` | channel_link, adat_channel_link |
| `0x12` | SET_GLOBAL | `param@16`, `value@17` (no channel byte), `@18` unused | talkback_button / _source / _gain |
| `0x53` | (routing?) | `param@16` (`0xd3`), multi-byte payload `@17+` -- not decoded | routing matrix (matrixtest capture) |

The channel-link feature was found because its bytes were shifted
(`@18`/`@19`); talkback's `0x12` was found because its value sits at `@17`
with no channel byte at all. A state-report diff alone never reveals any
of this -- only reading the actual outgoing bytes does.

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
throwaway script) against the frame layouts in the profile (`frame.command`,
`frame.link_command`, `frame.global_command`) -- check the opcode byte
(`@4`) first to pick the layout, then verify the payload byte positions
byte-for-byte rather than assuming they hold for a newly-discovered opcode.

A worked example of the full loop is the talkback work (2026-08): filter
`0x70` out-frames, see opcode `0x12` / param `0x1f`/`0x27`/`0x20` with the
value at `@17`; then for each command find the `0x73` state report just
before and after and diff -- talkback state landed in two bytes
(`73` packed status, `74` gain) sitting right after the 12-byte channel
status array. `tools/scan_capture.py` won't isolate this cleanly on its
own because the meter-jitter block (offsets 157-232) fires constantly;
diff the specific candidate offsets around each command timestamp instead.

**Readback is often bit-packed, and several sub-controls can share one
byte.** The output-trim capture (`settings-trim-...`, 2026-08) sends
`SET_PARAM(0x4b, target, value)` for targets 0/1/2; the readback is
`value << 4` at offset 24 for target 0, but `value << 2` and `value << 5`
in *the same* byte (offset 25) for targets 1 and 2. Talkback's offset 73
packs source, destination bitmask and the button bit together the same
way. So when a candidate byte moves: check whether the delta is the raw
value, `value << N`, or a single bit, and whether the untouched bits of
that byte might belong to a *different* sub-control you haven't captured
yet (offset 25 bits 0-1 are still spare -- probably pan law).

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
