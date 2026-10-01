"use strict";

// Memory Cat Brigade presentation only. No device commands or runtime handles.
function afxMemoryCatControlHTML(control, value, slot, live = false) {
  const id = afxEscape(control.id), label = afxEscape(control.label);
  const scope = live ? 'device test draft' : 'local preview';
  if (control.kind === 'continuous') {
    const [min, max] = control.range;
    const fraction = (value - min) / (max - min);
    return `<label class="afx-effect-control" style="--afx-turn:${-135 + fraction * 270}deg;--afx-fill:${fraction * 270}deg">`
      + `<span class="afx-control-label">${label}</span>`
      + `<span class="afx-knob" aria-hidden="true" data-afx-knob="${id}" data-afx-slot="${slot}"><span class="afx-knob-cap"></span></span>`
      + `<input type="range" min="${min}" max="${max}" step="1" value="${value}"`
      + ` aria-label="${label}, ${scope}" data-afx-control="${id}" data-afx-slot="${slot}">`
      + `<span class="afx-control-value"><output>${value}</output><span> / ${max}</span></span></label>`;
  }
  return `<div class="afx-mode-control"><span class="afx-control-label">${label}</span>`
    + `<div class="afx-mode-options" role="group" aria-label="${label}, ${scope}">`
    + Object.entries(control.options).map(([key, text]) =>
      `<button type="button" class="afx-mode-button" aria-pressed="${value === key}"`
      + ` data-afx-mode="${id}" data-afx-value="${afxEscape(key)}" data-afx-slot="${slot}">${afxEscape(text)}</button>`).join('')
    + '</div></div>';
}

function afxMemoryCatHTML(draft, slot) {
  // The faceplate's action order supplies labels; its artwork is not reused.
  const order = ['level', 'blend', 'feedback', 'delay', 'depth', 'lpf_fc'];
  const knobs = order.map(id => draft.effect.controls.find(c => c.id === id)).filter(Boolean);
  const modes = draft.effect.controls.filter(control => control.kind === 'enum');
  return `<div class="afx-effect-face"><div class="afx-effect-heading">${afxPanelPositionHTML(slot)}<div>`
    + '<span class="afx-effect-family">GAZELLE · DELAY</span>'
    + `<h3>${afxEscape(draft.effect.name)}</h3></div><span class="afx-preview-badge">${draft.live ? 'Device test' : 'Local preview'}</span>`
    + `<button type="button" class="afx-preview-close" ${draft.live ? 'data-afx-device-remove' : 'data-afx-remove'}="${slot}" aria-label="${draft.live ? 'Remove Memory Cat from the device' : 'Close local preview'}">×</button></div>`
    + `<div class="afx-effect-controls"><div class="afx-knob-bank">${knobs.map(c => afxMemoryCatControlHTML(c, draft.values[c.id], slot, draft.live)).join('')}</div>`
    + `<div class="afx-mode-bank">${modes.map(c => afxMemoryCatControlHTML(c, draft.values[c.id], slot, draft.live)).join('')}</div></div>`
    + (draft.live ? `<div class="afx-test-apply"><button type="button" class="afx-preview-open" data-afx-device-apply="${slot}">Apply all settings</button>`
      + `<span>${draft.liveReady ? 'Knobs send live · last sent values, no parameter readback.' : 'Apply once to initialize live knobs · current parameter readback unavailable.'} Switch A/B labels await confirmation.</span></div>`
      : '<p class="afx-preview-note">Preview settings only · effect loading and device controls are not connected.</p>')
    + '</div>';
}

function afxMemoryCatInput(draft, input) {
  const control = draft.effect.controls.find(c => c.id === input.dataset.afxControl);
  const value = Number(input.value);
  if (!control || control.kind !== 'continuous' || !Number.isSafeInteger(value)
      || value < control.range[0] || value > control.range[1]) return;
  draft.values[control.id] = value;
  const group = input.closest('.afx-effect-control');
  const fraction = (value - control.range[0]) / (control.range[1] - control.range[0]);
  group.style.setProperty('--afx-turn', `${-135 + fraction * 270}deg`);
  group.style.setProperty('--afx-fill', `${fraction * 270}deg`);
  group.querySelector('output').textContent = String(value);
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxMemoryCatClick(draft, event) {
  const button = event.target.closest('[data-afx-mode]');
  if (!button) return;
  const control = draft?.effect.controls.find(c => c.id === button.dataset.afxMode);
  if (!control?.options || !Object.hasOwn(control.options, button.dataset.afxValue)) return;
  draft.values[control.id] = button.dataset.afxValue;
  for (const option of button.parentElement.querySelectorAll('button'))
    option.setAttribute('aria-pressed', String(option === button));
  if (draft.live) AFX_DEVICE_RACK?.parameterChanged?.(draft);
}

function afxMemoryCatPointerDown(draft, event) {
  const knob = event.target.closest('[data-afx-knob]');
  if (!knob || event.button !== 0) return;
  const input = knob.closest('.afx-effect-control').querySelector('input');
  const control = draft.effect.controls.find(c => c.id === input.dataset.afxControl);
  if (!control) return;
  event.preventDefault();
  const startY = event.clientY, startValue = Number(input.value), pointer = event.pointerId;
  knob.setPointerCapture(pointer);
  const move = next => {
    if (next.pointerId !== pointer) return;
    input.value = String(Math.max(control.range[0], Math.min(control.range[1],
      Math.round(startValue + (startY - next.clientY) * (next.shiftKey ? .1 : .5)))));
    afxMemoryCatInput(draft, input);
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

AFX_PANELS.set('memory_brigade', {
  label: 'Memory Cat Brigade',
  stylesheet: '/webui/static/afx-memorycat.css?v=afx-memorycat-v2',
  render: afxMemoryCatHTML,
  input: afxMemoryCatInput,
  click: afxMemoryCatClick,
  pointerDown: afxMemoryCatPointerDown,
});
