"use strict";

// Physical and digital input-strip controls.

function buildChannels(n) {
  const wrap = $('#channels'); wrap.innerHTML = '';
  for (let ch = 0; ch < n; ch++) {
    const el = document.createElement('div');
    const channelLabel = profileSpaceLabel('input', {index: ch + 1}, `CH${ch + 1}`)
      .replace(/^Preamp\s+/i, 'CH');
    const nextChannelLabel = profileSpaceLabel('input', {index: ch + 2}, `CH${ch + 2}`)
      .replace(/^Preamp\s+/i, 'CH');
    el.className = 'pre'; el.dataset.ch = ch;
    el.innerHTML = `
      <div class="top">
        <span class="chid">${channelLabel}</span>
        <select class="mode" data-mode>${MODES.map(m =>
        `<option value="${m}"${String(m).toLowerCase() === 'hiz' && !HIZ.has(ch) ? ' disabled' : ''}>${m.toUpperCase()}</option>`).join('')}</select>
      </div>
      ${ch % 2 === 0 && pairOf(ch) < N_PAIRS
        ? `<button class="linkbtn" data-link title="link ${channelLabel}+${nextChannelLabel}">${LINK_ICON}</button>`
        : ''}
      <div class="body">
        <div class="knob" data-knob tabindex="0">
          <svg viewBox="37.84 35.98 34 34">
            <path class="kring-band" transform="${RING_BAND_SHIFT}" d="${RING_BAND_D}"/>
            <path class="kring-fill" data-ring d="${RING_D}"
                  stroke-dasharray="${RING_LEN}" stroke-dashoffset="${RING_LEN}"/>
            <circle class="kbezel" cx="54.840942" cy="52.983658" r="12.5"/>
            <g data-rot transform="rotate(${KNOB_A0} ${KNOB_C})">
              <path class="kbody" d="m 51.840763,40.483834 v 4.547009 a 8.5,8.5 0 0 0 -5.499922,7.953003 8.5,8.5 0 0 0 5.499922,7.953003 v 4.547009 h 6.000151 v -4.547009 a 8.5,8.5 0 0 0 5.499923,-7.953003 8.5,8.5 0 0 0 -5.499923,-7.953003 v -4.547009 z"/>
              <rect class="kmark" x="54.446659" y="40.486126" width="0.78835768" height="4.4360867"/>
              <rect class="kmarkb" x="54.446659" y="61.047771" width="0.78835768" height="4.4360867"/>
              <circle class="kcap" cx="54.840942" cy="52.983658" r="6.5"/>
            </g>
          </svg>
          <div class="gv"><b data-gv>–</b><small>dB</small></div>
        </div>
        <div class="mcol">
          <span class="clipled" data-clip title="clip -- click to clear"></span>
          <div class="vmeter"><i data-meter style="clip-path:inset(100% 0 0 0)"></i></div>
        </div>
      </div>
      <div class="btns">
        <button class="btn p48" data-tog="phantom">+48</button>
        <button class="btn" data-tog="phase_invert">Ø</button>
        ${hasEmu(ch) ? `<button class="btn emubtn" data-emu title="mic modeling (emuMic) settings">EMU</button>` : ''}
      </div>`;

    el.querySelector('[data-clip]').addEventListener('click', e => {
      clearTimeout(CLIP_TIMER[ch]); e.currentTarget.classList.remove('on');
    });
    el.querySelector('[data-mode]').addEventListener('change', e =>
      post('/api/mode', {channel: ch, mode: e.target.value}));
    el.querySelectorAll('[data-tog]').forEach(b => b.addEventListener('click', () => {
      if (b.disabled) return;
      const on = !b.classList.contains('on');
      post('/api/toggle', {channel: ch, param: b.dataset.tog, on});
      // 48V follows the linked partner; Ø (phase invert) stays independent
      if (isLinked(ch) && b.dataset.tog === 'phantom')
        post('/api/toggle', {channel: partnerOf(ch), param: 'phantom', on});
    }));
    const lk = el.querySelector('[data-link]');
    if (lk) lk.addEventListener('click', () => toggleLink(pairOf(ch)));
    const em = el.querySelector('[data-emu]');
    if (em) em.addEventListener('click', () => openEmuModal(ch));
    wireKnob(el, ch);
    wrap.appendChild(el);
  }
  refreshLinks();
  refreshEmu();
}

