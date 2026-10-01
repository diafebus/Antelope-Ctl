"use strict";

// Operator-driven Orion rack. Device slots and local previews stay distinct.
let AFX_TEST_STATE = null;
let AFX_TEST_BUSY = false;
let AFX_TEST_SESSION = null;
let AFX_TEST_DEVICE_VIEW = false;
let AFX_TEST_CHOICES = [];
let AFX_TEST_REFRESH_PENDING = false;
const AFX_TEST_DRAFTS = new Map();

function afxTestLinked(channel = AFX_CHANNEL) {
  return AFX_TEST_STATE?.link_readback
    ? AFX_TEST_STATE.links?.[Math.floor(channel / 2)] !== false
    : AFX_TEST_STATE?.links?.some(linked => linked === true);
}

function afxTestSlots(channel = AFX_CHANNEL) {
  return AFX_TEST_STATE?.channels?.[String(channel)];
}

function afxTestCanMove(channel, slot) {
  const record = afxTestSlots(channel)?.[slot];
  return afxTestActive(channel) && !!AFX_TEST_CHOICES.find(effect =>
    effect.loadable && effect.type_id === record?.type);
}

function afxTestSlotPicker(channel, slot) {
  if (!AFX_TEST_DEVICE_VIEW) return null;
  const writable = AFX_TEST_STATE?.online && AFX_TEST_STATE?.writes_enabled;
  return afxTestPickerHTML(channel, slot, afxTestSlots(channel)?.[slot], writable);
}

function afxTestActive(channel = AFX_CHANNEL) {
  return AFX_TEST_DEVICE_VIEW && !!AFX_TEST_STATE?.available && AFX_TEST_STATE.allowed_channels?.includes(channel);
}

function afxTestChannelChanged(channel) {
  if (!AFX_TEST_DEVICE_VIEW || !afxWindowIsOpen()) return;
  if (afxTestActive(channel)) {
    AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      afxTestLinked(channel)
        ? 'Linked rack: slot edits apply to both channels. Unlink to edit parameters.'
        : 'Select an effect in a slot. Memory Cat knobs and switches send live; switch A/B polarity remains unconfirmed.';
  }
}

function afxTestOpen() {
  if (!PROFILE?.runtime_contracts?.afx_memorycat_test?.enabled) return;
  AFX_TEST_DEVICE_VIEW = true;
  AFX_TEST_STATE = null;
  selectAfxChannel(AFX_CHANNEL);
  return afxTestRequest('/api/afx/memorycat-test');
}

async function afxTestRefresh() {
  if (!AFX_TEST_DEVICE_VIEW || !afxWindowIsOpen() || AFX_TEST_REFRESH_PENDING) return;
  AFX_TEST_REFRESH_PENDING = true;
  try {
    let requestedChannel;
    do {
      while (AFX_TEST_BUSY && afxWindowIsOpen()) await new Promise(resolve => setTimeout(resolve, 60));
      if (!AFX_TEST_DEVICE_VIEW || !afxWindowIsOpen()) break;
      requestedChannel = AFX_CHANNEL;
      await afxTestRequest('/api/afx/memorycat-test');
    } while (AFX_CHANNEL !== requestedChannel);
  } finally { AFX_TEST_REFRESH_PENDING = false; }
}

function afxTestDeviceState(state) {
  if (!AFX_TEST_DEVICE_VIEW || !afxWindowIsOpen()) return;
  if (!state.online) {
    if (AFX_TEST_STATE?.online || AFX_TEST_SESSION != null) {
      AFX_TEST_SESSION = null;
      AFX_TEST_DRAFTS.clear();
      AFX_LIVE_PENDING.clear();
      if (AFX_TEST_STATE) {
        AFX_TEST_STATE.online = false;
        AFX_TEST_STATE.parameters = {};
        AFX_TEST_STATE.parameter_states = {};
      }
      selectAfxChannel(AFX_CHANNEL);
    }
  } else if (AFX_TEST_SESSION == null || Number.isInteger(state.connection_generation)
      && state.connection_generation !== AFX_TEST_SESSION) {
    AFX_TEST_DRAFTS.clear();
    AFX_LIVE_PENDING.clear();
    void afxTestRefresh();
  }
}

