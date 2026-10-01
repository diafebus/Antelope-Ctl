# Device-specific WebUI features

The protocol profiles under `profiles/` describe hardware addresses, frame
layouts, ranges, and safety limits. Product-specific presentation belongs in
`webui/device_ui.py` instead. That registry is intentionally small: it only
decides which panel is visible and supplies labels for controls whose visual
layout differs between products.

The shared Protocol readback section is profile-driven and does not belong in
this registry. A profile may add `frame.readback.record_layouts` for nested
arrays such as link tables, mic-emulation state, or AFX slots. Only entries
whose outer index is capture-confirmed are polled; schema-only entries are
shown as capture-required. This keeps the presentation reusable without
copying a device's category numbers into the browser.

Input link indicators use a profile-declared
`frame.link_command.readback` mapping when a complete safe table is
available. Orion maps six Preamp pairs through `0x0b:0`, all eight ADAT
pairs through `0x0b:1`, and S/PDIF through `0x0b:2`. Input writers resolve
selectors from each profile bank's `link_pairs.space`: 0/1/2 on Orion.
Direct hardware transitions and Windows VM indicators confirmed the mapping
on 2026-09-30. The earlier digital write addresses and readback-domain
assignments were incorrect. A profile `cache_revision` clears old saved
input-link states once; complete readback repopulates the correct buttons.
The backend queries the matching table immediately after each link write.
Gain mirroring continues to use two per-channel writes in the browser.

Current entries:

- `zen_go_sc`: shows the Zen Go mixer input-source selectors above its 16
  strips and presents routing indices 6-9 as one logical 16-channel mixer
  input map. Those four capture-confirmed records are mirrored hardware views;
  a write reads all four, changes one slot, and writes each complete record
  back. The unrelated 8-channel/4-channel records (indices 3 and 5) are kept
  out of the WebUI destination list. A source bank that the profile cannot
  decode is shown as `DEVICE SOURCE 0xNN / N (UNMAPPED)` rather than being
  relabeled as a preamp or playback source.
- Gazelle Reverb is not a device-name registry entry. The button and panel
  are derived automatically from a profile's complete, confirmed
  `frame.auraverb_command` plus bounded readback contract, and are closed by
  default on Mix 1. This keeps the same WebUI code usable for another device
  once its profile supplies the confirmed wire layout.

Zen Go currently has no `frame.auraverb_command` or confirmed AuraVerb
readback layout. Its profile's `0x0a` entries are only observed query attempts,
not a decoded state record, so Gazelle Reverb stays hidden there until the Zen
Go profile is filled from device evidence. Orion's `0x1d/0xda` mapping is not
safe to reuse for Zen Go. The shared WebUI does use Zen Go's independently
confirmed surface selector, 16-lane mixer meter bank, and q0b/03 mixer-link
bitmap; it only replaces cached link state after receiving the complete 24-byte
response.

Adding a device-specific panel should add a registry entry and a capability
check, without changing the shared Orion mixer markup or copying protocol
constants into the browser.

## Orion AFX rack

Profiles with positive `afx.channel_count` and `afx.slots_per_channel` expose
the detachable AFX window. Orion declares 32 mono channels and eight slots;
its typed experimental operator contracts are `afx_rack_test` and
`afx_memorycat_test`. Other devices do not inherit these writers. Each effect
panel has its own files; `afx.js` owns the popup and shared drag behavior,
`afx-test.js` owns the selected device rack, and `afx-live.js` queues live
Memory Cat blocks. The effect dropdowns are categorized in the left slot list,
with a compact pair button in that channel header.

The API retains its original `memorycat-test` names for compatibility:

| Method/path | Request | Result/source |
|---|---|---|
| GET `/api/afx/catalog` | None | Local preview metadata, no device writes |
| GET `/api/afx/memorycat-test` | Optional `channel=0..31&refresh=true` | Cached rack state; refresh reads the selected chain and AFX link table when online |
| POST `/api/afx/memorycat-test/chain` | `channel`, `operation`, `slot`; `source` for move, `effect_id` for load/replace | Fresh selected-chain RMW with post-write verification |
| POST `/api/afx/memorycat-test/parameters` | `channel`, `instance`, complete eight-field `values` | Memory Cat block sent; acknowledged last-sent values, no parameter readback |
| POST `/api/afx/link` | `pair=0..15`, boolean `enabled` | Bare space-4 link flag with fresh readback verification |
| POST `/api/afx/memorycat-test/unlink` | None | Compatibility path for unlinking pair 0 only |

Chain and parameter requests require integer channel/slot/instance fields;
`channel` defaults to 0 for older clients, while the WebUI always supplies the
selection. Supported chain operations are load, replace, remove and move.
The `channels` object maps string channel indices 0–31 to slot arrays or null
when unavailable. The legacy `channel=0` and `slots` fields describe AFX 1.
Each slot contains `{type, instance}`; `{0,0}` is empty. `effects` includes
presentation categories and a `loadable` flag for the five independently
captured types, not license ownership or a generic write permission.

`links` contains 16 pair states; `link_readback` and `link_state_source`
distinguish device readback from a last-sent fallback. Direct 2026-10-01 trials
verified `link_pair_records`: pair N reads `0x0b:4` record N, for N=0..15.
Missing flags remain unknown; trailing records 16–31 are unmapped. AFX 1–2,
3–4, through 31–32 share the corresponding pair button and menu partner
labels. Only that pair must be OFF for mono changes. Link toggles preserve
both chains and do not reproduce the Launcher's extra assignments on unlink.
Stereo chain/parameter sharing remains unavailable.

`parameters` holds complete Memory Cat blocks last sent on the current
connection, keyed by instance. Initialize an instance with one complete Apply;
then knob and switch edits coalesce at 60 ms with one request in
flight and no rack repaint during dragging. Changing the selected channel or
connection discards mismatching queued edits; reordering preserves instance
settings, while load/replace requires fresh initialization. A/B switch labels
and parameter readback remain unconfirmed. A failed live write pauses sending
without retries.

`session` changes on device reconnect. The backend clears cached AFX inventory
and link flags, and the browser drops old parameter drafts. Allocation waits
for all 64 safe `0x19` storage records plus a fresh `0x15:0` resource counter.
A missing/mismatching post-write chain reply latches `writes_enabled=false`
for the server session; it does not attempt a blind repair. Read-only refresh
remains available and does not reset the latch. Scope and device-test limits
are recorded in [PROTOCOL.md §12a](../PROTOCOL.md#12a-afx-real-time-chain-and-parameter-controls).
