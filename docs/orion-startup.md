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
| S/PDIF | `0x11` | 0, 1 |
| Phase markers | `0x0b` | 1, 2 |
| Observed startup command | Not a query | See below |
| Surround global | `0x1b` | 0 |
| Surround speaker EQ | `0x1a` | 0 through 15 |
| Routing | `0x03` | 0 through 14 |
| Mixers | `0x04` | 0 through 3, each followed by marker `0x0b:3` |
| AuraVerb | `0x0a` | 0 |
| Table | `0x15` | 0 |
| Phase marker | `0x0b` | 0 |
| State record | `0x16` | 0 |
| Stream slots | `0x19` | 0 through 63 |
| Closing marker | `0x0b` | 4 |

Category `0x0b` occurs eight times, with indices `1,2,3,3,3,3,0,4`. Eight occurrences do not imply eight records. Its `category_counts` value is therefore 5, the exclusive upper bound for observed marker values 0 through 4. Indices 5 through 7 were absent from all five captures. The existing query validator now rejects those indices without a runtime code change.

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