function afxTestToolbarHTML() {
  if (!PROFILE?.runtime_contracts?.afx_memorycat_test?.enabled) return '';
  return '<div class="afx-test-toolbar"><span>Orion · device rack</span>'
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
    const readPath = body === undefined && path === '/api/afx/memorycat-test'
      ? `${path}?channel=${AFX_CHANNEL}&refresh=true` : path;
    const response = await fetch(readPath, body === undefined ? undefined : {
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
    if (body === undefined && path === '/api/afx/memorycat-test') {
      for (const record of state.channels?.[String(AFX_CHANNEL)] || [])
        if (record.type === 73) AFX_TEST_DRAFTS.delete(record.instance);
    }
    if (body && path.endsWith('/chain') && body.operation !== 'move') {
      const channel = String(body.channel ?? 0);
      const previous = AFX_TEST_STATE?.channels?.[channel]?.[body.slot];
      if (previous?.type === 73) AFX_TEST_DRAFTS.delete(previous.instance);
      if (body.operation === 'load' || body.operation === 'replace') {
        const loaded = state.channels?.[channel]?.[body.slot];
        if (loaded?.type === 73) AFX_TEST_DRAFTS.delete(loaded.instance);
      }
    }
    AFX_TEST_STATE = state;
    if (Array.isArray(state.effects)) AFX_TEST_CHOICES = state.effects;
    if (!state.available) throw new Error('The Memory Cat pilot is unavailable for this profile.');
    selectAfxChannel(AFX_CHANNEL);
    status.textContent = path.endsWith('/unlink') || path.endsWith('/link')
      ? state.link_readback ? 'Link flag verified by device readback; existing effects preserved.' : 'Link flag sent; readback unavailable.'
      : body && path.endsWith('/parameters')
      ? result.verified ? 'Settings verified by device readback.' : 'Settings sent; parameter readback unavailable.'
      : afxTestLinked(AFX_CHANNEL)
      ? 'Linked rack: slot edits apply to both channels. Unlink to edit parameters.'
      : 'Select an effect in a slot. Memory Cat controls send live as you adjust them.';
  } catch (error) {
    if (body && AFX_WINDOW === popup && !popup.closed && AFX_TEST_DEVICE_VIEW) {
      // Read the failure latch, never retry the failed device mutation.
      try {
        const response = await fetch('/api/afx/memorycat-test');
        if (response.ok) {
          AFX_TEST_STATE = await response.json();
          selectAfxChannel(AFX_CHANNEL);
        }
      } catch (_) { /* Keep the original write error visible. */ }
    }
    if (AFX_WINDOW === popup && !popup.closed) status.textContent = error.message;
    // A write error must never be automatically retried.
  } finally {
    AFX_TEST_BUSY = false;
  }
}

function afxTestDraft(channel, slot) {
  if (!afxTestActive(channel)) return null;
  const record = afxTestSlots(channel)?.[slot];
  if (record?.type !== 73) return null;
  if (!AFX_TEST_DRAFTS.has(record.instance)) {
    const fields = PROFILE.runtime_contracts.afx_memorycat_test.parameter_offsets;
    const knobs = {level: 'Level', blend: 'Blend', feedback: 'Feedback', delay: 'Delay', depth: 'Depth', lpf_fc: 'Filter'};
    const controls = Object.keys(fields).map(id => ({id,
      label: knobs[id] || (id === 'chrs_vibr' ? 'Chorus / Vibrato' : '550 ms / 1100 ms'),
      kind: Object.hasOwn(knobs, id) ? 'continuous' : 'enum', range: [0, 100],
      options: {'0': 'A · 0', '1': 'B · 1'},
    }));
    const read = AFX_TEST_STATE.parameter_states?.[String(record.instance)];
    const sent = read?.values || AFX_TEST_STATE.parameters?.[String(record.instance)];
    const values = Object.fromEntries(controls.map(control => [control.id,
      control.kind === 'continuous' ? sent?.[control.id] ?? null
        : sent?.[control.id] == null ? null : String(sent[control.id])]));
    AFX_TEST_DRAFTS.set(record.instance, {live: true, liveReady: !!sent, parameterAvailable: !!sent,
      parameterSource: read ? 'readback' : 'last-sent', bypassed: read?.bypassed,
      livePaused: false, instance: record.instance,
      effect: {id: 'memory_brigade', name: 'Memory Cat Brigade', controls}, values});
  }
  return AFX_TEST_DRAFTS.get(record.instance);
}

function afxTestRackHTML(capacity, channel) {
  if (!AFX_TEST_DEVICE_VIEW) return null;
  return Array.from({length: capacity.slots}, (_, slot) => {
    const record = afxTestSlots(channel)?.[slot], draft = afxTestDraft(channel, slot);
    let face;
    if (draft) face = AFX_PANELS.get(draft.effect.id).render(draft, slot);
    else {
      const empty = record && record.type === 0 && record.instance === 0;
      const choice = AFX_TEST_CHOICES.find(effect => effect.type_id === record?.type);
      const text = empty ? 'Empty slot' : record ? `${choice?.name || `Effect type ${record.type}`} · controls unavailable` : 'Slot readback unavailable';
      face = `<div class="afx-rack-face"><h3>${afxTestCanMove(channel, slot) ? afxPanelPositionHTML(slot) : `<span class="afx-slot-number">${slot + 1}</span>Slot ${slot + 1}`} </h3>`
        + `<div class="afx-rack-controls"><span>${text}</span>`
        + '</div></div>';
    }
    return `<article class="afx-rack-unit${draft ? ' afx-rack-effect' : ''}" data-afx-rack-slot="${slot}"`
      + ` aria-label="AFX ${channel + 1}, slot ${slot + 1}"><span class="afx-rack-ear" aria-hidden="true"></span>`
      + `<div class="afx-slot-unit">${face}</div>`
      + '<span class="afx-rack-ear" aria-hidden="true"></span></article>';
  }).join('');
}

function afxTestPickerHTML(channel, slot, record, writable) {
  const current = AFX_TEST_CHOICES.find(effect => effect.type_id === record?.type);
  const empty = record?.type === 0 && record?.instance === 0;
  const enabled = afxTestActive(channel) && writable && record && (empty || current?.loadable);
  return `<label class="afx-slot-picker"><select data-afx-effect-select="${slot}" aria-label="Effect for slot ${slot + 1}"${enabled ? '' : ' disabled'}>`
    + `<option value=""${empty ? ' selected' : ''}>${record ? 'Empty' : 'Device slot unavailable'}</option>`
    + (!empty && record && !current ? `<option selected disabled>Effect type ${record.type}</option>` : '')
    + afxTestEffectOptionsHTML(current)
    + '</select></label>';
}

function afxTestEffectOptionsHTML(current) {
  const categories = ['Dynamics', 'EQ & Filters', 'Modulation', 'Delay & Reverb',
    'Pitch & Tuning', 'Amps & Cabinets', 'Preamps', 'Saturation & Distortion', 'Other'];
  return categories.map(category => {
    const effects = AFX_TEST_CHOICES.filter(effect => (effect.category || 'Other') === category);
    if (!effects.length) return '';
    return `<optgroup label="${afxEscape(category)}">`
      + effects.map(effect => `<option value="${afxEscape(effect.id)}"${current?.id === effect.id ? ' selected' : ''}${effect.loadable ? '' : ' disabled'}>${afxEscape(effect.name)}${effect.loadable ? '' : ' · not mapped'}</option>`).join('')
      + '</optgroup>';
  }).join('');
}

function afxTestChange(event) {
  const select = event.target;
  if (!select.matches('[data-afx-effect-select]') || !afxTestActive() || AFX_TEST_BUSY) return;
  const slot = Number(select.dataset.afxEffectSelect), record = afxTestSlots(AFX_CHANNEL)?.[slot];
  const empty = record?.type === 0 && record?.instance === 0;
  const choice = AFX_TEST_CHOICES.find(effect => effect.id === select.value && effect.loadable);
  if (!record || (!choice && select.value)) return;
  if (!choice && empty || choice?.type_id === record.type) return;
  void afxTestRequest('/api/afx/memorycat-test/chain', {
    operation: choice ? empty ? 'load' : 'replace' : 'remove', channel: AFX_CHANNEL, slot,
    ...(choice ? {effect_id: choice.id} : {}),
  });
}

function afxTestChannelLabel(channel) {
  if (!AFX_TEST_DEVICE_VIEW) return `AFX ${channel + 1}`;
  const pair = Math.floor(channel / 2), linked = AFX_TEST_STATE?.links?.[pair];
  const count = (afxTestSlots(channel) || []).filter(slot => slot.type > 0).length;
  return `AFX ${channel + 1}` + (count ? ` · ${count} FX` : '')
    + (linked === true ? ` ↔ ${channel % 2 ? channel : channel + 2}` : '');
}

function afxTestPairHTML(channel) {
  if (!AFX_TEST_DEVICE_VIEW) return '';
  const pair = Math.floor(channel / 2), linked = AFX_TEST_STATE?.links?.[pair];
  const writable = AFX_TEST_STATE?.online && AFX_TEST_STATE?.writes_enabled;
  return `<button class="afx-pair-link${linked === true ? ' on' : ''}" type="button" data-afx-pair="${pair}" aria-pressed="${linked == null ? 'mixed' : linked}"${writable ? '' : ' disabled'} title="${linked == null ? 'State unknown · click to link' : AFX_TEST_STATE.link_readback ? 'Device link readback' : 'Last command sent this session'}" aria-label="${linked === true ? 'Unlink' : 'Link'} AFX ${pair * 2 + 1}–${pair * 2 + 2}">`
    + '<svg class="afx-link-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/></svg>'
    + `<span>${pair * 2 + 1}–${pair * 2 + 2}</span></button>`;
}

function afxTestLinkClick(event) {
  const button = event.target.closest('[data-afx-pair]');
  if (!button || !AFX_TEST_DEVICE_VIEW || AFX_TEST_BUSY) return;
  const pair = Number(button.dataset.afxPair);
  void afxTestRequest('/api/afx/link', {pair, enabled: AFX_TEST_STATE?.links?.[pair] !== true});
}

function afxTestSlotLabel(channel, slot) {
  if (!afxTestActive(channel)) return null;
  const record = afxTestSlots(channel)?.[slot];
  if (!record) return null;
  return record.type === 0 && record.instance === 0 ? 'Empty'
    : AFX_TEST_CHOICES.find(effect => effect.type_id === record.type)?.name || `Effect type ${record.type}`;
}

function afxTestMove(source, slot) {
  if (!AFX_TEST_BUSY && afxTestActive())
    return afxTestRequest('/api/afx/memorycat-test/chain', {operation: 'move', channel: AFX_CHANNEL, source, slot});
}

function afxTestClick(event) {
  if (event.target.closest('[data-afx-test-connect]') || event.target.closest('[data-afx-test-refresh]')) {
    AFX_TEST_DEVICE_VIEW = true;
    selectAfxChannel(AFX_CHANNEL);
    void afxTestRequest('/api/afx/memorycat-test');
    return true;
  }
  if (event.target.closest('[data-afx-test-preview]')) {
    AFX_TEST_DEVICE_VIEW = false;
    AFX_TEST_STATE = null;
    selectAfxChannel(AFX_CHANNEL);
    AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      'Local previews do not load effects. Connect device rack to load effects.';
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
    void afxTestRequest('/api/afx/memorycat-test/chain', {operation, channel: AFX_CHANNEL, slot});
    return true;
  }
  const move = event.target.closest('[data-afx-move]');
  if (move) {
    const source = Number(move.dataset.afxSlot);
    void afxTestMove(source, source + Number(move.dataset.afxMove));
    return true;
  }
  const resume = event.target.closest('[data-afx-device-resume]');
  if (resume) {
    const draft = afxTestDraft(AFX_CHANNEL, Number(resume.dataset.afxDeviceResume));
    if (!draft) return true;
    draft.livePaused = false;
    AFX_DEVICE_RACK.parameterChanged(draft);
    AFX_PANELS.get(draft.effect.id).updateLiveStatus(draft, AFX_WINDOW.document);
    return true;
  }
  return false;
}

AFX_DEVICE_RACK = {toolbarHTML: afxTestToolbarHTML, rackHTML: afxTestRackHTML,
  click: afxTestClick, draft: afxTestDraft, active: afxTestActive, move: afxTestMove,
  open: afxTestOpen, slotLabel: afxTestSlotLabel, channelChanged: afxTestChannelChanged,
  slotPicker: afxTestSlotPicker, canMove: afxTestCanMove, change: afxTestChange, pairHTML: afxTestPairHTML, channelLabel: afxTestChannelLabel, linkClick: afxTestLinkClick,
  refresh: afxTestRefresh, deviceState: afxTestDeviceState};