// ---- ADAT / S-PDIF strips ----------------------------------------------
// Both address spaces are gain + link only -- no mode / 48V / Ø, and the HID
// protocol carries no ADAT/S-PDIF meters. Same knob art as the preamp; range
// from the profile (params.adat_gain / spdif_gain, -6..+12 dB on the Orion).
// Link state starts with the browser's saved value; a profile-confirmed 0x0b
// mapping replaces it when a complete device table arrives. Unmapped pairs
// retain that browser fallback.
// Endpoints:
// POST /api/adat-gain /api/spdif-gain /api/adat-link /api/spdif-link.
const DIG = {
  adat:  {api: 'adat',  grid: 'adatgrid',  label: n => profileSpaceLabel('adat', {index: n + 1}, 'ADAT ' + (n + 1)),
          n: 0, pairs: 0, range: [-6, 12], links: {}},
  spdif: {api: 'spdif', grid: 'spdifgrid', label: n => profileSpaceLabel('spdif', {side: n ? 'R' : 'L'}, n ? 'R' : 'L'),
          n: 0, pairs: 0, range: [-6, 12], links: {}},
};
const DIG_PENDING = {};                       // "adat:3" -> {val, ts}
const digKey = (kind, ch) => kind + ':' + ch;
const digEl = (kind, ch) =>
  document.querySelector(`.pre.dig[data-digk="${kind}"][data-ch="${ch}"]`);
const digPartner = ch => (ch % 2 ? ch - 1 : ch + 1);
const digIsLinked = (kind, ch) => !!DIG[kind].links[Math.floor(ch / 2)];
function digLoadLinks(k) {
  try { return JSON.parse(localStorage.getItem(k + 'Links') || '{}') || {}; }
  catch (_) { return {}; }
}
function digSaveLinks(k) {
  try { localStorage.setItem(k + 'Links', JSON.stringify(DIG[k].links)); } catch (_) {}
}

function inputLinkReadbackSpec() {
  const spec = PROFILE?.frame?.link_command?.readback;
  if (!spec || !['confirmed', 'capture-confirmed'].includes(
      String(spec.status || '').trim().toLowerCase())) return null;
  return spec;
}

function syncInputLinksFromReadback(structured) {
  const spec = inputLinkReadbackSpec();
  if (!spec || !Array.isArray(structured?.layouts)) return false;
  const category = Number(spec.category), index = Number(spec.index);
  const count = Number(spec.record_count);
  const pairs = spec.pair_counts;
  if (!Number.isInteger(category) || !Number.isInteger(index)
      || !Number.isInteger(count) || count <= 0 || !pairs
      || typeof pairs !== 'object' || Array.isArray(pairs)) return false;
  const preampCount = Number(pairs.preamp || 0), adatCount = Number(pairs.adat || 0);
  if (!Number.isInteger(preampCount) || !Number.isInteger(adatCount)
      || preampCount < 0 || adatCount < 0 || (!preampCount && !adatCount)
      || preampCount > count || adatCount > count
      || preampCount > N_PAIRS || adatCount > DIG.adat.pairs) return false;

  const layout = structured.layouts.find(item => item?.kind === 'link_table'
    && Number(item.category) === category && Number(item.index) === index
    && Number(item.record_count) === count && item.safe === true);
  const records = layout?.current?.[String(index)];
  if (!Array.isArray(records) || records.length !== count) return false;
  const linked = Array(count);
  for (const record of records) {
    const selector = Number(record?.record_index);
    const value = record?.linked;
    if (!Number.isInteger(selector) || selector < 0 || selector >= count
        || linked[selector] !== undefined
        || (value !== true && value !== false && value !== 0 && value !== 1)) return false;
    linked[selector] = value === true || value === 1;
  }
  for (let selector = 0; selector < count; selector++) {
    if (linked[selector] === undefined) return false;
  }

  let preampChanged = false, adatChanged = false;
  for (let pair = 0; pair < preampCount; pair++) {
    if (!!LINKS[pair] !== linked[pair]) preampChanged = true;
    if (linked[pair]) LINKS[pair] = true; else delete LINKS[pair];
  }
  for (let pair = 0; pair < adatCount; pair++) {
    if (!!DIG.adat.links[pair] !== linked[pair]) adatChanged = true;
    if (linked[pair]) DIG.adat.links[pair] = true; else delete DIG.adat.links[pair];
  }
  if (preampChanged) { saveLinks(); refreshLinks(); }
  if (adatChanged) { digSaveLinks('adat'); digRefreshLinks('adat'); }
  return preampChanged || adatChanged;
}
function digCurGain(el, kind, ch) {
  const p = DIG_PENDING[digKey(kind, ch)];
  return p ? p.val : (+el.querySelector('[data-gv]').textContent || 0);
}

