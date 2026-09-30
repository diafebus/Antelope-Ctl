"use strict";

// AFX rack previews are local drafts, separate from unavailable device slots.
let AFX_WINDOW = null;
let AFX_CHANNEL = 0;
let AFX_PREVIEW_CATALOG = null;
let AFX_PREVIEW_REQUEST = null;
const AFX_DRAFTS = new Map();
const AFX_PANELS = new Map();
let AFX_DEVICE_RACK = null;

function afxEscape(value) {
  return String(value).replace(/[&<>"']/g, char =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

function afxDraftKey(channel, slot) { return `${channel}:${slot}`; }

async function previewAfxEffect(slot, effectId) {
  const capacity = afxCapacity();
  if (!AFX_PANELS.has(effectId) || !capacity || !Number.isSafeInteger(slot) || slot < 0 || slot >= capacity.slots) return;
  const popup = AFX_WINDOW, channel = AFX_CHANNEL;
  if (!afxWindowIsOpen()) return;
  const status = popup.document.getElementById('afx-preview-status');
  status.textContent = 'Reading local control definitions…';
  try {
    if (!AFX_PREVIEW_CATALOG) {
      if (!AFX_PREVIEW_REQUEST) {
        AFX_PREVIEW_REQUEST = fetch('/api/afx/catalog').then(response => {
          if (!response.ok) throw new Error('Could not read the AFX control catalog.');
          return response.json();
        }).finally(() => { AFX_PREVIEW_REQUEST = null; });
      }
      AFX_PREVIEW_CATALOG = await AFX_PREVIEW_REQUEST;
    }
    if (AFX_WINDOW !== popup || popup.closed || AFX_CHANNEL !== channel) return;
    if (AFX_PREVIEW_CATALOG.mode !== 'preview' || AFX_PREVIEW_CATALOG.device_writes !== false)
      throw new Error('The local preview catalog is unavailable.');
    const effect = AFX_PREVIEW_CATALOG.effects.find(item => item.id === effectId);
    if (!effect) throw new Error('Effect controls are not mapped for this device profile.');
    const key = afxDraftKey(channel, slot);
    if (!AFX_DRAFTS.has(key)) {
      AFX_DRAFTS.set(key, {effect, values: Object.fromEntries(effect.controls.map(control =>
        [control.id, control.kind === 'continuous' ? control.range[0] : null]))});
    }
    popup.document.getElementById('afx-rack').innerHTML = afxRackHTML(capacity, channel);
    status.textContent = 'Local previews do not load an effect or read its device settings.';
  } catch (error) {
    if (AFX_WINDOW === popup && !popup.closed && AFX_CHANNEL === channel)
      status.textContent = error.message;
  }
}

function clickAfxPreview(event) {
  if (AFX_DEVICE_RACK?.click(event)) return;
  const preview = event.target.closest('[data-afx-preview]');
  if (preview) { void previewAfxEffect(Number(preview.dataset.afxPreview), preview.dataset.afxEffect); return; }
  const remove = event.target.closest('[data-afx-remove]');
  if (remove) {
    AFX_DRAFTS.delete(afxDraftKey(AFX_CHANNEL, Number(remove.dataset.afxRemove)));
    selectAfxChannel(AFX_CHANNEL);
    return;
  }
  const move = event.target.closest('[data-afx-move]');
  if (move) {
    const source = Number(move.dataset.afxSlot);
    moveAfxDraft(source, source + Number(move.dataset.afxMove));
    return;
  }
  const input = event.target.closest('[data-afx-slot]');
  const slot = input && Number(input.dataset.afxSlot);
  const draft = input && (AFX_DEVICE_RACK?.draft(AFX_CHANNEL, slot)
    || AFX_DRAFTS.get(afxDraftKey(AFX_CHANNEL, slot)));
  if (draft) AFX_PANELS.get(draft.effect.id)?.click(draft, event);
}

function moveAfxDraft(source, destination) {
  const capacity = afxCapacity();
  if (!capacity || ![source, destination].every(index => Number.isSafeInteger(index)
      && index >= 0 && index < capacity.slots) || source === destination) return;
  if (AFX_DEVICE_RACK?.active(AFX_CHANNEL)) { void AFX_DEVICE_RACK.move(source, destination); return; }
  const slots = Array.from({length: capacity.slots}, (_, slot) =>
    AFX_DRAFTS.get(afxDraftKey(AFX_CHANNEL, slot)));
  if (!slots[source]) return;
  slots.splice(destination, 0, slots.splice(source, 1)[0]);
  slots.forEach((draft, slot) => {
    const key = afxDraftKey(AFX_CHANNEL, slot);
    if (draft) AFX_DRAFTS.set(key, draft); else AFX_DRAFTS.delete(key);
  });
  selectAfxChannel(AFX_CHANNEL);
}

function afxPanelPositionHTML(slot) {
  return `<span class="afx-panel-position">${String(slot + 1).padStart(2, '0')}</span>`
    + `<button type="button" class="afx-panel-drag" draggable="true" data-afx-drag="${slot}"`
    + ' aria-label="Drag to reorder effect">⠿</button>'
    + `<button type="button" class="afx-panel-move" data-afx-slot="${slot}" data-afx-move="-1"`
    + ` aria-label="Move effect up"${slot === 0 ? ' disabled' : ''}>↑</button>`
    + `<button type="button" class="afx-panel-move" data-afx-slot="${slot}" data-afx-move="1"`
    + ` aria-label="Move effect down"${slot === afxCapacity().slots - 1 ? ' disabled' : ''}>↓</button>`;
}

function afxCapacity() {
  const channels = PROFILE?.afx?.channel_count;
  const slots = PROFILE?.afx?.slots_per_channel;
  return Number.isSafeInteger(channels) && channels > 0
    && Number.isSafeInteger(slots) && slots > 0 ? {channels, slots} : null;
}

function afxWindowIsOpen() {
  return !!AFX_WINDOW && !AFX_WINDOW.closed;
}

function setAfxLauncherState(open) {
  const button = document.getElementById('afxopen');
  if (!button) return;
  button.classList.toggle('on', open);
  button.setAttribute('aria-expanded', String(open));
}

function afxSelectedChannel(capacity) {
  return Number.isSafeInteger(AFX_CHANNEL) && AFX_CHANNEL >= 0
    && AFX_CHANNEL < capacity.channels ? AFX_CHANNEL : 0;
}

function afxRackHTML(capacity, channel) {
  const deviceRack = AFX_DEVICE_RACK?.rackHTML(capacity, channel);
  if (deviceRack != null) return deviceRack;
  return Array.from({length: capacity.slots}, (_, slot) => {
    const draft = AFX_DRAFTS.get(afxDraftKey(channel, slot));
    const preview = PROFILE?.afx?.catalog === 'afx_effects.json'
      ? Array.from(AFX_PANELS, ([id, panel]) => `<button type="button" class="afx-preview-open"
          data-afx-preview="${slot}" data-afx-effect="${afxEscape(id)}">Preview ${afxEscape(panel.label)} controls</button>`).join('') : '';
    return `<article class="afx-rack-unit${draft ? ' afx-rack-effect' : ''}" data-afx-rack-slot="${slot}" aria-label="AFX ${channel + 1}, slot ${slot + 1}: ${draft ? 'local preview, device state unavailable' : 'state unavailable'}">`
    + '<span class="afx-rack-ear" aria-hidden="true"></span>'
    + (draft ? AFX_PANELS.get(draft.effect.id).render(draft, slot)
      : `<div class="afx-rack-face"><h3><span class="afx-slot-number">${String(slot + 1).padStart(2, '0')}</span>`
        + `Slot ${slot + 1}</h3><div class="afx-rack-controls"><span>Slot contents unavailable</span>${preview}</div></div>`)
    + '<span class="afx-rack-ear" aria-hidden="true"></span></article>';
  }).join('');
}

function afxWindowHTML(capacity) {
  const channel = afxSelectedChannel(capacity);
  const options = Array.from({length: capacity.channels}, (_, index) =>
    `<option value="${index}"${index === channel ? ' selected' : ''}>AFX ${index + 1}</option>`).join('');
  const slots = Array.from({length: capacity.slots}, (_, slot) =>
    `<li class="afx-slot"><span class="afx-slot-number">${slot + 1}</span><span>Unavailable</span></li>`).join('');
  return '<header class="afx-window-header"><div><h1>AFX</h1>'
    + '<p id="afx-device"></p></div>'
    + `<span class="afx-capacity">${capacity.channels} channels · ${capacity.slots} slots per channel</span>`
    + '<button class="secbtn" type="button" data-afx-close>Close</button></header>'
    + '<main class="afx-window-main"><aside class="afx-channel-panel" aria-label="Channel selection">'
    + '<label class="afx-channel-select" for="afx-channel">Select channel</label>'
    + `<select id="afx-channel">${options}</select>`
    + `<article class="afx-channel"><h2 id="afx-channel-name">AFX ${channel + 1}</h2>`
    + `<p class="afx-chain-label">${capacity.slots} effect slots</p><ol class="afx-slots">${slots}</ol></article></aside>`
    + '<section class="afx-rack-panel" aria-labelledby="afx-rack-title">'
    + `<div class="afx-rack-heading"><h2 id="afx-rack-title">AFX ${channel + 1} · Effects rack</h2>`
    + '<p class="afx-note">Effect controls will appear here when available.</p></div>'
    + (AFX_DEVICE_RACK?.toolbarHTML() || '')
    + '<p id="afx-preview-status" class="afx-preview-status" role="status"></p>'
    + `<div id="afx-rack" class="afx-rack">${afxRackHTML(capacity, channel)}</div></section></main>`;
}

function selectAfxChannel(channel) {
  const capacity = afxCapacity();
  if (!capacity || !Number.isSafeInteger(channel) || channel < 0 || channel >= capacity.channels) return;
  AFX_CHANNEL = channel;
  if (!afxWindowIsOpen()) return;
  const d = AFX_WINDOW.document;
  d.getElementById('afx-channel').value = String(channel);
  d.getElementById('afx-channel-name').textContent = `AFX ${channel + 1}`;
  d.getElementById('afx-rack-title').textContent = `AFX ${channel + 1} · Effects rack`;
  d.getElementById('afx-rack').innerHTML = afxRackHTML(capacity, channel);
}

function closeAfxWindow() {
  const popup = AFX_WINDOW;
  AFX_WINDOW = null;
  if (popup && !popup.closed) popup.close();
  setAfxLauncherState(false);
}

function openAfxWindow() {
  const capacity = afxCapacity();
  if (!capacity) return;
  if (afxWindowIsOpen()) {
    AFX_WINDOW.focus();
    return;
  }
  const popup = window.open('', 'antelopeAFX',
    'popup=yes,location=no,toolbar=no,menubar=no,status=no,'
    + 'scrollbars=yes,resizable=yes,width=1320,height=780');
  if (!popup) {
    setAfxLauncherState(false);
    reportMessage('afx-popup', 'AFX popup blocked',
      'Allow popups for this page to open the AFX window.');
    return;
  }
  AFX_WINDOW = popup;
  AFX_CHANNEL = afxSelectedChannel(capacity);
  const d = popup.document;
  d.open();
  d.write('<!doctype html><html lang="en"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>AFX — antelope-ctl</title>'
    + '<link rel="stylesheet" href="/webui/static/app.css?v=routing-mix-colors-v1">'
    + '<link rel="stylesheet" href="/webui/static/afx.css?v=afx-memorycat-v3">'
    + Array.from(AFX_PANELS.values(), panel => `<link rel="stylesheet" href="${afxEscape(panel.stylesheet)}">`).join('')
    + '</head><body class="afx-window-body" role="dialog" aria-label="AFX"></body></html>');
  d.close();
  d.body.innerHTML = afxWindowHTML(capacity);
  d.getElementById('afx-device').textContent = PROFILE.device?.label || PROFILE.device?.name || '';
  d.getElementById('afx-channel').addEventListener('change', event => {
    selectAfxChannel(Number(event.target.value));
  });
  d.getElementById('afx-rack').addEventListener('click', clickAfxPreview);
  d.body.addEventListener('click', event => {
    if (event.target.closest('.afx-test-toolbar')) AFX_DEVICE_RACK?.click(event);
  });
  d.getElementById('afx-rack').addEventListener('input', event => {
    const input = event.target;
    if (!input.matches('[data-afx-control]')) return;
    const slot = Number(input.dataset.afxSlot);
    const draft = AFX_DEVICE_RACK?.draft(AFX_CHANNEL, slot) || AFX_DRAFTS.get(afxDraftKey(AFX_CHANNEL, slot));
    if (draft) AFX_PANELS.get(draft.effect.id)?.input(draft, input);
  });
  d.getElementById('afx-rack').addEventListener('pointerdown', event => {
    const target = event.target.closest('[data-afx-slot]');
    if (!target) return;
    const slot = Number(target.dataset.afxSlot);
    const draft = AFX_DEVICE_RACK?.draft(AFX_CHANNEL, slot) || AFX_DRAFTS.get(afxDraftKey(AFX_CHANNEL, slot));
    if (draft) AFX_PANELS.get(draft.effect.id)?.pointerDown?.(draft, event);
  });
  d.getElementById('afx-rack').addEventListener('dragstart', event => {
    const handle = event.target.closest('[data-afx-drag]');
    if (!handle) { event.preventDefault(); return; }
    event.dataTransfer.setData('text/plain', `${AFX_CHANNEL}:${handle.dataset.afxDrag}`);
    event.dataTransfer.effectAllowed = 'move';
  });
  d.getElementById('afx-rack').addEventListener('dragover', event => {
    if (!event.target.closest('[data-afx-rack-slot]')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  });
  d.getElementById('afx-rack').addEventListener('drop', event => {
    const target = event.target.closest('[data-afx-rack-slot]');
    if (!target) return;
    event.preventDefault();
    const data = event.dataTransfer.getData('text/plain');
    if (!/^\d+:\d+$/.test(data)) return;
    const [channel, slot] = data.split(':').map(Number);
    if (channel === AFX_CHANNEL) moveAfxDraft(slot, Number(target.dataset.afxRackSlot));
  });
  const closeButton = d.querySelector('[data-afx-close]');
  closeButton.addEventListener('click', closeAfxWindow);
  popup.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeAfxWindow();
  });
  popup.addEventListener('pagehide', () => {
    if (AFX_WINDOW !== popup) return;
    AFX_WINDOW = null;
    setAfxLauncherState(false);
  }, {once: true});
  clearMessage('afx-popup');
  setAfxLauncherState(true);
  popup.focus();
  d.getElementById('afx-channel').focus();
}

document.getElementById('afxopen').addEventListener('click', openAfxWindow);
window.addEventListener('pagehide', closeAfxWindow);
