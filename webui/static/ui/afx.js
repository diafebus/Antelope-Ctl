"use strict";

// AFX capacity view. Slot contents need a verified channel/readback mapping.
let AFX_WINDOW = null;
let AFX_CHANNEL = 0;

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
  return Array.from({length: capacity.slots}, (_, slot) =>
    `<article class="afx-rack-unit" aria-label="AFX ${channel + 1}, slot ${slot + 1}: state unavailable">`
    + '<span class="afx-rack-ear" aria-hidden="true"></span>'
    + `<div class="afx-rack-face"><h3><span class="afx-slot-number">${String(slot + 1).padStart(2, '0')}</span>`
    + `Slot ${slot + 1}</h3><div class="afx-rack-controls">Slot contents unavailable</div></div>`
    + '<span class="afx-rack-ear" aria-hidden="true"></span></article>').join('');
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
    + '<link rel="stylesheet" href="/webui/static/afx.css?v=afx-rack-v2">'
    + '</head><body class="afx-window-body" role="dialog" aria-label="AFX"></body></html>');
  d.close();
  d.body.innerHTML = afxWindowHTML(capacity);
  d.getElementById('afx-device').textContent = PROFILE.device?.label || PROFILE.device?.name || '';
  d.getElementById('afx-channel').addEventListener('change', event => {
    selectAfxChannel(Number(event.target.value));
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
