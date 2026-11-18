"use strict";

// Shared presentation and gesture primitives; the rack owns device state.
function afxEffectDisplayValue(control, value) {
  return value == null ? '—' : control.decimals != null
    ? Number(value).toFixed(control.decimals) : String(value - (control.display_center || 0));
}

function afxEffectReady(draft, id) {
  if (draft.live && !draft.parameterAvailable) return false;
  const condition = draft.effect.panel?.dependencies?.[id];
  return !condition || (typeof condition === 'string' ? draft.values[condition] > 0
    : condition.values.includes(String(draft.values[condition.control])));
}

function afxEffectControlHTML(control, value, slot, live = false, ready = true) {
  const id = afxEscape(control.id), label = afxEscape(control.label);
  const scope = live ? 'device test draft' : 'local preview';
  if (control.kind === 'continuous' || control.rotary) {
    const keys = control.rotary ? Object.keys(control.options) : null;
    const [min, max] = keys ? [0, keys.length - 1] : control.range;
    const known = value != null;
    const fraction = known ? ((keys ? keys.indexOf(String(value)) : value) - min) / (max - min) : 0;
    return `<label class="afx-effect-control${known ? '' : ' unknown'}${ready ? '' : ' blocked'}" style="--afx-turn:${-135 + fraction * 270}deg;--afx-fill:${fraction * 270}deg">`
      + `<span class="afx-control-label">${label}</span>`
      + `<span class="afx-knob" aria-hidden="true" data-afx-knob="${id}" data-afx-slot="${slot}"><span class="afx-knob-cap"><span class="afx-knob-pointer"></span></span></span>`
      + (keys ? `<select class="afx-detent-select" data-afx-control="${id}" data-afx-slot="${slot}" aria-label="${label}, ${scope}"${ready ? '' : ' disabled'}>`
        + (!known ? '<option value="" selected disabled>Unknown</option>' : '')
        + keys.map(key => `<option value="${afxEscape(key)}"${String(value) === key ? ' selected' : ''}>${afxEscape(control.options[key])}</option>`).join('') + '</select>'
        : `<input class="afx-knob-input" type="range" min="${min}" max="${max}" step="${control.step || 1}" value="${known ? value : min}"${ready ? '' : ' disabled'}`
      + ` aria-label="${label}, ${scope}" data-afx-control="${id}" data-afx-slot="${slot}">`
      + `<span class="afx-control-value"><output>${afxEffectDisplayValue(control, value)}</output><span> / ${max - (control.display_center || 0)}</span></span>`)
      + '</label>';
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
  if (!control || !afxEffectReady(draft, control.id)) return;
  const value = control.rotary ? input.value : Number(input.value);
  if (control.rotary ? !Object.hasOwn(control.options, value)
      : control.kind !== 'continuous' || !Number.isFinite(value)
      || value < control.range[0] || value > control.range[1]
      || Math.abs((value - control.range[0]) / (control.step || 1)
        - Math.round((value - control.range[0]) / (control.step || 1))) > 1e-6) return;
  draft.values[control.id] = value;
  const group = input.closest('.afx-effect-control');
  const keys = control.rotary ? Object.keys(control.options) : null;
  const fraction = keys ? keys.indexOf(value) / (keys.length - 1)
    : (value - control.range[0]) / (control.range[1] - control.range[0]);
  group.style.setProperty('--afx-turn', `${-135 + fraction * 270}deg`);
  group.style.setProperty('--afx-fill', `${fraction * 270}deg`);
  if (!keys) group.querySelector('output').textContent = afxEffectDisplayValue(control, value);
  afxEffectDependencies(draft, input.ownerDocument);
  AFX_PANELS.get(draft.effect.id)?.update?.(draft, input.ownerDocument);
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxEffectClick(draft, event) {
  if (draft.live && !draft.parameterAvailable) return;
  const button = event.target.closest('[data-afx-mode]');
  if (!button || button.disabled) return;
  const control = draft?.effect.controls.find(c => c.id === button.dataset.afxMode);
  if (!control?.options || !Object.hasOwn(control.options, button.dataset.afxValue)
      || !afxEffectReady(draft, control.id)) return;
  draft.values[control.id] = button.dataset.afxValue;
  for (const option of button.parentElement.querySelectorAll('button'))
    option.setAttribute('aria-pressed', String(option === button));
  afxEffectDependencies(draft, button.ownerDocument);
  AFX_PANELS.get(draft.effect.id)?.update?.(draft, button.ownerDocument);
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxEffectPointerDown(draft, event) {
  if (draft.live && !draft.parameterAvailable) return;
  const knob = event.target.closest('[data-afx-knob]');
  if (!knob || event.button !== 0) return;
  const input = knob.closest('.afx-effect-control').querySelector('[data-afx-control]');
  if (input.disabled) return;
  const control = draft.effect.controls.find(c => c.id === input.dataset.afxControl);
  if (!control) return;
  event.preventDefault();
  const keys = control.rotary ? Object.keys(control.options) : null;
  const min = keys ? 0 : control.range[0], max = keys ? keys.length - 1 : control.range[1];
  const step = control.step || 1;
  const startY = event.clientY, startValue = keys ? keys.indexOf(input.value) : Number(input.value), pointer = event.pointerId;
  knob.setPointerCapture(pointer);
  const move = next => {
    if (next.pointerId !== pointer) return;
    const speed = keys ? .08 : control.step != null ? (max - min) / 240 : .5;
    const fine = next.shiftKey ? (!keys && control.step == null ? .2 : .1) : 1;
    const value = Math.max(min, Math.min(max, min + Math.round((startValue - min
      + (startY - next.clientY) * speed * fine) / step) * step));
    input.value = keys ? keys[Math.round(value)] : String(Number(value.toFixed(6)));
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
  for (const id of Object.keys(draft.effect.panel?.dependencies || {})) {
    for (const input of doc.querySelectorAll(`[data-afx-control="${id}"]`)) {
      if (input.dataset.afxSlot !== String(draft.slot)) continue;
      const blocked = !afxEffectReady(draft, id);
      input.disabled = blocked;
      input.closest('.afx-effect-control').classList.toggle('blocked', blocked);
    }
  }
}

// Shared compact face identity. Processing remains a local preview unless an
// existing panel explicitly supplies a runtime control; this adds no writer.
function afxPanelIdentityHTML(draft, slot, processing, removable = true) {
  const status = draft.live ? (draft.effect.local_presentation
    ? 'Device values unavailable' : draft.effect.id === 'memory_brigade' ? 'Device test' : 'Device settings unknown') : 'Local preview';
  const power = processing || `<span class="afx-bypass-state" data-afx-bypass-state title="Bypass cannot be changed by this panel">Bypass: ${draft.live && typeof draft.bypassed === 'boolean' ? draft.bypassed ? 'On' : 'Off' : 'Unknown'}</span>`;
  return `<aside class="afx-effect-heading afx-panel-identity"><div class="afx-panel-tools">${afxPanelPositionHTML(slot, removable)}`
    + `<button type="button" class="afx-preview-close" ${draft.live ? 'data-afx-device-remove' : 'data-afx-remove'}="${slot}"${removable ? '' : ' disabled'} aria-label="${draft.live ? 'Remove effect from device' : 'Remove local panel'}">×</button></div>`
    + `<h3>${afxEscape(draft.effect.name)}</h3><span class="afx-preview-badge" title="${afxEscape(status)}">${afxEscape(status)}</span>`
    + `<div class="afx-panel-processing">${power}</div></aside>`;
}

// Presentation only; no new runtime writer is connected by this renderer.
function afxModulationHTML(draft, slot, style) {
  draft.slot = slot;
  const panel = draft.effect.panel;
  const byId = new Map(draft.effect.controls.map(c => [c.id, c]));
  const control = id => afxEffectControlHTML(byId.get(id), draft.values[id], slot,
    draft.live, afxEffectReady(draft, id));
  const note = style === 'v12' ? 'Colorize and Clr Shifter require Space above zero.' : '';
  return `<div class="afx-effect-face afx-compact-panel afx-modulation afx-${style}" title="${afxEscape(note)}">`
    + afxPanelIdentityHTML(draft, slot)
    + '<div class="afx-panel-content"><div class="afx-modulation-knobs">'
    + panel.rows.map(row => `<div class="afx-modulation-row">${row.map(control).join('')}</div>`).join('')
    + `</div><div class="afx-modulation-switches">${panel.switches.map(control).join('')}</div></div></div>`;
}