// ADAT / S-PDIF knob art. Body = ideas/adat-knob.svg (grey metal, plain
// gradients, no mesh/script); tick = ideas/adat-knob-pointer.svg, in
// <g data-rot>. Rotates about the knob-BODY centre (11.857, 12.054) in the
// source's own 0..23.7769 viewBox. Gradient ids prefixed per instance.
// ONLY buildDig() uses this -- the preamp + monitor knobs are elsewhere.
const DIG_KNOB_C = '11.857 12.054';
// white progress arc round the dig knob, same idea as the preamp .kring-fill:
// 270 deg, gap at the bottom, r ~11 about the knob centre. stroke-dashoffset
// (DIG_RING_LEN -> 0) reveals it as the value rises.
const DIG_RING_D = 'M 4.079 19.832 A 11 11 0 1 1 19.635 19.832';
const DIG_RING_LEN = 51.84;
let AK_N = 0;
function adatKnobSVG() {
  const p = 'ak' + (++AK_N) + '-';
  return `<svg class="vk2" viewBox="0 0 23.7769 23.669477"><defs><linearGradient id="${p}linearGradient16"><stop style="stop-color:#525251;stop-opacity:1;" offset="0"/><stop style="stop-color:#464645;stop-opacity:0.8863;" offset="0.1479"/><stop style="stop-color:#61605f;stop-opacity:0.7765;" offset="0.398"/><stop style="stop-color:#4b4a49;stop-opacity:0.6667;" offset="0.5694"/><stop style="stop-color:#716f6d;stop-opacity:0.5554;" offset="1"/></linearGradient><linearGradient id="${p}linearGradient13"><stop style="stop-color:#c5c4c3;stop-opacity:1;" offset="0"/><stop style="stop-color:#c5c4c3;stop-opacity:0.7275;" offset="1"/></linearGradient><linearGradient id="${p}linearGradient12"><stop style="stop-color:#373434;stop-opacity:1;" offset="0"/><stop style="stop-color:#afabab;stop-opacity:0;" offset="1"/></linearGradient><linearGradient id="${p}linearGradient10"><stop style="stop-color:#4b4b4b;stop-opacity:1;" offset="0"/><stop style="stop-color:#4f4b4b;stop-opacity:0.1163;" offset="0.7539"/><stop style="stop-color:#817a7a;stop-opacity:0;" offset="1"/></linearGradient><linearGradient id="${p}linearGradient4"><stop style="stop-color:#4b4b4b;stop-opacity:1;" offset="0"/><stop style="stop-color:#504e4e;stop-opacity:0.1163;" offset="0.7539"/><stop style="stop-color:#817a7a;stop-opacity:0;" offset="1"/></linearGradient><linearGradient id="${p}linearGradient3"><stop style="stop-color:#858181;stop-opacity:1;" offset="0"/><stop style="stop-color:#373434;stop-opacity:0;" offset="1"/></linearGradient><radialGradient xlink:href="#${p}linearGradient3" id="${p}radialGradient4" cx="39.5249" cy="39.3556" fx="39.5249" fy="39.3556" r="5.7435" gradientTransform="matrix(0.58,-0.0035,0.0077,1.2658,7.8481,-12.8849)" gradientUnits="userSpaceOnUse"/><radialGradient xlink:href="#${p}linearGradient4" id="${p}radialGradient6" cx="30.6757" cy="29.2785" fx="30.6757" fy="29.2785" r="3.9025" gradientTransform="matrix(0.3416,0.0724,-0.1789,0.8444,16.9643,0.9736)" gradientUnits="userSpaceOnUse"/><radialGradient xlink:href="#${p}linearGradient10" id="${p}radialGradient6-0" cx="28.0081" cy="28.9172" fx="28.0081" fy="28.9172" r="3.9025" gradientTransform="matrix(0.517,-0.2325,0.354,0.7872,13.3323,9.6192)" gradientUnits="userSpaceOnUse"/><radialGradient xlink:href="#${p}linearGradient12" id="${p}radialGradient13" cx="39.8505" cy="22.7668" fx="39.8505" fy="22.7668" r="2.3478" gradientTransform="matrix(0.9999,-0.0148,0.041,2.7699,-9.6091,-36.7244)" gradientUnits="userSpaceOnUse"/><linearGradient xlink:href="#${p}linearGradient13" id="${p}linearGradient15" x1="22.8572" y1="-39.3886" x2="38.8572" y2="-39.3886" gradientUnits="userSpaceOnUse" gradientTransform="translate(-1.2835,8.471)"/><linearGradient xlink:href="#${p}linearGradient16" id="${p}linearGradient17" x1="46.9644" y1="33.4279" x2="23.8837" y2="25.0457" gradientUnits="userSpaceOnUse" gradientTransform="translate(-8.471,-1.2835)"/></defs><path class="kring-band" d="${DIG_RING_D}"/><path class="kring-fill" data-ring d="${DIG_RING_D}" stroke-dasharray="${DIG_RING_LEN}" stroke-dashoffset="${DIG_RING_LEN}"/><g style="display:inline" transform="translate(-19.0599,-17.5197)"><circle style="fill:#686868;fill-opacity:1;stroke:none;stroke-width:0.1;stroke-dasharray:none" cx="-29.5737" cy="30.917" transform="rotate(-90)" r="10.5"/><circle style="display:inline;fill:#252222;fill-opacity:1;stroke:none;stroke-width:0.1;stroke-dasharray:none" cx="-29.5737" cy="30.817" transform="rotate(-90)" r="10.4"/></g><g transform="translate(-19.0599,-17.5197)" style="display:inline"><ellipse style="fill:url(#${p}radialGradient4);fill-opacity:1;stroke:none;stroke-width:0.1;stroke-dasharray:none;stroke-opacity:1" cx="31.0974" cy="36.1579" rx="5.6935" ry="3.7707"/><ellipse style="fill:url(#${p}radialGradient6);stroke:none;stroke-width:0.1;stroke-dasharray:none;stroke-opacity:1" ry="5.9672" rx="4.6513" cy="28.5754" cx="24.6551"/><ellipse style="fill:url(#${p}radialGradient6-0);stroke:none;stroke-width:0.1;stroke-dasharray:none;stroke-opacity:1" cx="36.2553" cy="29.9481" rx="4.8759" ry="7.9887"/><ellipse style="fill:url(#${p}radialGradient13);stroke:none;stroke-width:0.1;stroke-dasharray:none;stroke-opacity:1" cx="31.0948" cy="22.6677" rx="3.1532" ry="5.7973"/></g><g transform="translate(-19.0599,-17.5197)" style="display:inline"><circle style="fill:url(#${p}linearGradient15);stroke:none;stroke-width:0.1;stroke-dasharray:none" cx="29.5737" cy="-30.9176" r="8" transform="rotate(90)"/><circle style="fill:url(#${p}linearGradient17);stroke:none;stroke-width:0.1;stroke-dasharray:none" cx="31.0176" cy="29.4737" r="7.9"/></g><g data-rot transform="rotate(${KNOB_A0} ${DIG_KNOB_C})"><rect x="11.183" y="4.054" width="1.349" height="3.779" rx=".3" fill="#dad8d8"/></g></svg>`;
}

