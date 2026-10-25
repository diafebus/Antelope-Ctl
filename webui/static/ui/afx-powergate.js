"use strict";

// Original presentation; the shared catalog owns model-local control metadata.
AFX_PANELS.set('powergate', {
  label: 'PowerGate',
  category: 'Dynamics',
  stylesheet: '/webui/static/afx-captured.css?v=afx-captured-v1',
  render: (draft, slot) => afxCapturedHTML(draft, slot, 'powergate', 'GATE / HOLD'),
  update: afxCapturedUpdate,
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
