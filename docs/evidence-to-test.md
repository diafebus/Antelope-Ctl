# Worked example: a bounded Orion startup query

This example follows an existing readback fact without accessing hardware.
The observed action is the Windows Launcher connecting to Orion Studio Synergy
Core. [The startup findings](orion-startup.md#capture-evidence) cite private
`AntelopeINIT.pcapng`, query frames **15688–20134**, compared offline on
**2026-09-06** with four macOS startup captures. Windows has 113 query/reply
pairs; its first query is category `0x11`, index `0` (assignment status).
The published provenance identifies the capture range; it does not assign an
individual frame number to each query. Raw captures and identity replies are
not distributed.

## Minimal wire facts

Requests are 320-byte control payloads on endpoint `0x01` OUT. The documented
request envelope has magic `0x74` at byte 0, LE32 subcommand `0x10` at byte 4,
category at byte 8 and index at byte 12; padding begins at byte 16.

For category `0x11`, index `0`, the reconstructed request is:

```text
offset 00: 74 00 00 00 10 00 00 00 11 00 00 00 00 00 00 00
offset 16: 304 zero bytes
```

This is a **reconstruction from published captured fields**, not a newly
extracted raw frame or fresh hardware verification. It contains no serial,
account fields, reply contents or unrelated traffic. Synthetic reply bodies in
other tests must be labelled synthetic rather than presented as capture excerpts.

## Profile to builder to regression

In [the Orion profile](../profiles/orion_studio_sc.json):

- `transport.report_size` supplies 320.
- `frame.readback` supplies request magic, offsets and subcommand.
- `frame.readback.startup_queries[0]` records category `0x11`, index `0`.
- `frame.readback.category_counts["0x11"]` bounds that category to two records.

`protocol.build_readback_query(profile, 0x11, 0)` first checks the index with
`check_readback_index`, then builds the request from these fields. It creates
bytes only; transport is a separate layer. Startup metadata is not an automatic
replay program and omits the observed non-query command.

The existing
[`OrionStartupTests.test_windows_query_order_and_repeated_markers`](../tools/test_orion_startup.py)
compares the entire ordered list (including repeated mixer-link markers) to
sanitized capture facts, then checks each generated frame's length, header,
category, index and zero padding. Its neighboring test rejects link-table
indices 5–7: five outer tables allow indices 0–4, regardless of nested counts.

Run those checks from the repository root:

```sh
python3 -m unittest tools.test_orion_startup
python3 tools/offline_checks.py
```

No hardware or capture archive is read. Passing proves that profile and builder
still reproduce the documented requests and enforce the tested bounds. It does
not prove that replaying startup is necessary, that an undocumented index is safe,
or that a device setting survived a physical power cycle.
