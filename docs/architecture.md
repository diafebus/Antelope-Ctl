# Architecture map

Device knowledge flows from JSON into builders/parsers and then into clients.
Hardware I/O belongs to the transport; browser code never opens the device.

```text
profiles/<model>.json ──> antelope/protocol.py ──> antelope/transport.py ──> HID
                                ↑                       ↑
                         antelope/cli.py ────────────────┘

browser modules <── SSE/snapshot + API replies ── webui/server.py
      │                                              │
      └── HTTP edits ──> API validation ──> command queue
                                                     │
                                      single Device worker
                                          │          ↑
                                 builders/transport  parsers/readbacks
                                          └── HID ───┘
```

| Owner | Responsibility and useful entry points |
| --- | --- |
| [Device profiles](../profiles/orion_studio_sc.json) | Report sizes, endpoints, command fields, ranges, safe query bounds, evidence and bounded runtime contracts. [Schema](profile-schema.md) explains the format; [protocol reference](../PROTOCOL.md) explains findings. |
| [Protocol](../antelope/protocol.py) | Profile loading, pure frame builders and parsers. `build_readback_query` enforces classic bounds through `check_readback_index`; record layouts describe nested payloads without expanding outer bounds. |
| [Transport](../antelope/transport.py) | HID discovery, opening, reading, writing and request/reply handling. It does not decide which new device commands are justified. |
| [CLI](../antelope/cli.py) | Resolves profiles and command arguments, builds frames, uses transport, displays decoded state. Some views use explicitly labelled local caches; those are not device readback. |
| [WebUI server](../webui/server.py) | FastAPI endpoints and `Device`: one background worker owns the transport and serializes queued operations, polling and readbacks. Browser requests do not create competing controllers. |
| [Device UI metadata](../webui/device_ui.py) | Derives browser-facing device capabilities and labels from the active profile. |
| [Browser](../webui/static/index.html) | Ordered modules in `static/ui/`; `core.js` supplies shared helpers, feature modules render controls, `boot.js` fans out state. SSE carries fast state; `rb_ver` signals slow-state refresh. No frontend build step. |

The server holds decoded state and serialized caches. A sent value and a verified
readback are distinct evidence. Verification is feature-specific: AFX pilot edits
compare slot/parameter replies, while other paths can update last-sent caches.
Do not describe every cache as verified state. Session/reconnect invalidation must
prevent stale AFX drafts from being replayed. Opening/refreshing reads state;
it does not send starting presets, parameters or bypass defaults.

## AFX layers

[profiles/afx_effects.json](../profiles/afx_effects.json) is an ordered manifest
with catalog-wide metadata. Each `profiles/afx/<effect_id>.json` file holds one
plugin's shared definition, model-specific encodings and capture provenance.
[antelope/catalog.py](../antelope/catalog.py) resolves the manifest into the
existing catalog dictionary for the WebUI and capture tools; it also accepts
legacy inline catalogs. The loader uses only the Python standard library.
[The exporter](../tools/export_afx_catalog.py) produces flat JSON for external
consumers without maintaining a second authored catalog. Resource counts and
catalog entries do not establish license ownership or enable runtime writes.
[antelope/afx.py](../antelope/afx.py) implements the explicitly bounded Orion
operator contracts; [webui/afx_test.py](../webui/afx_test.py) performs their
read/preflight/write/verify transactions through the existing worker.
[webui/afx_catalog.py](../webui/afx_catalog.py) prepares catalog data for clients.

Shared rack/state logic stays in `afx.js`, `afx-test.js` and `afx-live.js`;
effect presentation lives in separate Memory Cat, V12 and BBD modules, with
`afx-controls.js` sharing control primitives. Local previews are drafts.
Unverified or absent device parameters stay unknown/disabled. Tagged instance
queries use their own profile-declared tuples; after an uncorrelated timeout,
further instance reads stop until reconnect.

## Evidence tooling and checks

The [tool index](../tools/README.md) separates offline analyzers, read-only device
tools and write/restore trials. `tools/afx_vm_pilot.py` coordinates a passive
Linux recorder and the vendor-UI runner in `tools/windows/`. Gesture plans,
budgets and recovery evidence belong to that capture workflow, not the runtime
WebUI command queue. Successful GUI gestures do not promote a candidate into a
runtime reader/writer. Raw results remain private and ignored.

[tools/offline_checks.py](../tools/offline_checks.py) runs explicit Python and Node
checks with synthetic/sanitized fixtures and mocked boundaries. See the
[worked example](evidence-to-test.md) for how capture facts become reproducible
offline assertions. It does not test audible behavior, physical retention or
Windows gestures. Broad splits of the large protocol/CLI/server modules can wait
until AFX contracts settle; they are not required for a small contribution.
