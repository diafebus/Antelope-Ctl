"use strict";

// Memory Cat Brigade presentation only. No device commands or runtime handles.

function afxMemoryCatHTML(draft, slot) {
  // The faceplate's action order supplies labels; its artwork is not reused.
  const order = ['level', 'blend', 'feedback', 'delay', 'depth', 'lpf_fc'];
  const knobs = order.map(id => draft.effect.controls.find(c => c.id === id)).filter(Boolean);
  const modes = draft.effect.controls.filter(control => control.kind === 'enum');
  return '<div class="afx-effect-face afx-compact-panel">'
    + afxPanelIdentityHTML(draft, slot)
    + `<div class="afx-panel-content"><div class="afx-knob-bank">${knobs.map(c => afxEffectControlHTML(c, draft.values[c.id], slot, draft.live, !draft.live || draft.parameterAvailable)).join('')}</div>`
    + `<div class="afx-mode-bank">${modes.map(c => afxEffectControlHTML(c, draft.values[c.id], slot, draft.live, !draft.live || draft.parameterAvailable)).join('')}</div>`
    + (draft.live ? `<div class="afx-live-status" data-afx-live-state="${draft.instance}"><span>${afxMemoryCatLiveMessage(draft)}</span>`
      + `<button type="button" class="afx-preview-open" data-afx-device-resume="${slot}"${draft.livePaused ? '' : ' hidden'}>Retry live controls</button></div>` : '')
    + '</div></div>';
}

function afxMemoryCatLiveMessage(draft) {
  return (draft.livePaused ? 'Live controls paused after a failed send.'
    : !draft.parameterAvailable ? 'Device settings unavailable · controls wait for a fresh readback.'
    : draft.parameterSource === 'readback' ? `Live controls · device settings · ${draft.bypassed ? 'bypassed' : 'active'}.`
    : 'Live controls · last sent settings.');
}

function afxMemoryCatUpdateLiveStatus(draft, doc) {
  const group = doc.getElementById('afx-rack')?.querySelector?.(`[data-afx-live-state="${draft.instance}"]`);
  if (!group) return;
  group.querySelector('span').textContent = afxMemoryCatLiveMessage(draft);
  group.querySelector('button').hidden = !draft.livePaused;
  const bypass = group.closest?.('.afx-effect-face')?.querySelector('[data-afx-bypass-state]');
  if (bypass) bypass.textContent = `Bypass: ${typeof draft.bypassed === 'boolean' ? draft.bypassed ? 'On' : 'Off' : 'Unknown'}`;
}


AFX_PANELS.set('memory_brigade', {
  label: 'Memory Cat Brigade',
  stylesheet: '/webui/static/afx-memorycat.css?v=afx-memorycat-v9',
  render: afxMemoryCatHTML,
  updateLiveStatus: afxMemoryCatUpdateLiveStatus,
  input: afxEffectInput,
  click: afxEffectClick,
  pointerDown: afxEffectPointerDown,
});
