"use strict";

// Original presentation; the shared catalog owns model-local control metadata.
AFX_PANELS.set('powerex', {
  label: 'PowerEx',
  category: 'Dynamics',
  stylesheet: '/webui/static/afx-captured.css?v=afx-captured-v9',
  render: (draft, slot) => afxCapturedHTML(draft, slot, 'powerex'),
  update: afxCapturedUpdate,
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
