"use strict";

// AFX capacity view. Slot contents need a verified channel/readback mapping.
let AFX_WINDOW = null;

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

function afxWindowHTML(capacity) {
  const channels = Array.from({length: capacity.channels}, (_, channel) =>
    `<article class="afx-channel" aria-label="AFX channel ${channel + 1}">`
    + `<h2>AFX ${channel + 1}</h2><ol class="afx-slots">`
    + Array.from({length: capacity.slots}, (_, slot) =>
      `<li class="afx-slot" aria-label="Slot ${slot + 1}: state unavailable">`
      + `<span class="afx-slot-number">${slot + 1}</span><span>Unavailable</span></li>`).join('')
    + '</ol></article>').join('');
  return '<header class="afx-window-header"><div><h1>AFX</h1>'
    + '<p id="afx-device"></p></div>'
    + `<span class="afx-capacity">${capacity.channels} channels · ${capacity.slots} slots per channel</span>`
    + '<button class="secbtn" type="button" data-afx-close>Close</button></header>'
    + '<main class="afx-window-main"><p class="afx-note">'
    + 'Slot contents are not available yet.</p>'
    + `<div class="afx-channels">${channels}</div></main>`;
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
  const d = popup.document;
  d.open();
  d.write('<!doctype html><html lang="en"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>AFX — antelope-ctl</title>'
    + '<link rel="stylesheet" href="/webui/static/app.css?v=routing-mix-colors-v1">'
    + '<link rel="stylesheet" href="/webui/static/afx.css?v=afx-window-v1">'
    + '</head><body class="afx-window-body" role="dialog" aria-label="AFX"></body></html>');
  d.close();
  d.body.innerHTML = afxWindowHTML(capacity);
  d.getElementById('afx-device').textContent = PROFILE.device?.label || PROFILE.device?.name || '';
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
  closeButton.focus();
}

document.getElementById('afxopen').addEventListener('click', openAfxWindow);
window.addEventListener('pagehide', closeAfxWindow);
