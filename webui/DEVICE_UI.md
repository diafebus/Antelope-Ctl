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
