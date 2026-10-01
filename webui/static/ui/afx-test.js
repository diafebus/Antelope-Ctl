"use strict";

// Operator-driven Orion pilot. Device slots and local previews stay distinct.
let AFX_TEST_STATE = null;
let AFX_TEST_BUSY = false;
let AFX_TEST_SESSION = null;
let AFX_TEST_DEVICE_VIEW = false;
let AFX_TEST_CHOICES = [];
const AFX_TEST_DRAFTS = new Map();

function afxTestActive(channel = AFX_CHANNEL) {
  return AFX_TEST_DEVICE_VIEW && channel === 0 && !!AFX_TEST_STATE?.available;
}

function afxTestChannelChanged(channel) {
  if (!AFX_TEST_DEVICE_VIEW || !afxWindowIsOpen()) return;
  if (channel !== 0) {
    AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      'Device loading is currently available on AFX 1 only. This channel has local previews.';
  } else if (AFX_TEST_STATE?.available) {
    AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      AFX_TEST_STATE.links?.some(linked => linked === true)
        ? 'AFX links are on. Unlink before editing this mono rack; stereo sharing is not available yet.'
        : 'Select an effect in a slot. Initialized Memory Cat knobs send live; switch A/B polarity remains unconfirmed.';
  }
}

function afxTestOpen() {
  if (!PROFILE?.runtime_contracts?.afx_memorycat_test?.enabled) return;
  AFX_TEST_DEVICE_VIEW = true;
  AFX_TEST_STATE = null;
  selectAfxChannel(0);
  return afxTestRequest('/api/afx/memorycat-test');
}

function afxTestToolbarHTML() {
  if (!PROFILE?.runtime_contracts?.afx_memorycat_test?.enabled) return '';
  return '<div class="afx-test-toolbar"><span>AFX · Preamp 1 test rack</span>'
    + '<button type="button" class="afx-preview-open" data-afx-test-connect>Connect device rack</button>'
    + '<button type="button" class="afx-preview-open" data-afx-test-refresh>Refresh slots</button>'
    + '<button type="button" class="afx-preview-open" data-afx-test-preview>Local preview</button></div>';
}

