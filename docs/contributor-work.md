# Contributor work and current limits

This is the public contribution entry point, not the owner's local session queue.
Hardware development currently targets Orion Studio Synergy Core. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for setup and evidence requirements.

| State | Area | Boundary |
| --- | --- | --- |
| Working | Offline Python/Node checks | Run from a clean clone without hardware or private captures. They verify software contracts, not physical behavior. |
| Working within documented coverage | Orion CLI/WebUI input controls, routing, mixer, Gazelle Reverb and bounded Surround paths | Consult [PROTOCOL.md](../PROTOCOL.md) and the active profile for each control's evidence and restrictions. Some CLI state is a last-sent cache. |
| Experimental | Orion AFX captured-effect rack and Memory Cat controls | Five captured load IDs; Memory Cat parameter reads cover instances 0–2. Linked audible operation and reads 3–7 remain open. No general catalog writer. |
| Captured / runtime incomplete | V12, BBD, Instinct and Master De-Esser parameters | Labelled capture maps have different coverage. V12/BBD panels include previews; [De-Esser](orion-afx-deesser.md) now has a visible-control capture pass. Maps do not establish runtime parameter readers, writers or physical scaling. [AFX workflow](orion-afx-workflow.md) owns details. |
| Experimental | Vendor-UI capture automation | Offline budgets, checkpoints and reviewed recovery exist. Consecutive native plugin/gesture and interrupted/resumed acceptance remain incomplete. Partial capture is not full plugin support. |
| Unknown | Remaining device semantics | Classic category `0x07`, safe outer bounds for `0x0c`, some meters, talkback packing, higher-layout Surround semantics and newer firmware behavior need evidence. Do not probe unknown indices. |
| Outside current hardware scope | Other devices, kernel driver and entitlement/activation | Sibling profiles require independent evidence; resource counts do not establish licenses. See [SCOPE.md](../SCOPE.md). |

## Bounded contributions without a device

- Audit one documented profile field against its parser and schema description;
  correct discrepancies without expanding hardware claims or bounds.
- Add a focused malformed/truncated-response regression to an existing parser
  test, preserving unknown bytes and using explicitly synthetic fixtures.
- Improve one effect panel's keyboard accessibility or unknown-state rendering
  using local previews and the existing Node checks; keep effect modules separate.
- Turn an already documented finding into a small sanitized offline example,
  retaining its source references and distinguishing reconstructed bytes.

Coordinate new hardware work before selecting trials. Reuse recorded evidence
before requesting more captures. Larger module refactors and a broad AFX
documentation rewrite are deferred until the contracts stabilize.
