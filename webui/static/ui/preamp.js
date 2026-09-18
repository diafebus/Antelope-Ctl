"use strict";

// Physical preamp strip rendering and interaction.

function paintKnob(el, gain) {
  const [lo, hi] = modeRange(currentMode(el));
  const g = Math.max(lo, Math.min(hi, gain));
  const frac = hi > lo ? (g - lo) / (hi - lo) : 0;
  el.querySelector('[data-rot]').setAttribute(
    'transform', `rotate(${(KNOB_A0 + frac * KNOB_SWEEP).toFixed(1)} ${KNOB_C})`);
  el.querySelector('[data-ring]').setAttribute(
    'stroke-dashoffset', (RING_LEN * (1 - frac)).toFixed(2));
  el.querySelector('[data-gv]').textContent = Math.round(g);
}

function currentMode(el) {
  const sel = el.querySelector('[data-mode]');
  return sel && sel.value ? sel.value : 'mic';
}

const preEl = ch => document.querySelector(`.pre[data-ch="${ch}"]`);

function toggleLink(pair) { setLink(pair, !LINKS[pair]); }
function setLink(pair, on) {
  if (pair < 0 || pair >= N_PAIRS) return;
  if (!!LINKS[pair] === !!on) return;             // no change
  if (on) LINKS[pair] = true; else delete LINKS[pair];
  saveLinks();
  post('/api/link', {pair, enabled: on});
  if (on) {
    // The device doesn't sync the pair itself; push the higher channel's
    // mode + gain + 48V to match the lower one (the Launcher does the same).
    const lo = pair * 2, hi = pair * 2 + 1, loEl = preEl(lo), hiEl = preEl(hi);
    if (loEl && hiEl) {
      const loMode = currentMode(loEl), hiSel = hiEl.querySelector('[data-mode]');
      if (hiSel.value !== loMode) { hiSel.value = loMode; post('/api/mode', {channel: hi, mode: loMode}); }
      const g = currentGain(loEl, lo);
      PENDING[hi] = {val: g, ts: Date.now()};
      paintKnob(hiEl, g);
      post('/api/gain', {channel: hi, db: g});
      // gain + 48V follow the pair; Ø (phase invert) stays independent
      const loP = loEl.querySelector('[data-tog="phantom"]').classList.contains('on');
      if (hiEl.querySelector('[data-tog="phantom"]').classList.contains('on') !== loP)
        post('/api/toggle', {channel: hi, param: 'phantom', on: loP});
    }
  }
  refreshLinks();
}
function refreshLinks() {
  $$('.pre:not(.dig)').forEach(el => {
    const ch = +el.dataset.ch, linked = isLinked(ch);
    const lk = el.querySelector('[data-link]');
    if (lk) lk.classList.toggle('on', linked);
    // input_mode can't be changed on a linked pair -- the Launcher greys it out
    const modeSel = el.querySelector('[data-mode]');
    if (modeSel) { modeSel.disabled = linked; modeSel.title = linked ? 'unlink to change mode' : ''; }
    el.classList.toggle('linked', linked);
    el.classList.toggle('linkstart', linked && ch % 2 === 0);
    el.classList.toggle('linkend', linked && ch % 2 === 1);
  });
}
// mirror a gain change to the linked partner (paint now, POST separately)
function linkPaint(ch, v) {
  if (!isLinked(ch)) return;
  const pe = preEl(partnerOf(ch)); if (!pe) return;
  PENDING[partnerOf(ch)] = {val: v, ts: Date.now()};
  paintKnob(pe, v);
}
function linkSend(ch, v) {
  if (!isLinked(ch)) return;
  PENDING[partnerOf(ch)] = {val: v, ts: Date.now()};
  post('/api/gain', {channel: partnerOf(ch), db: v});
}

