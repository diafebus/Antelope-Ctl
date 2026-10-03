"use strict";

// Shared presentation and gesture primitives; the rack owns device state.
function afxEffectDisplayValue(control, value) {
  return value == null ? '—' : String(value - (control.display_center || 0));
}

function afxEffectControlHTML(control, value, slot, live = false, ready = true) {
  const id = afxEscape(control.id), label = afxEscape(control.label);
  const scope = live ? 'device test draft' : 'local preview';
  if (control.kind === 'continuous') {
    const [min, max] = control.range;
    const known = value != null;
    const fraction = known ? (value - min) / (max - min) : 0;
    return `<label class="afx-effect-control${known ? '' : ' unknown'}${ready ? '' : ' blocked'}" style="--afx-turn:${-135 + fraction * 270}deg;--afx-fill:${fraction * 270}deg">`
      + `<span class="afx-control-label">${label}</span>`
      + `<span class="afx-knob" aria-hidden="true" data-afx-knob="${id}" data-afx-slot="${slot}"><span class="afx-knob-cap"><span class="afx-knob-pointer"></span></span></span>`
      + `<input class="afx-knob-input" type="range" min="${min}" max="${max}" step="1" value="${known ? value : min}"${ready ? '' : ' disabled'}`
      + ` aria-label="${label}, ${scope}" data-afx-control="${id}" data-afx-slot="${slot}">`
      + `<span class="afx-control-value"><output>${afxEffectDisplayValue(control, value)}</output><span> / ${max - (control.display_center || 0)}</span></span></label>`;
  }
  return `<div class="afx-mode-control"><span class="afx-control-label">${label}</span>`
    + `<div class="afx-mode-options" role="group" aria-label="${label}, ${scope}">`
    + Object.entries(control.options).map(([key, text]) =>
      `<button type="button" class="afx-mode-button" aria-pressed="${value === key}"${ready ? '' : ' disabled'}`
      + ` data-afx-mode="${id}" data-afx-value="${afxEscape(key)}" data-afx-slot="${slot}">${afxEscape(text)}</button>`).join('')
    + '</div></div>';
}


function afxEffectInput(draft, input) {
  if (input.disabled || draft.live && !draft.parameterAvailable) return;
  const control = draft.effect.controls.find(c => c.id === input.dataset.afxControl);
  const parent = draft.effect.panel?.dependencies?.[control?.id];
  if (parent && !(draft.values[parent] > 0)) return;
  const value = Number(input.value);
  if (!control || control.kind !== 'continuous' || !Number.isSafeInteger(value)
      || value < control.range[0] || value > control.range[1]) return;
  draft.values[control.id] = value;
  const group = input.closest('.afx-effect-control');
  const fraction = (value - control.range[0]) / (control.range[1] - control.range[0]);
  group.style.setProperty('--afx-turn', `${-135 + fraction * 270}deg`);
  group.style.setProperty('--afx-fill', `${fraction * 270}deg`);
  group.querySelector('output').textContent = afxEffectDisplayValue(control, value);
  afxEffectDependencies(draft, input.ownerDocument);
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxEffectClick(draft, event) {
  if (draft.live && !draft.parameterAvailable) return;
  const button = event.target.closest('[data-afx-mode]');
  if (!button || button.disabled) return;
  const control = draft?.effect.controls.find(c => c.id === button.dataset.afxMode);
  if (!control?.options || !Object.hasOwn(control.options, button.dataset.afxValue)) return;
  draft.values[control.id] = button.dataset.afxValue;
  for (const option of button.parentElement.querySelectorAll('button'))
    option.setAttribute('aria-pressed', String(option === button));
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxEffectPointerDown(draft, event) {
  if (draft.live && !draft.parameterAvailable) return;
  const knob = event.target.closest('[data-afx-knob]');
  if (!knob || event.button !== 0) return;
  const input = knob.closest('.afx-effect-control').querySelector('input');
  if (input.disabled) return;
  const control = draft.effect.controls.find(c => c.id === input.dataset.afxControl);
  if (!control) return;
  event.preventDefault();
  const startY = event.clientY, startValue = Number(input.value), pointer = event.pointerId;
  knob.setPointerCapture(pointer);
  const move = next => {
    if (next.pointerId !== pointer) return;
    input.value = String(Math.max(control.range[0], Math.min(control.range[1],
      Math.round(startValue + (startY - next.clientY) * (next.shiftKey ? .1 : .5)))));
    afxEffectInput(draft, input);
  };
  const finish = next => {
    if (next.pointerId !== pointer) return;
    knob.removeEventListener('pointermove', move);
    knob.removeEventListener('pointerup', finish);
    knob.removeEventListener('pointercancel', finish);
    if (knob.hasPointerCapture(pointer)) knob.releasePointerCapture(pointer);
  };
  knob.addEventListener('pointermove', move);
  knob.addEventListener('pointerup', finish);
  knob.addEventListener('pointercancel', finish);
}

function afxEffectDependencies(draft, doc) {
  if (!doc?.querySelectorAll) return;
  for (const [id, parent] of Object.entries(draft.effect.panel?.dependencies || {})) {
    for (const input of doc.querySelectorAll(`[data-afx-control="${id}"]`)) {
      if (input.dataset.afxSlot !== String(draft.slot)) continue;
      const blocked = draft.live && !draft.parameterAvailable || !(draft.values[parent] > 0);
      input.disabled = blocked;
      input.closest('.afx-effect-control').classList.toggle('blocked', blocked);
    }
  }
}

// Presentation only; no new runtime writer is connected by this renderer.
function afxModulationHTML(draft, slot, style) {
  draft.slot = slot;
  const panel = draft.effect.panel;
  const byId = new Map(draft.effect.controls.map(c => [c.id, c]));
  const ready = id => (!draft.live || draft.parameterAvailable)
    && (!panel.dependencies?.[id] || draft.values[panel.dependencies[id]] > 0);
  const control = id => afxEffectControlHTML(byId.get(id), draft.values[id], slot, draft.live, ready(id));
  return `<div class="afx-effect-face afx-modulation afx-${style}"><div class="afx-effect-heading">${afxPanelPositionHTML(slot)}<div>`
    + `<span class="afx-effect-family">SYNERGY CORE · MODULATION</span><h3>${afxEscape(draft.effect.name)}</h3></div>`
    + `<span class="afx-preview-badge">${draft.live ? 'Device settings unknown' : 'Local preview'}</span>`
    + `<button type="button" class="afx-preview-close" ${draft.live ? 'data-afx-device-remove' : 'data-afx-remove'}="${slot}" aria-label="${draft.live ? 'Remove effect from device' : 'Close local preview'}">×</button></div>`
    + '<div class="afx-modulation-body"><div class="afx-modulation-knobs">'
    + panel.rows.map(row => `<div class="afx-modulation-row">${row.map(control).join('')}</div>`).join('')
    + `</div><div class="afx-modulation-switches">${panel.switches.map(control).join('')}`
    + '<div class="afx-mode-control"><span class="afx-control-label">Power</span><button type="button" class="afx-mode-button" disabled>Unknown</button></div></div></div>'
    + '<div class="afx-modulation-meter">Output level unavailable</div>'
    + `<p class="afx-preview-note">${draft.live ? 'Parameter state unavailable · controls wait for verified readback. Load, move and remove use the captured rack contract.' : 'Local preview settings only · no device parameter or bypass writes.'}</p>`
    + (style === 'v12' ? '<p class="afx-preview-note">Colorize and Clr Shifter require Space above zero.</p>' : '')
    + '</div>';
}