function paintDigKnob(el, kind, gain) {
  const [lo, hi] = DIG[kind].range;
  const v = Math.max(lo, Math.min(hi, gain));
  const frac = hi > lo ? (v - lo) / (hi - lo) : 0;
  el.querySelector('[data-rot]').setAttribute(
    'transform', `rotate(${(KNOB_A0 + frac * KNOB_SWEEP).toFixed(1)} ${DIG_KNOB_C})`);
  const ring = el.querySelector('[data-ring]');
  if (ring) ring.setAttribute('stroke-dashoffset', (DIG_RING_LEN * (1 - frac)).toFixed(2));
  el.querySelector('[data-gv]').textContent = Math.round(v);
}

function wireDigKnob(el, kind, ch) {
  const knob = el.querySelector('[data-knob]');
  const [lo, hi] = DIG[kind].range, key = digKey(kind, ch), d = DIG[kind];
  let dragging = false, moved = false, startY = 0, startGain = 0, live = 0,
      sendTimer = null, lastSent = 0, pid = null;
  const clampNow = () => (live = Math.max(lo, Math.min(hi, Math.round(live))));
  const sendNow = () => {
    clearTimeout(sendTimer); sendTimer = null;
    const v = clampNow();
    DIG_PENDING[key] = {val: v, ts: Date.now()};
    lastSent = Date.now();
    post('/api/' + d.api + '-gain', {channel: ch, db: v});
    digLinkSend(kind, ch, v);
  };
  const queueSend = () => {
    if (sendTimer) return;
    const wait = Math.max(0, 75 - (Date.now() - lastSent));
    if (!wait) { sendNow(); return; }
    sendTimer = setTimeout(() => { sendTimer = null; sendNow(); }, wait);
  };
  const applyLive = () => {
    clampNow();
    DIG_PENDING[key] = {val: live, ts: Date.now()};
    paintDigKnob(el, kind, live);
    digLinkPaint(kind, ch, live);
  };
  const endDrag = () => {
    if (pid != null) { try { knob.releasePointerCapture(pid); } catch (_) {} pid = null; }
    dragging = false; el.classList.remove('dragging');
  };
  knob.addEventListener('pointerdown', e => {
    dragging = true; moved = false; startY = e.clientY;
    startGain = live = digCurGain(el, kind, ch);
    el.classList.add('dragging'); pid = e.pointerId; knob.setPointerCapture(pid);
  });
  knob.addEventListener('pointermove', e => {
    if (!dragging) return;
    const dy = startY - e.clientY;
    if (!moved && Math.abs(dy) < 3) return;   // ignore click jitter -- a plain
    moved = true;                             // click/dbl-click must not nudge it
    live = startGain + dy * ((hi - lo) / KNOB_DRAG_PIXELS);
    applyLive(); queueSend();
  });
  const stop = () => {
    if (!dragging) return;
    const wasMoved = moved;
    endDrag();
    if (wasMoved) sendNow();                  // a plain click sends nothing
  };
  knob.addEventListener('pointerup', stop);
  knob.addEventListener('pointercancel', stop);
  // a missed pointerup (fast double-click + capture) would otherwise leave the
  // knob "dragging" and captured, so the next mouse move jumps it to the rail
  knob.addEventListener('lostpointercapture', () => { if (dragging) endDrag(); });
  knob.addEventListener('dblclick', e => {   // reset to 0 dB (unity)
    e.preventDefault();
    endDrag(); moved = false;
    clearTimeout(sendTimer); sendTimer = null;
    live = 0; applyLive(); sendNow();
  });
  knob.addEventListener('wheel', e => {
    if (!knob.matches(':hover')) return;
    e.preventDefault();
    e.stopPropagation();
    live = digCurGain(el, kind, ch) - Math.sign(e.deltaY);
    applyLive(); queueSend();
  }, {passive: false});
}

