"use strict";

// Captured panel presentations. Values here are local drafts, never wire state.
function afxCapturedHTML(draft, slot, style) {
  draft.slot = slot;
  const byId = new Map(draft.effect.controls.map(control => [control.id, control]));
  const control = id => afxEffectControlHTML(byId.get(id), draft.values[id], slot,
    draft.live, afxEffectReady(draft, id));
  const bypassed = draft.values.processing === '0';
  const switches = draft.effect.panel.switches.filter(id => id !== 'processing');
  return `<div class="afx-effect-face afx-compact-panel afx-captured-panel afx-face-${style}${bypassed ? ' is-bypassed' : ''}" data-afx-panel-slot="${slot}" data-afx-panel-effect="${afxEscape(draft.effect.id)}">`
    + afxPanelIdentityHTML(draft, slot, byId.has('processing') ? control('processing') : '', !draft.live || draft.removable)
    + '<div class="afx-panel-content"><div class="afx-captured-banks">'
    + draft.effect.panel.rows.map(row => `<div class="afx-captured-row">${row.map(control).join('')}</div>`).join('')
    + '</div>'
    + (switches.length ? `<div class="afx-captured-switches">${switches.map(id => id === 'ctrl' && draft.effect.id === 'deesser'
      ? `<div class="afx-unmapped-control"><span class="afx-control-label">Monitor / Out</span><span>Mode meanings unverified</span><select data-afx-control="ctrl" data-afx-slot="${slot}" aria-label="Monitor modes unidentified" disabled><option>Unidentified</option></select></div>` : control(id)).join('')}</div>` : '')
    + '</div></div>';
}

function afxCapturedUpdate(draft, doc) {
  const root = doc?.querySelector?.(`[data-afx-panel-slot="${draft.slot}"]`);
  if (!root || root.dataset.afxPanelEffect !== draft.effect.id) return;
  root.classList.toggle('is-bypassed', draft.values.processing === '0');

}
