"use strict";

// Original presentation; the shared catalog owns model-local control metadata.
AFX_PANELS.set('pultec_eqp', {
  label: 'VEQ-1A',
  category: 'EQ & Filters',
  stylesheet: '/webui/static/afx-captured.css?v=afx-captured-v9',
  render: (draft, slot) => afxCapturedHTML(draft, slot, 'veq1a'),
  update: afxCapturedUpdate,
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