function digToggleLink(kind, pair) { digSetLink(kind, pair, !DIG[kind].links[pair]); }
function digSetLink(kind, pair, on) {
  const d = DIG[kind];
  if (pair < 0 || pair >= d.pairs || !!d.links[pair] === !!on) return;
  if (on) d.links[pair] = true; else delete d.links[pair];
  digSaveLinks(kind);
  post('/api/' + d.api + '-link', {pair, enabled: on});
  if (on) {                                   // sync the higher channel to the lower
    const loCh = pair * 2, hiCh = pair * 2 + 1;
    const loEl = digEl(kind, loCh), hiEl = digEl(kind, hiCh);
    if (loEl && hiEl) {
      const g = digCurGain(loEl, kind, loCh);
      DIG_PENDING[digKey(kind, hiCh)] = {val: g, ts: Date.now()};
      paintDigKnob(hiEl, kind, g);
      post('/api/' + d.api + '-gain', {channel: hiCh, db: g});
    }
  }
  digRefreshLinks(kind);
}
function digRefreshLinks(kind) {
  document.querySelectorAll(`.pre.dig[data-digk="${kind}"]`).forEach(el => {
    const ch = +el.dataset.ch, linked = digIsLinked(kind, ch);
    const lk = el.querySelector('[data-link]');
    if (lk) lk.classList.toggle('on', linked);
    el.classList.toggle('linked', linked);
    el.classList.toggle('linkstart', linked && ch % 2 === 0);
    el.classList.toggle('linkend', linked && ch % 2 === 1);
  });
}
function digLinkPaint(kind, ch, v) {
  if (!digIsLinked(kind, ch)) return;
  const pe = digEl(kind, digPartner(ch)); if (!pe) return;
  DIG_PENDING[digKey(kind, digPartner(ch))] = {val: v, ts: Date.now()};
  paintDigKnob(pe, kind, v);
}
function digLinkSend(kind, ch, v) {
  if (!digIsLinked(kind, ch)) return;
  const pch = digPartner(ch);
  DIG_PENDING[digKey(kind, pch)] = {val: v, ts: Date.now()};
  post('/api/' + DIG[kind].api + '-gain', {channel: pch, db: v});
}

