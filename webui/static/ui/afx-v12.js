"use strict";

// V12's two-row rack. Metadata comes from the shared catalog, not this panel.
AFX_PANELS.set('turboensembler', {
  label: 'V12 Chorus',
  stylesheet: '/webui/static/afx-modulation.css?v=afx-modulation-v1',
  render: (draft, slot) => afxModulationHTML(draft, slot, 'v12'),
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
