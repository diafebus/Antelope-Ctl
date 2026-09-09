# Device-specific WebUI features

The protocol profiles under `profiles/` describe hardware addresses, frame
layouts, ranges, and safety limits. Product-specific presentation belongs in
`webui/device_ui.py` instead. That registry is intentionally small: it only
decides which panel is visible and supplies labels for controls whose visual
layout differs between products.

Current entries:

- `zen_go_sc`: shows the Zen Go mixer input-source selectors above its 16
  strips. The selectors are read-only until the Zen Go routing readback is
  captured and bounded; the routing command rewrites a whole group, so the UI
  must not guess the other 15 sources.
- `orion_studio_sc`: shows the AuraVerb button and panel on Mix 1. AuraVerb's
  wire command and readback remain in the Orion protocol profile; the panel is
  closed by default.

Adding a device-specific panel should add a registry entry and a capability
check, without changing the shared Orion mixer markup or copying protocol
constants into the browser.
