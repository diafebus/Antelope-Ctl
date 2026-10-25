"use strict";

// Captured panel presentations. Values here are local drafts, never wire state.
function afxCapturedHTML(draft, slot, style, subtitle) {
  draft.slot = slot;
  const byId = new Map(draft.effect.controls.map(control => [control.id, control]));
  const control = id => afxEffectControlHTML(byId.get(id), draft.values[id], slot,
    draft.live, afxEffectReady(draft, id));
  const bypassed = draft.values.processing === '0';
  return `<div class="afx-effect-face afx-captured-panel afx-face-${style}${bypassed ? ' is-bypassed' : ''}" data-afx-panel-slot="${slot}" data-afx-panel-effect="${afxEscape(draft.effect.id)}">`
    + `<div class="afx-effect-heading">${afxPanelPositionHTML(slot, !draft.live || draft.removable)}<div><span class="afx-effect-family">GAZELLE · ${afxEscape(draft.effect.panel.family || 'SYNERGY CORE')}</span>`
    + `<h3>${afxEscape(draft.effect.name)}</h3></div><span class="afx-preview-badge">${draft.live ? 'Device values unavailable' : 'Local preview'}</span>`
    + `<button type="button" class="afx-preview-close" ${draft.live ? 'data-afx-device-remove' : 'data-afx-remove'}="${slot}"${draft.live && !draft.removable ? ' disabled' : ''} aria-label="${draft.live ? 'Remove effect from device' : 'Remove local panel'}">×</button></div>`
    + `<div class="afx-captured-body"><aside class="afx-face-brand"><span class="afx-face-monogram">${afxEscape(subtitle.split(' / ')[0])}</span>`
    + `<span class="afx-face-subtitle">${afxEscape(subtitle)}</span><span class="afx-face-power${draft.live ? ' unknown' : ''}" data-afx-power aria-label="${draft.live ? 'Processing state unavailable' : bypassed ? 'Local bypass' : 'Local active'}"></span></aside>`
    + '<div class="afx-captured-banks">'
    + draft.effect.panel.rows.map(row => `<div class="afx-captured-row" style="--afx-columns:${row.length}">${row.map(control).join('')}</div>`).join('')
    + '</div></div>'
    + `<div class="afx-captured-switches">${draft.effect.panel.switches.map(control).join('')}</div>`
    + `<p class="afx-preview-note">${draft.live ? 'Controls wait for verified device values.' : 'Local panel · no audio processing or device changes.'}</p>`
    + (draft.effect.id === 'deesser' ? '<p class="afx-preview-note">Q is available with BandPass filters. Monitor position names are not yet identified.</p>' : '')
    + '</div>';
}

function afxCapturedUpdate(draft, doc) {
  const root = doc?.querySelector?.(`[data-afx-panel-slot="${draft.slot}"]`);
  if (!root || root.dataset.afxPanelEffect !== draft.effect.id) return;
  root.classList.toggle('is-bypassed', draft.values.processing === '0');
  root.querySelector('[data-afx-power]')?.setAttribute('aria-label',
    draft.live ? 'Processing state unavailable' : draft.values.processing === '0' ? 'Local bypass' : 'Local active');
}
