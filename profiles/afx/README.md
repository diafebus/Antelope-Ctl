# AFX plugin definitions

Each `<effect_id>.json` file contains one plugin's shared controls and its
model-specific implementations, evidence and verification limits. Edit the
plugin file directly. IDs remain compatibility identifiers; filenames use
those exact IDs.

[../afx_effects.json](../afx_effects.json) owns catalog-wide metadata and the
ordered `effect_files` list. Add a reference there when adding a plugin.
Python consumers use `antelope.catalog.load_catalog(path)`; external consumers
can obtain flat JSON with `tools/export_afx_catalog.py`. Do not commit a
generated combined catalog or write it over the manifest.

See the [schema guide](../../docs/profile-schema.md#afx-and-the-shared-effect-catalog)
for storage/loading/export details and the
[capture workflow](../../docs/orion-afx-workflow.md#editing-captured-plugin-knowledge)
for evidence updates and migration of archived helpers. Catalog observations
retain model-specific wire evidence. The Zen Go and Discrete 4
`commands.parameters` blocks are available to the offline codec fixtures.
The shipped device profiles leave that codec disabled. Orion-derived selector
label candidates remain evidence for model-local verification.