function buildDig(kind) {
  const d = DIG[kind], wrap = $('#' + d.grid);
  if (!wrap) return;
  d.links = digLoadLinks(kind);
  wrap.innerHTML = '';
  for (let ch = 0; ch < d.n; ch++) {
    const pair = Math.floor(ch / 2), hasLink = pair < d.pairs;
    const el = document.createElement('div');
    el.className = 'pre dig'; el.dataset.digk = kind; el.dataset.ch = ch;
    el.innerHTML = `
      <div class="top"><span class="chid">${d.label(ch)}</span></div>
      <div class="body">
        <div class="knob" data-knob tabindex="0">
          ${adatKnobSVG()}
          <div class="gv"><b data-gv>–</b><small>dB</small></div>
        </div>
      </div>
      ${hasLink && ch % 2 === 0
        ? `<button class="linkbtn" data-link title="link ${d.label(ch)}+${d.label(ch + 1)}">${LINK_ICON}</button>`
        : ''}`;
    const lk = el.querySelector('[data-link]');
    if (lk) lk.addEventListener('click', () => digToggleLink(kind, pair));
    wireDigKnob(el, kind, ch);
    wrap.appendChild(el);
  }
  digRefreshLinks(kind);
}

function applyDig(kind, list) {
  (list || []).forEach(c => {
    const el = digEl(kind, c.ch); if (!el) return;
    const key = digKey(kind, c.ch), p = DIG_PENDING[key];
    if (p && (Math.round(c.gain) === p.val || Date.now() - p.ts > PENDING_TTL)) delete DIG_PENDING[key];
    if (!DIG_PENDING[key] && !el.classList.contains('dragging')) paintDigKnob(el, kind, c.gain);
  });
}

function initTabs() {
  const bar = document.querySelector('.tabbar'); if (!bar) return;
  const show = name => {
    let button = bar.querySelector(`.tabbtn[data-tab="${name}"]`);
    if (!button || button.hidden) {
      button = [...bar.querySelectorAll('.tabbtn')].find(b => !b.hidden);
      if (!button) return;
      name = button.dataset.tab;
    }
    bar.querySelectorAll('.tabbtn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('[data-pane]').forEach(p => { p.hidden = p.dataset.pane !== name; });
    try { localStorage.setItem('inputsTab', name); } catch (_) {}
  };
  bar.addEventListener('click', e => {
    const b = e.target.closest('.tabbtn'); if (b) show(b.dataset.tab);
  });
  let saved = null;
  try { saved = localStorage.getItem('inputsTab'); } catch (_) {}
  show(saved || bar.querySelector('.tabbtn:not([hidden])')?.dataset.tab || 'inputs');
}

// ---- emuMic (in-UI settings panel) --------------------------------
