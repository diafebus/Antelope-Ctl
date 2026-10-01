"use strict";

// Operator-driven Orion pilot. Device slots and local previews stay distinct.
let AFX_TEST_STATE = null;
let AFX_TEST_BUSY = false;
let AFX_TEST_SESSION = null;
let AFX_TEST_DEVICE_VIEW = false;
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
      'Device slots shown. Apply sends all eight draft settings; switch A/B polarity is unconfirmed.';
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
  return '<div class="afx-test-toolbar"><span>Memory Cat · Preamp 1 pilot</span>'
    + '<button type="button" class="afx-preview-open" data-afx-test-connect>Connect device rack</button>'
    + '<button type="button" class="afx-preview-open" data-afx-test-refresh>Refresh slots</button>'
    + '<button type="button" class="afx-preview-open" data-afx-test-unlink>Unlink AFX 1/2 only</button>'
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
    const state = body && (path.endsWith('/parameters') || path.endsWith('/unlink'))
      ? await fetch('/api/afx/memorycat-test').then(r => r.json()) : result;
    if (AFX_WINDOW !== popup || popup.closed || !AFX_TEST_DEVICE_VIEW) return;
    if (AFX_TEST_SESSION !== state.session) {
      AFX_TEST_DRAFTS.clear();
      AFX_TEST_SESSION = state.session;
    }
    AFX_TEST_STATE = state;
    if (!state.available) throw new Error('The Memory Cat pilot is unavailable for this profile.');
    selectAfxChannel(AFX_CHANNEL);
    status.textContent = path.endsWith('/unlink')
      ? 'Link-OFF sent. Existing effects on both channels were preserved.'
      : body && path.endsWith('/parameters')
      ? 'Settings sent. Parameter readback is unavailable; confirm the result on the device.'
      : 'Device slots shown. Switch A/B polarity is unconfirmed; Apply sends all eight settings.';
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
    AFX_TEST_DRAFTS.set(record.instance, {live: true, instance: record.instance,
      effect: {id: 'memory_brigade', name: 'Memory Cat Brigade', controls}, values});
  }
  return AFX_TEST_DRAFTS.get(record.instance);
}

function afxTestRackHTML(capacity, channel) {
  if (!AFX_TEST_DEVICE_VIEW || channel !== 0) return null;
  const writable = AFX_TEST_STATE?.online && AFX_TEST_STATE?.writes_enabled;
  return Array.from({length: capacity.slots}, (_, slot) => {
    const record = AFX_TEST_STATE?.slots?.[slot], draft = afxTestDraft(channel, slot);
    let face;
    if (draft) face = AFX_PANELS.get(draft.effect.id).render(draft, slot);
    else {
      const empty = record && record.type === 0 && record.instance === 0;
      const text = empty ? 'Empty slot' : record ? `Effect type ${record.type} · controls unavailable` : 'Slot readback unavailable';
      face = `<div class="afx-rack-face"><h3><span class="afx-slot-number">${slot + 1}</span>Slot ${slot + 1}</h3>`
        + `<div class="afx-rack-controls"><span>${text}</span>`
        + (empty ? `<button type="button" class="afx-preview-open" data-afx-device-load="${slot}"${writable ? '' : ' disabled'}>Load Memory Cat</button>` : '')
        + '</div></div>';
    }
    return `<article class="afx-rack-unit${draft ? ' afx-rack-effect' : ''}" data-afx-rack-slot="${slot}"`
      + ` aria-label="Preamp 1, slot ${slot + 1}"><span class="afx-rack-ear" aria-hidden="true"></span>`
      + face + '<span class="afx-rack-ear" aria-hidden="true"></span></article>';
  }).join('');
}

function afxTestSlotLabel(channel, slot) {
  if (!afxTestActive(channel)) return null;
  const record = AFX_TEST_STATE.slots?.[slot];
  if (!record) return null;
  return record.type === 0 && record.instance === 0 ? 'Empty'
    : record.type === 73 ? 'Memory Cat' : `Effect type ${record.type}`;
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
  open: afxTestOpen, slotLabel: afxTestSlotLabel, channelChanged: afxTestChannelChanged};
