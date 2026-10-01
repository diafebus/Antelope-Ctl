# Orion Studio Synergy Core startup

The Orion profile records the Windows Launcher's ordered readback requests in `frame.readback.startup_queries`. Each entry contains a hexadecimal `category` and an integer `index`.

Preserve the array order and duplicates. Do not reconstruct startup from `category_counts`. The list contains queries only, not a complete executable initialization sequence. The current Python CLI does not automatically replay this metadata.

## Capture evidence

Offline comparison on 2026-09-06 used these private captures:

- `AntelopeINIT.pcapng`, Windows, query frames 15688 through 20134.
- `macos-antelopeINIT-poweron.pcapng`.
- `macos-antelopeINIT-poweron1-itresettopreviousstate.pcapng`.
- `macos-antelopeINIT-poweroff-on2-itsavedstate.pcapng`.
- `macos-antelopeINIT-poweroff-on3-itsavedstate.pcapng`.

Windows contains 113 queries and 113 readback replies. Each macOS capture contains 209 queries and 209 replies. Raw captures and device serial values are not included, following [SCOPE.md](../SCOPE.md).

All control payloads are 320 bytes. Requests use endpoint `0x01` OUT; responses use `0x82` IN. Darwin captures expose outgoing payloads on completion records. Use the endpoint direction bit, not the displayed source label, to determine direction.

## Windows order

| Step | Category | Indices |
| --- | --- | --- |
| Assignment status / feature mask | `0x11` | 0, 1 |
| ADAT and S/PDIF link tables | `0x0b` | 1, 2 |
| Observed startup command | Not a query | See below |
| Surround global | `0x1b` | 0 |
| Surround speaker EQ | `0x1a` | 0 through 15 |
| Routing | `0x03` | 0 through 14 |
| Mixers | `0x04` | 0 through 3, each followed by the mixer-link table `0x0b:3` |
| Gazelle Reverb (`0x0a`, AuraVerb protocol) | `0x0a` | 0 |
| Remaining featured AFX instances | `0x15` | 0 |
| Preamp link flags (six pairs) | `0x0b` | 0 |
| Mic-emulation state | `0x16` | 0 |
| AFX strip order | `0x19` | 0 through 63 |
| AFX link table / closing marker | `0x0b` | 4 |

The global Surround record at category `0x1b`, index 0 includes the EQ
PRE/POST state and is the fresh-read source for the profile's bounded global
writes. The EQ-position control changes only capture-backed flags-B bit 7;
the official-Launcher transition and the correction to the earlier flags-A
probe are documented in `PROTOCOL.md` and
`tools/surround_eq_position_selftest.py`.

Category `0x0b` occurs eight times with indices `1,2,3,3,3,3,0,4`.
These are five selectors, not eight records. Index 0 has six Preamp flags,
index 1 eight ADAT flags, index 2 one S/PDIF flag, index 3 64 mixer flags,
and index 4 32 AFX table entries. The 16 channel-pair selectors for Orion's
32 user-facing AFX channels map to entries 0–15; entries 16–31 remain
unmapped. Repeated mixer reads do not expand query bounds:
`category_counts` remains 5, permitting outer indices 0–4 only.

Direct device tests and Windows VM checks on 2026-09-30 confirmed input
write spaces 0=Preamp, 1=ADAT, 2=S/PDIF and matching link-table indices.
All eight ADAT selectors were individually toggled/restored; all-ON ADAT
and S/PDIF ON states were deliberately retained for VM confirmation. Earlier
Launcher digital buttons emitted incorrect write spaces; their old tests
and the old WebUI mapped those replies to the wrong domains. The corrected
profile supplies separate authoritative mappings for all three input banks.
These results do not alter the startup walk, bounds, or establish retention
through a device power cycle. See [PROTOCOL.md](../PROTOCOL.md) §4/§7.

Direct AFX trials on 2026-10-01 toggled each space-4 pair 0–15 ON/OFF,
comparing all five safe link tables and restoring their original values after
every trial. Only the corresponding `0x0b:4` byte changed. The WebUI uses
this confirmed mapping for the pair button and linked-channel menu labels.
Reconnect clears the cached AFX flags and slot inventory before polling the
new connection; opening/refreshing the rack requests fresh selected-channel
slots and link flags. This changes neither the startup query order nor its
bounds and does not introduce default link or effect writes.

The other nested response shapes are also recorded in
`frame.readback.record_layouts`: category `0x16` index 0 contains eight
mic-emulation records; category `0x19` contains eight AFX slots per strip;
category `0x15` contains 91 remaining-instance counters. Mono load/remove
trials verified write-channel/readback-index correspondence on indices 2–31,
with original chains restored; index 0 was owner-tested earlier. Index 1 mono
writes and storage indices 32–63 were not exercised by those trials. The
loader waits for the complete 64-record inventory before allocating an
instance, and counters describe remaining resources rather than licenses. Category `0x0c`
has a schema-defined available/max table shape, but its outer query bounds
are intentionally not added until a device capture confirms them.

## Observed startup command

All five captures contain opcode `0x13`, parameter `0x49`, channel 1, value 0, after marker `0x0b:2`. Windows frame 15784 carries this command at 7.713707 seconds. The macOS poweron capture carries it in frame 12467 at 22.537315 seconds.

The profile documents this command separately under `frame.init_enumeration_report.startup_command`. Its semantics and necessity remain unverified. This change does not execute it. A consumer must not assume that replaying `startup_queries` alone reproduces every startup action.

## macOS differences and limits

macOS additionally queries firmware/identity categories `0x00` and `0x01`, plus `0x12`, at index 0. It performs two routing, mixer, and stream passes. Surround queries occur between those passes, rather than before the first routing pass as on Windows.

The profile preserves the Windows query sequence, not a merged or deduplicated sequence. These observations do not prove that every macOS request is required. Capture-specific gain restoration writes are not startup defaults and must not be replayed blindly.

The original startup-capture analysis did not establish Linux hidraw report-ID
handling, minimum delays, or the cause of a reported HID write timeout. It
performed no hardware writes. The later authorized link/chain trials above
are separate evidence; see [PROTOCOL.md §12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls).

## Offline regression checks

Run from the repository root:

```sh
python3 -m unittest tools.test_orion_startup
```

Tests verify exact query order, repeated markers, report encoding, and rejection of unobserved marker indices. They use sanitized category/index facts and do not open hardware.