// Optimistic gain: while the user is setting a knob we paint their value
// immediately and IGNORE the state stream for that channel until the device
// echoes the value back (or PENDING_TTL passes, so a dropped write can't
// freeze the knob). This kills the "snap back to old value, then jump" that a
// fixed dirty-timer caused when a stale frame landed mid round-trip.
const PENDING = {};          // ch -> {val, ts}
const PENDING_TTL = 2500;
function currentGain(el, ch) {
  const p = PENDING[ch];
  return p ? p.val : (+el.querySelector('[data-gv]').textContent || 0);
}

function wireKnob(el, ch) {
  const knob = el.querySelector('[data-knob]');
  let dragging = false, startY = 0, startGain = 0, live = 0, sendTimer = null, lastSent = 0;

  const clampNow = () => {
    const [lo, hi] = modeRange(currentMode(el));
    live = Math.max(lo, Math.min(hi, Math.round(live)));
    return live;
  };
  const sendNow = () => {
    clearTimeout(sendTimer); sendTimer = null;
    const v = clampNow();
    PENDING[ch] = {val: v, ts: Date.now()};
    lastSent = Date.now();
    post('/api/gain', {channel: ch, db: v});
    linkSend(ch, v);
  };
  const queueSend = () => {                     // throttle: fire now, or trailing
    if (sendTimer) return;
    const wait = Math.max(0, 75 - (Date.now() - lastSent));
    if (wait === 0) { sendNow(); return; }
    sendTimer = setTimeout(() => { sendTimer = null; sendNow(); }, wait);
  };
  const applyLive = () => {
    clampNow();
    PENDING[ch] = {val: live, ts: Date.now()};  // hold the stream off straight away
    paintKnob(el, live);
    linkPaint(ch, live);
  };

  knob.addEventListener('pointerdown', e => {
    dragging = true; startY = e.clientY;
    startGain = live = currentGain(el, ch);
    el.classList.add('dragging');
    knob.setPointerCapture(e.pointerId);
  });
  knob.addEventListener('pointermove', e => {
    if (!dragging) return;
    const [lo, hi] = modeRange(currentMode(el));
    live = startGain + (startY - e.clientY) * ((hi - lo) / KNOB_DRAG_PIXELS);   // full range ≈ 240px
    applyLive(); queueSend();
  });
  const stop = () => {
    if (!dragging) return;
    dragging = false;
    el.classList.remove('dragging');
    sendNow();                                  // final value, no throttle wait
  };
  knob.addEventListener('pointerup', stop);
  knob.addEventListener('pointercancel', stop);
  knob.addEventListener('wheel', e => {
    e.preventDefault();
    live = currentGain(el, ch) - Math.sign(e.deltaY);
    applyLive(); queueSend();
  }, {passive: false});
}

function applyChannels(channels) {
  (channels || []).forEach(c => {
    const el = document.querySelector(`.pre[data-ch="${c.ch}"]`); if (!el) return;
    const modeSel = el.querySelector('[data-mode]');
    // don't touch the <select> while it's focused/open -- mutating it (even
    // re-setting .value or an option's .disabled) bumps the native popup's
    // highlight. The hi-z option's disabled state is fixed at build time.
    if (document.activeElement !== modeSel) modeSel.value = c.mode;
    const p = PENDING[c.ch];
    if (p && (Math.round(c.gain) === p.val || Date.now() - p.ts > PENDING_TTL)) {
      delete PENDING[c.ch];                      // device caught up (or we gave up)
    }
    if (!PENDING[c.ch] && !el.classList.contains('dragging')) paintKnob(el, c.gain);

    const p48 = el.querySelector('[data-tog="phantom"]');
    p48.classList.toggle('on', c.phantom);
    p48.disabled = String(c.mode).toLowerCase() !== 'mic';
                                                  // Launcher only exposes 48V in mic mode
    el.querySelector('[data-tog="phase_invert"]').classList.toggle('on', c.phase_invert);
  });
}

// ?meterdebug=1 -- inspect both streams. Physical inputs use 0x73 @221..232;
// 0x75 ownership is still unresolved (see webui/METERS.md).