async function afxTestRequest(path, body) {
  if (!afxWindowIsOpen() || AFX_TEST_BUSY) return;
  const popup = AFX_WINDOW, status = popup.document.getElementById('afx-preview-status');
  AFX_TEST_BUSY = true;
  status.textContent = body ? 'Waiting for the device…' : 'Reading the device rack…';
  try {
    const response = await fetch(path, body === undefined ? undefined : {
      method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The AFX test request failed.');
    const state = body && (path.endsWith('/parameters') || path.endsWith('/unlink') || path.endsWith('/link'))
      ? await fetch('/api/afx/memorycat-test').then(r => r.json()) : result;
    if (AFX_WINDOW !== popup || popup.closed || !AFX_TEST_DEVICE_VIEW) return;
    if (AFX_TEST_SESSION !== state.session) {
      AFX_TEST_DRAFTS.clear();
      AFX_TEST_SESSION = state.session;
    }
    AFX_TEST_STATE = state;
    if (body && path.endsWith('/parameters')) {
      const draft = AFX_TEST_DRAFTS.get(body.instance);
      if (draft) draft.liveReady = true;
      (state.parameters ||= {})[String(body.instance)] = {...body.values};
    }
    if (Array.isArray(state.effects)) AFX_TEST_CHOICES = state.effects;
    if (!state.available) throw new Error('The Memory Cat pilot is unavailable for this profile.');
    selectAfxChannel(AFX_CHANNEL);
    status.textContent = path.endsWith('/unlink') || path.endsWith('/link')
      ? 'Link flag sent; existing effects were preserved. Stereo parameter sharing is not available yet.'
      : body && path.endsWith('/parameters')
      ? 'Settings sent. Parameter readback is unavailable; confirm the result on the device.'
      : state.links?.some(linked => linked === true)
      ? 'AFX links are on. Unlink before editing this mono rack; stereo sharing is not available yet.'
      : 'Select an effect in a slot. Memory Cat controls send live after the first full Apply.';
  } catch (error) {
    if (AFX_WINDOW === popup && !popup.closed) status.textContent = error.message;
    // A write error must never be automatically retried.
  } finally {
    AFX_TEST_BUSY = false;
  }
}

function afxTestDraft(channel, slot) {
  if (!afxTestActive(channel)) return null;
  const record = AFX_TEST_STATE.slots?.[slot];
  if (record?.type !== 73) return null;
  if (!AFX_TEST_DRAFTS.has(record.instance)) {
    const fields = PROFILE.runtime_contracts.afx_memorycat_test.parameter_offsets;
    const knobs = {level: 'Level', blend: 'Blend', feedback: 'Feedback', delay: 'Delay', depth: 'Depth', lpf_fc: 'Filter'};
    const controls = Object.keys(fields).map(id => ({id,
      label: knobs[id] || (id === 'chrs_vibr' ? 'Chorus / Vibrato' : '550 ms / 1100 ms'),
      kind: Object.hasOwn(knobs, id) ? 'continuous' : 'enum', range: [0, 100],
      options: {'0': 'A · 0', '1': 'B · 1'},
    }));
    const sent = AFX_TEST_STATE.parameters?.[String(record.instance)];
    const values = Object.fromEntries(controls.map(control => [control.id,
      control.kind === 'continuous' ? sent?.[control.id] ?? 0
        : sent?.[control.id] == null ? null : String(sent[control.id])]));
      AFX_TEST_DRAFTS.set(record.instance, {live: true, liveReady: !!sent, instance: record.instance,
      effect: {id: 'memory_brigade', name: 'Memory Cat Brigade', controls}, values});
  }
  return AFX_TEST_DRAFTS.get(record.instance);
}

function afxTestRackHTML(capacity, channel) {
  if (!AFX_TEST_DEVICE_VIEW) return null;
  const writable = AFX_TEST_STATE?.online && AFX_TEST_STATE?.writes_enabled
    && !AFX_TEST_STATE.links?.some(linked => linked === true);
  return Array.from({length: capacity.slots}, (_, slot) => {
    const record = channel === 0 ? AFX_TEST_STATE?.slots?.[slot] : null, draft = afxTestDraft(channel, slot);
    let face;
    if (draft) face = AFX_PANELS.get(draft.effect.id).render(draft, slot);
    else {
      const empty = record && record.type === 0 && record.instance === 0;
      const choice = AFX_TEST_CHOICES.find(effect => effect.type_id === record?.type);
      const text = empty ? 'Empty slot' : record ? `${choice?.name || `Effect type ${record.type}`} · controls unavailable` : 'Slot readback unavailable';
      face = `<div class="afx-rack-face"><h3><span class="afx-slot-number">${slot + 1}</span>Slot ${slot + 1}</h3>`
        + `<div class="afx-rack-controls"><span>${text}</span>`
        + '</div></div>';
    }
    return `<article class="afx-rack-unit${draft ? ' afx-rack-effect' : ''}" data-afx-rack-slot="${slot}"`
      + ` aria-label="AFX ${channel + 1}, slot ${slot + 1}"><span class="afx-rack-ear" aria-hidden="true"></span>`
      + `<div class="afx-slot-unit">${afxTestPickerHTML(channel, slot, record, writable)}${face}</div>`
      + '<span class="afx-rack-ear" aria-hidden="true"></span></article>';
  }).join('');
}

function afxTestPickerHTML(channel, slot, record, writable) {
  const current = AFX_TEST_CHOICES.find(effect => effect.type_id === record?.type);
  const empty = record?.type === 0 && record?.instance === 0;
  const enabled = channel === 0 && writable && record && (empty || current?.loadable);
  return `<label class="afx-slot-picker">Effect<select data-afx-effect-select="${slot}" aria-label="Effect for slot ${slot + 1}"${enabled ? '' : ' disabled'}>`
    + `<option value=""${empty ? ' selected' : ''}>${record ? 'Empty' : 'Device slot unavailable'}</option>`
    + (!empty && record && !current ? `<option selected disabled>Effect type ${record.type}</option>` : '')
    + AFX_TEST_CHOICES.map(effect => `<option value="${afxEscape(effect.id)}"${current?.id === effect.id ? ' selected' : ''}${effect.loadable ? '' : ' disabled'}>${afxEscape(effect.name)}${effect.loadable ? '' : ' · not mapped'}</option>`).join('')
    + '</select></label>';
}

function afxTestChange(event) {
  const select = event.target;
  if (!select.matches('[data-afx-effect-select]') || !afxTestActive() || AFX_TEST_BUSY) return;
  const slot = Number(select.dataset.afxEffectSelect), record = AFX_TEST_STATE.slots?.[slot];
  const empty = record?.type === 0 && record?.instance === 0;
  const choice = AFX_TEST_CHOICES.find(effect => effect.id === select.value && effect.loadable);
  if (!record || (!choice && select.value)) return;
  if (!choice && empty || choice?.type_id === record.type) return;
  void afxTestRequest('/api/afx/memorycat-test/chain', {
    operation: choice ? empty ? 'load' : 'replace' : 'remove', slot,
    ...(choice ? {effect_id: choice.id} : {}),
  });
}

function afxTestChannelLabel(channel) {
  if (!AFX_TEST_DEVICE_VIEW) return `AFX ${channel + 1}`;
  const pair = Math.floor(channel / 2), linked = AFX_TEST_STATE?.links?.[pair];
  return `AFX ${channel + 1}` + (linked === true ? ` ↔ ${channel % 2 ? channel : channel + 2}` : linked === false ? '' : ' · link ?');
}

function afxTestPairHTML(channel) {
  if (!AFX_TEST_DEVICE_VIEW) return '';
  const pair = Math.floor(channel / 2), linked = AFX_TEST_STATE?.links?.[pair];
  const writable = AFX_TEST_STATE?.online && AFX_TEST_STATE?.writes_enabled;
  return `<button class="afx-pair-link${linked === true ? ' on' : ''}" type="button" data-afx-pair="${pair}" aria-pressed="${linked == null ? 'mixed' : linked}"${writable ? '' : ' disabled'}>${linked === true ? 'Unlink' : 'Link'} AFX ${pair * 2 + 1}–${pair * 2 + 2}</button>`
    + `<p class="afx-link-note">${linked == null ? 'Link state unknown' : 'Link state last sent by this server'}</p>`;
}

function afxTestLinkClick(event) {
  const button = event.target.closest('[data-afx-pair]');
  if (!button || !AFX_TEST_DEVICE_VIEW || AFX_TEST_BUSY) return;
  const pair = Number(button.dataset.afxPair);
  void afxTestRequest('/api/afx/link', {pair, enabled: AFX_TEST_STATE?.links?.[pair] !== true});
}

function afxTestSlotLabel(channel, slot) {
  if (!afxTestActive(channel)) return null;
  const record = AFX_TEST_STATE.slots?.[slot];
  if (!record) return null;
  return record.type === 0 && record.instance === 0 ? 'Empty'
    : AFX_TEST_CHOICES.find(effect => effect.type_id === record.type)?.name || `Effect type ${record.type}`;
}

function afxTestMove(source, slot) {
  if (!AFX_TEST_BUSY && afxTestActive())
    return afxTestRequest('/api/afx/memorycat-test/chain', {operation: 'move', source, slot});
}

function afxTestClick(event) {
  if (event.target.closest('[data-afx-test-connect]') || event.target.closest('[data-afx-test-refresh]')) {
    AFX_TEST_DEVICE_VIEW = true;
    selectAfxChannel(0);
    void afxTestRequest('/api/afx/memorycat-test');
    return true;
  }
  if (event.target.closest('[data-afx-test-preview]')) {
    AFX_TEST_DEVICE_VIEW = false;
    AFX_TEST_STATE = null;
    selectAfxChannel(AFX_CHANNEL);
    AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      'Local previews do not load effects. Connect device rack to load Memory Cat on AFX 1.';
    return true;
  }
  if (event.target.closest('[data-afx-test-unlink]')) {
    void afxTestRequest('/api/afx/memorycat-test/unlink', {});
    return true;
  }
  if (!afxTestActive()) return false;
  for (const [attribute, operation] of [['data-afx-device-load', 'load'], ['data-afx-device-remove', 'remove']]) {
    const button = event.target.closest(`[${attribute}]`);
    if (!button) continue;
    const slot = Number(button.getAttribute(attribute));
    void afxTestRequest('/api/afx/memorycat-test/chain', {operation, slot});
    return true;
  }
  const move = event.target.closest('[data-afx-move]');
  if (move) {
    const source = Number(move.dataset.afxSlot);
    void afxTestMove(source, source + Number(move.dataset.afxMove));
    return true;
  }
  const apply = event.target.closest('[data-afx-device-apply]');
  if (apply) {
    const draft = afxTestDraft(0, Number(apply.dataset.afxDeviceApply));
    if (!draft) return true;
    if (['chrs_vibr', 'size'].some(id => draft.values[id] === null)) {
      AFX_WINDOW.document.getElementById('afx-preview-status').textContent = 'Select both switch positions before applying the complete settings.';
      return true;
    }
    const values = Object.fromEntries(Object.entries(draft.values).map(([key, value]) => [key, Number(value)]));
    void afxTestRequest('/api/afx/memorycat-test/parameters', {instance: draft.instance, values});
    return true;
  }
  return false;
}

AFX_DEVICE_RACK = {toolbarHTML: afxTestToolbarHTML, rackHTML: afxTestRackHTML,
  click: afxTestClick, draft: afxTestDraft, active: afxTestActive, move: afxTestMove,
  open: afxTestOpen, slotLabel: afxTestSlotLabel, channelChanged: afxTestChannelChanged,
  change: afxTestChange, pairHTML: afxTestPairHTML, channelLabel: afxTestChannelLabel, linkClick: afxTestLinkClick};
