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
| Link tables with S/PDIF record 0 and an unassigned byte | `0x0b` | 1, 2 |
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

Category `0x0b` occurs eight times, with indices `1,2,3,3,3,3,0,4`. These are five link-table selectors, not eight records: index 0 returns six Preamp-pair link flags; index 1 returns eight bytes, of which record 0 tracks the single S/PDIF pair; index 2 returns one unassigned byte; index 3 returns 64 mixer-pair states; and index 4 returns 32 AFX-link states. The Launcher repeats index 3 four times around mixer reads as a sequencing marker, but the response is still a real link table. Its `category_counts` value is therefore 5, the exclusive upper bound for observed outer indices 0 through 4. Indices 5 through 7 were absent from all five captures. The existing query validator rejects those indices.

A later controlled WebUI probe on 2026-09-23 captured `SET_LINK` space 0,
pair 3 on, followed by a bounded index-0 response whose record 3 changed to
1; a fresh response after off returned 0. Index-1 record 3 stayed 0 in both
states. Index 0 returns the six Preamp link states for the 12 physical
preamp inputs. ADAT has eight pairs, so these records are not its readback.
The old WebUI used them as ADAT state; that mapping was incorrect. ADAT pair
indices 6 and 7 have no identified readback byte. Controlled
direct-HID ON/OFF tests on 2026-09-26 changed none of the five known tables
for those pairs on a short read. Earlier tests also read index-0 record 4
while exercising ADAT pair 4, but index 0 is the Preamp table and that
comparison does not establish ADAT state. The previous ADAT loop was invalid.
This evidence does not change the startup query bounds or confirm ADAT link
state.
The user also verified the old WebUI after a hard reload: ADAT 7/8 showed ON,
then both ADAT 7/8 and physical Preamp 7/8 indicators showed OFF after the
OFF click and matching index-0 readback. Record 3 is the Preamp 7/8 pair;
using it for the ADAT indicator was incorrect and did not establish ADAT
link state.
ADAT 13/14 and 15/16 were also toggled ON and OFF. Their `SET_LINK` writes
use pair indices 6 and 7; neither direct test changed an index-1 record.
The table remains available in readback diagnostics but is not treated as
the link indicator for those pairs. A controlled S/PDIF OFF/ON test, with
ADAT held fixed, changed index-1 record 0 from 1 to 0 to 1. Index 2 stayed
zero, so it must not drive the S/PDIF button.

The other nested response shapes are also recorded in
`frame.readback.record_layouts`: category `0x16` index 0 contains eight
mic-emulation records; category `0x19` contains eight AFX slots per strip;
category `0x15` contains 91 remaining-instance counters. Category `0x0c`
has a schema-defined available/max table shape, but its outer query bounds
are intentionally not added until a device capture confirms them.

## Observed startup command

All five captures contain opcode `0x13`, parameter `0x49`, channel 1, value 0, after marker `0x0b:2`. Windows frame 15784 carries this command at 7.713707 seconds. The macOS poweron capture carries it in frame 12467 at 22.537315 seconds.

The profile documents this command separately under `frame.init_enumeration_report.startup_command`. Its semantics and necessity remain unverified. This change does not execute it. A consumer must not assume that replaying `startup_queries` alone reproduces every startup action.

## macOS differences and limits

macOS additionally queries firmware/identity categories `0x00` and `0x01`, plus `0x12`, at index 0. It performs two routing, mixer, and stream passes. Surround queries occur between those passes, rather than before the first routing pass as on Windows.

The profile preserves the Windows query sequence, not a merged or deduplicated sequence. These observations do not prove that every macOS request is required. Capture-specific gain restoration writes are not startup defaults and must not be replayed blindly.

Capture analysis does not establish Linux hidraw report-ID handling, minimum delays, or the cause of a reported HID write timeout. No hardware writes were performed for this change.

## Offline regression checks

Run from the repository root:

```sh
python3 -m unittest tools.test_orion_startup
```

Tests verify exact query order, repeated markers, report encoding, and rejection of unobserved marker indices. They use sanitized category/index facts and do not open hardware.
