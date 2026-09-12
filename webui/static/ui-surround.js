"use strict";

// ---- surround monitor ---------------------------------------------------
let SURROUND = null;
let SURROUND_SPEAKER = 0;
let SURROUND_BUILT = false;

const SURROUND_ESC = {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'};
const surroundEscape = value => String(value == null ? '' : value)
  .replace(/[&<>"']/g, char => SURROUND_ESC[char]);
const surroundNumber = (value, digits = 1) => {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '–';
};
const surroundHex = value => `0x${Number(value || 0).toString(16).padStart(2, '0')}`;

function surroundSpeaker(index, data = SURROUND) {
  return data?.speakers?.[index] || {
    index,
    label: `Speaker ${index + 1}`,
    active: false,
    readback: false,
    bands: [],
  };
}

function surroundMask(label, mask, data) {
  const bits = Array.from({length: data.speaker_count || 16}, (_, index) => {
    const speaker = surroundSpeaker(index, data);
    const on = (Number(mask || 0) & (1 << index)) !== 0;
    return `<span class="surround-mask-bit${on ? ' on' : ''}" title="${surroundEscape(label)} bit ${index}">
      <b>${surroundEscape(speaker.label)}</b><i>${on ? 'ON' : 'OFF'}</i></span>`;
  }).join('');
  return `<div class="surround-mask"><h4>${surroundEscape(label)} <span>${surroundHex(mask)}</span></h4>
    <div class="surround-mask-bits">${bits}</div></div>`;
}

function surroundRangeInput(field, label, value, range, unit, writable, step = 0.1) {
  const [min, max] = range;
  const fallback = field === 'delay_ms' ? min : 0;
  const current = Number.isFinite(Number(value)) ? Number(value) : fallback;
  const display = Number.isFinite(Number(value))
    ? `${surroundNumber(value)} ${unit}` : 'waiting';
  return `<label class="surround-control">
    <span class="surround-control-label">${surroundEscape(label)}</span>
    <input type="range" data-surround-global="${field}" min="${min}" max="${max}"
      step="${step}" value="${current}"${writable ? '' : ' disabled'}>
    <span class="surround-readout" data-surround-value="${field}">${display}</span>
  </label>`;
}

function surroundBassManagement(global) {
  const channels = global?.bass_mgmt_channels || [];
  if (!channels.length) return '<p class="surround-empty">No bass-management blocks in this readback.</p>';
  const rows = channels.map((channel, index) => `<tr>
    <td>Channel ${index + 1}</td>
    <td>${surroundNumber(channel.lp_cutoff_hz, 0)} Hz${channel.lp_bypass ? ' · bypass' : ''}</td>
    <td>${surroundNumber(channel.hp_cutoff_hz, 0)} Hz${channel.hp_bypass ? ' · bypass' : ''}</td>
    <td>${surroundNumber(channel.fader_db)} dB${channel.fader_mute ? ' · mute' : ''}</td>
    <td>${surroundNumber(channel.lp_order, 0)} / ${surroundNumber(channel.hp_order, 0)}</td>
  </tr>`).join('');
  return `<table class="surround-table"><thead><tr><th>channel</th><th>low-pass</th>
    <th>high-pass</th><th>fader</th><th>order L/H</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function surroundGlobalHTML(data) {
  const global = data.global;
  const write = data.write || {};
  const writable = write.enabled === true;
  const delayRange = write.delay_ms_range?.length === 2 ? write.delay_ms_range : [0.6, 4.5];
  const levelRange = write.level_db_range?.length === 2 ? write.level_db_range : [-60, 16];
  const format = global?.format || (global?.lfe_present ? '2.1' : '2.0');
  const flags = global
    ? `${surroundHex(global.flags_a_raw)} / ${surroundHex(global.flags_b_raw)}`
    : 'waiting for readback';
  return `<section class="surround-card">
    <div class="surround-card-hd"><div><h3>Global monitor</h3>
      <p class="surround-meta">category 0x1b · ${surroundEscape(flags)}</p></div>
      <span class="surround-state">${global ? surroundEscape(format) : 'WAITING'}</span></div>
    <div class="surround-controls">
      <label class="surround-control"><span class="surround-control-label">Format</span>
        <select disabled><option${format === '2.0' ? ' selected' : ''}>2.0</option>
          <option${format === '2.1' ? ' selected' : ''}>2.1</option></select>
        <span class="surround-readonly">read-only</span></label>
      ${surroundRangeInput('delay_ms', 'Global delay', global?.global_delay_ms,
        delayRange, 'ms', writable, Number(write.delay_step_ms) || 0.1)}
      ${surroundRangeInput('level_db', 'Global level', global?.level_db,
        levelRange, 'dB', writable, Number(write.level_step_db) || 0.1)}
      <div class="surround-control"><span class="surround-control-label">EQ position</span>
        <button class="btn" disabled>${global?.eq_post ? 'POST' : 'PRE'}</button>
        <span class="surround-readonly">read-only</span></div>
      <div class="surround-control"><span class="surround-control-label">Bass management</span>
        <button class="btn" disabled>${global?.bass_mgmt_on ? 'ON' : 'OFF'}</button>
        <span class="surround-readonly">read-only</span></div>
    </div>
    <p class="surround-note">${surroundEscape(write.note ||
      'Only the verified global delay and level path can be written.')}</p>
    <div class="surround-masks">
      ${surroundMask('Bypass', global?.bypass_mask, data)}
      ${surroundMask('Mute', global?.mute_mask, data)}
      ${surroundMask('Dim', global?.dim_mask, data)}
    </div>
    <div class="surround-bass"><h4>Bass-management blocks <span>read-only</span></h4>
      ${surroundBassManagement(global)}</div>
  </section>`;
}

function surroundCandidateControl(label, type = 'range') {
  const input = type === 'checkbox'
    ? `<input type="checkbox" disabled aria-label="${surroundEscape(label)}">`
    : `<input type="range" min="0" max="100.6" step="0.1" disabled aria-label="${surroundEscape(label)}">`;
  return `<label class="surround-control surround-disabled"><span class="surround-control-label">${surroundEscape(label)}</span>
    ${input}<span class="surround-readonly">readback unavailable</span></label>`;
}

function surroundMode(mode) {
  return Number.isFinite(Number(mode)) ? surroundHex(mode) : '–';
}

function surroundEqTable(speaker) {
  const rows = (speaker?.bands || []).map((band, index) => `<tr>
    <td>${index + 1}</td>
    <td><input type="number" value="${Number(band.freq_hz)}" disabled></td>
    <td><input type="number" value="${surroundNumber(band.q, 2)}" disabled></td>
    <td><input type="number" value="${surroundNumber(band.gain_db, 2)}" disabled></td>
    <td><code>${surroundMode(band.mode)}</code></td>
  </tr>`).join('');
  if (!rows) return '<p class="surround-empty">Waiting for the speaker EQ readback.</p>';
  return `<table class="surround-table surround-eq-table"><thead><tr>
    <th>band</th><th>frequency Hz</th><th>Q</th><th>gain dB</th><th>mode</th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}

function surroundSpeakerHTML(data) {
  const count = data.speaker_count || data.speakers?.length || 16;
  const speaker = surroundSpeaker(SURROUND_SPEAKER, data);
  const options = Array.from({length: count}, (_, index) => {
    const item = surroundSpeaker(index, data);
    return `<option value="${index}"${index === SURROUND_SPEAKER ? ' selected' : ''}>
      ${surroundEscape(item.label)}</option>`;
  }).join('');
  const status = speaker.readback ? (speaker.active ? 'ACTIVE' : 'inactive') : 'WAITING';
  return `<section class="surround-card">
    <div class="surround-card-hd"><div><h3>Speaker monitor</h3>
      <p class="surround-meta">category 0x1a · one readback per speaker</p></div>
      <span class="surround-state">${surroundEscape(status)}</span></div>
    <div class="surround-speakerbar">
      <label>Speaker <select data-surround-speaker>${options}</select></label>
      <span class="surround-speaker-name">${surroundEscape(speaker.label)}</span>
      <span class="surround-meta">${speaker.readback ? `${speaker.bands.length} EQ bands` : 'waiting for readback'}</span>
    </div>
    <div class="surround-controls surround-speaker-controls">
      ${surroundCandidateControl('Speaker delay')}
      ${surroundCandidateControl('Speaker level')}
      ${surroundCandidateControl('Phase invert', 'checkbox')}
    </div>
    <div class="surround-eq"><div class="surround-subhd"><h4>16-band EQ</h4>
      <span class="surround-readonly">read-only · mode bytes stay raw</span></div>
      ${surroundEqTable(speaker)}</div>
    <p class="surround-note">The per-speaker 0x87 frame is decoded for EQ readback. Its delay, level and phase head bytes are still candidate mappings, so no write is sent.</p>
  </section>`;
}

function renderSurround() {
  const host = $('#surround');
  if (!host) return;
  if (!SURROUND) {
    host.innerHTML = '<div class="surround-shell"><p class="surround-empty">Waiting for surround readback.</p></div>';
    return;
  }
  if (!SURROUND.available) {
    host.innerHTML = '<div class="surround-shell"><p class="surround-empty">Surround is not safely mapped for this profile.</p></div>';
    return;
  }
  host.innerHTML = `<div class="surround-shell">
    <div class="surround-header"><div><strong>Surround monitor</strong>
      <span class="surround-meta">profile-driven control surface</span></div>
      <span class="surround-meta">${SURROUND.active_speaker_count == null
        ? 'speaker count pending' : `${SURROUND.active_speaker_count} active speakers`}</span></div>
    <div class="surround-grid">${surroundGlobalHTML(SURROUND)}${surroundSpeakerHTML(SURROUND)}</div>
  </div>`;
}

async function reloadSurround() {
  SURROUND = await getJSON('/api/surround');
  const count = SURROUND.speaker_count || SURROUND.speakers?.length || 0;
  if (count && SURROUND_SPEAKER >= count) SURROUND_SPEAKER = 0;
  renderSurround();
}

function buildSurround() {
  const host = $('#surround');
  if (!host) return;
  if (!SURROUND_BUILT) {
    host.addEventListener('input', event => {
      const input = event.target.closest('[data-surround-global]');
      if (!input) return;
      const value = Number(input.value);
      const unit = input.dataset.surroundGlobal === 'delay_ms' ? 'ms' : 'dB';
      const readout = host.querySelector(`[data-surround-value="${input.dataset.surroundGlobal}"]`);
      if (readout) readout.textContent = `${surroundNumber(value)} ${unit}`;
    });
    host.addEventListener('change', event => {
      const speaker = event.target.closest('[data-surround-speaker]');
      if (speaker) {
        SURROUND_SPEAKER = Number(speaker.value) || 0;
        renderSurround();
        return;
      }
      const input = event.target.closest('[data-surround-global]');
      if (input) post('/api/surround/global', {
        [input.dataset.surroundGlobal]: Number(input.value),
      });
    });
    SURROUND_BUILT = true;
  }
  renderSurround();
  if (!SURROUND) reloadSurround().catch(() => {});
}

$('#routetabs')?.addEventListener('click', event => {
  if (event.target.closest('[data-rtab="surround"]')) buildSurround();
});
