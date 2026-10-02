"use strict";

// BBD's four knobs and stereo/modulation switches; no invented wire polarity.
AFX_PANELS.set('bbdchorus', {
  label: 'BBD-Chorus',
  stylesheet: '/webui/static/afx-modulation.css?v=afx-modulation-v1',
  render: (draft, slot) => afxModulationHTML(draft, slot, 'bbd'),
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
