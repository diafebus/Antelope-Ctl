"use strict";

// ---- surround monitor ---------------------------------------------------
let SURROUND = null;
let SURROUND_SPEAKER = 0;
let SURROUND_BUILT = false;

const SURROUND_FORMAT_OPTIONS = [
  '2.0', '2.1', '3.0', '3.1', '4.0', '4.1',
  '5.0', '5.1', '5.1.2', '5.1.4',
  '7.0', '7.0.2', '7.1', '7.1.2', '7.1.4', '7.1.6',
  '9.1.2', '9.1.4', '9.1.6',
];

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

function surroundBassModal(global) {
  return '<div class="surround-bass-modal" data-surround-bass-modal hidden>'
    + '<div class="surround-bass-dialog" role="dialog" aria-modal="true"'
    + ' aria-labelledby="surround-bass-title">'
    + '<div class="surround-bass-modal-hd"><strong id="surround-bass-title">Bass Management</strong>'
    + '<button class="modal-x" type="button" data-surround-bass-close aria-label="close">&times;</button></div>'
    + '<div class="surround-bass-modal-bd">'
    + '<div class="surround-subhd"><h4>Decoded channel blocks</h4><span class="surround-readonly">read-only</span></div>'
    + surroundBassManagement(global)
    + '<p class="surround-note">The 2.1 bass-management blocks are decoded from the global surround readback. Filter type and link flags remain observational.</p>'
    + '</div></div></div>';
}

function surroundGlobalHTML(data) {
  const global = data.global;
  const write = data.write || {};
  const writable = write.enabled === true;
  const delayRange = write.delay_ms_range?.length === 2 ? write.delay_ms_range : [0.6, 4.5];
  const levelRange = write.level_db_range?.length === 2 ? write.level_db_range : [-60, 16];
  const format = global?.format || (global?.lfe_present ? '2.1' : '2.0');
  const formatOptions = SURROUND_FORMAT_OPTIONS.map(item =>
    '<option value="' + item + '"' + (item === format ? ' selected' : '')
      + (item === '2.0' || item === '2.1' ? '' : ' disabled') + '>' + item + '</option>'
  ).join('');
  const flags = global
    ? `${surroundHex(global.flags_a_raw)} / ${surroundHex(global.flags_b_raw)}`
    : 'waiting for readback';
  return `<section class="surround-card">
    <div class="surround-card-hd"><div><h3>Global monitor</h3>
      <p class="surround-meta">category 0x1b · ${surroundEscape(flags)}</p></div>
      <span class="surround-state">${global ? surroundEscape(format) : 'WAITING'}</span></div>
    <div class="surround-controls">
      <label class="surround-control surround-format-control"><span class="surround-control-label">Format</span>
        <select disabled aria-label="Surround format" title="Layouts beyond 2.1 require the MRC hardware">${formatOptions}</select>
        <span class="surround-readonly">read-only</span></label>
      ${surroundRangeInput('delay_ms', 'Global delay', global?.global_delay_ms,
        delayRange, 'ms', writable, Number(write.delay_step_ms) || 0.1)}
      ${surroundRangeInput('level_db', 'Global level', global?.level_db,
        levelRange, 'dB', writable, Number(write.level_step_db) || 0.1)}
      <div class="surround-control"><span class="surround-control-label">EQ position</span>
        <button class="btn" disabled>${global?.eq_post ? 'POST' : 'PRE'}</button>
        <span class="surround-readonly">read-only</span></div>
    </div>
    <p class="surround-note">${surroundEscape(write.note ||
      'Only the verified global delay and level path can be written.')}</p>
    <div class="surround-masks">
      ${surroundMask('Bypass', global?.bypass_mask, data)}
      ${surroundMask('Mute', global?.mute_mask, data)}
      ${surroundMask('Dim', global?.dim_mask, data)}
    </div>
    <div class="surround-bass-launch">
      <div><h4>Bass management</h4>
        <span class="surround-meta">${global?.bass_mgmt_on ? 'ON' : 'OFF'} · decoded blocks</span></div>
      <button class="btn" type="button" data-surround-bass-open aria-haspopup="dialog" aria-expanded="false">OPEN</button>
    </div>
    ${surroundBassModal(global)}
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

function surroundGraphPath(points) {
  if (!points.length) return '';
  if (points.length === 1) {
    return 'M ' + points[0].x + ' ' + points[0].y;
  }
  let path = 'M ' + points[0].x + ' ' + points[0].y;
  for (let index = 0; index < points.length - 1; index += 1) {
    const point = points[index];
    const next = points[index + 1];
    const midX = (point.x + next.x) / 2;
    const midY = (point.y + next.y) / 2;
    path += ' Q ' + point.x + ' ' + point.y + ' ' + midX + ' ' + midY;
  }
  const last = points[points.length - 1];
  path += ' Q ' + last.x + ' ' + last.y + ' ' + last.x + ' ' + last.y;
  return path;
}

function surroundEqSigma(q) {
  const number = Number(q);
  const safeQ = Number.isFinite(number) && number > 0 ? number : 0.71;
  return Math.max(0.04, Math.min(2.5, 0.75 / safeQ));
}

function surroundEqResponseAt(bands, frequency) {
  const logFrequency = Math.log2(frequency);
  return bands.reduce((total, band) => {
    const distance = (logFrequency - Math.log2(band.frequency))
      / surroundEqSigma(band.q);
    return total + band.gain * Math.exp(-0.5 * distance * distance);
  }, 0);
}

function surroundEqCurvePoints(bands, sampleCount = 256) {
  if (!bands.length) return [];
  const start = bands[0].frequency;
  const end = bands[bands.length - 1].frequency;
  if (!(end > start)) {
    return [{frequency: start, gain: surroundEqResponseAt(bands, start)}];
  }
  return Array.from({length: sampleCount}, (_, index) => {
    const fraction = index / (sampleCount - 1);
    const frequency = start * Math.pow(end / start, fraction);
    return {frequency, gain: surroundEqResponseAt(bands, frequency)};
  });
}

function surroundEqGraph(speaker) {
  const width = 960;
  const height = 250;
  const left = 42;
  const right = 12;
  const top = 14;
  const bottom = 32;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const minFreq = 20;
  const maxFreq = 20000;
  const minGain = -24;
  const maxGain = 12;
  const xFor = frequency => left + (
    Math.log10(Math.max(minFreq, Math.min(maxFreq, frequency)) / minFreq)
    / Math.log10(maxFreq / minFreq)) * plotWidth;
  const yFor = gain => top + (
    (maxGain - Math.max(minGain, Math.min(maxGain, gain)))
    / (maxGain - minGain)) * plotHeight;
  const bands = (speaker?.bands || []).map((band, index) => ({
    index,
    frequency: Number(band.freq_hz),
    gain: Number(band.gain_db),
    q: Number(band.q),
  })).filter(point => Number.isFinite(point.frequency) && Number.isFinite(point.gain))
    .sort((a, b) => a.frequency - b.frequency || a.index - b.index)
  if (!bands.length) {
    return '<div class="surround-eq-graph surround-empty">Waiting for the speaker EQ readback.</div>';
  }
  const points = bands.map(point => ({
    ...point, x: xFor(point.frequency), y: yFor(point.gain),
  }));

  const frequencyTicks = [[20, '20'], [50, '50'], [100, '100'], [200, '200'],
    [500, '500'], [1000, '1k'], [2000, '2k'], [5000, '5k'],
    [10000, '10k'], [20000, '20k']];
  const gainTicks = [-24, -12, 0, 12];
  const verticals = frequencyTicks.map(([value, label]) => {
    const x = xFor(value);
    return '<line x1="' + x + '" y1="' + top + '" x2="' + x
      + '" y2="' + (top + plotHeight) + '" />'
      + '<text x="' + x + '" y="' + (height - 10)
      + '" text-anchor="middle">' + label + '</text>';
  }).join('');
  const horizontals = gainTicks.map(value => {
    const y = yFor(value);
    return '<line x1="' + left + '" y1="' + y + '" x2="' + (width - right)
      + '" y2="' + y + '" />'
      + '<text x="' + (left - 7) + '" y="' + (y + 3)
      + '" text-anchor="end">' + value + '</text>';
  }).join('');
  const curve = surroundEqCurvePoints(bands).map(point => ({
    ...point, x: xFor(point.frequency), y: yFor(point.gain),
  }));
  const line = surroundGraphPath(curve);
  const area = line + ' L ' + curve[curve.length - 1].x + ' ' + (top + plotHeight)
    + ' L ' + curve[0].x + ' ' + (top + plotHeight) + ' Z';
  const markers = points.map(point => '<circle cx="' + point.x + '" cy="' + point.y + '" r="4">'
    + '<title>Band ' + (point.index + 1) + ': '
    + surroundNumber(point.frequency, 0) + ' Hz, '
    + surroundNumber(point.gain, 2) + ' dB, Q '
    + surroundNumber(point.q, 2) + '</title></circle>').join('');
  return '<div class="surround-eq-graph">'
    + '<svg viewBox="0 0 ' + width + ' ' + height + '" role="img"'
    + ' aria-label="Speaker EQ gain map from 20 Hz to 20 kHz">'
    + '<g class="surround-eq-gridlines">' + verticals + horizontals + '</g>'
    + '<path class="surround-eq-area" d="' + area + '" />'
    + '<path class="surround-eq-line" d="' + line + '" />'
    + '<g class="surround-eq-points">' + markers + '</g>'
    + '</svg>'
    + '<span class="surround-eq-graph-note">Q-shaped gain estimate from readback · bounded to the configured band span</span>'
    + '</div>';
}

function surroundKnobAngle(value, min, max, logarithmic = false) {
  const number = Number(value);
  let fraction = max > min ? (number - min) / (max - min) : 0;
  if (logarithmic && number > 0 && min > 0 && max > min) {
    fraction = (Math.log(number) - Math.log(min)) / (Math.log(max) - Math.log(min));
  }
  return (-135 + Math.max(0, Math.min(1, fraction)) * 270).toFixed(1);
}

function surroundEqKnob(field, value, min, max, step, unit, digits,
                        speaker, band, writable, logarithmic = false) {
  const number = Number(value);
  const current = Number.isFinite(number) ? number : min;
  const angle = surroundKnobAngle(current, min, max, logarithmic);
  const inputLabel = `${field} band ${band + 1}`;
  return '<div class="mixer-knob-control surround-eq-knob">'
    + '<output class="mixer-readout" data-surround-eq-value="'
    + surroundEscape(field) + '">' + surroundNumber(current, digits) + unit + '</output>'
    + '<div class="mixer-knob surround-knob" title="' + surroundEscape(inputLabel) + '">'
    + '<i style="transform:translateX(-50%) rotate(' + angle + 'deg)"></i>'
    + '<input type="range" data-surround-eq-input data-surround-eq-field="'
    + surroundEscape(field) + '" data-surround-eq-speaker="' + speaker
    + '" data-surround-eq-band="' + band + '" min="' + min + '" max="'
    + max + '" step="' + step + '" value="' + surroundEscape(current) + '"'
    + (writable ? '' : ' disabled') + ' aria-label="' + surroundEscape(inputLabel)
    + '"></div>'
    + '</div>';
}

function surroundEqModeSelect(mode, index, speaker, writable) {
  const current = Number(mode);
  const values = index === 0 ? [0, 4] : index === 15 ? [0, 1, 3] : [2];
  if (Number.isFinite(current) && !values.includes(current)) values.push(current);
  const options = values.map(value => '<option value="' + value + '"'
    + (value === current ? ' selected' : '') + '>' + surroundHex(value) + '</option>').join('');
  return '<label class="surround-eq-mode"><span>MODE</span>'
    + '<select data-surround-eq-input data-surround-eq-field="mode"'
    + ' data-surround-eq-speaker="' + speaker + '" data-surround-eq-band="'
    + index + '"' + (writable ? '' : ' disabled') + ' aria-label="band '
    + (index + 1) + ' mode">' + options + '</select></label>';
}

function surroundEqBand(band, index, speaker, writable) {
  return '<article class="surround-band">'
    + '<strong>' + (index + 1) + '</strong>'
    + surroundEqKnob('frequency', band.freq_hz, 20, 20000, 1, ' Hz', 0,
      speaker, index, writable, true)
    + surroundEqKnob('gain', band.gain_db, -24, 12, 0.01, ' dB', 2,
      speaker, index, writable)
    + surroundEqKnob('q', band.q, 0.1, 18, 0.01, '', 2,
      speaker, index, writable)
    + surroundEqModeSelect(band.mode, index, speaker, writable)
    + '</article>';
}

function surroundEqGrid(speaker, writable = false) {
  const bands = speaker?.bands || [];
  if (!bands.length) return '<p class="surround-empty">Waiting for the speaker EQ readback.</p>';
  return '<div class="surround-eq-layout">'
    + '<div class="surround-eq-legend" aria-hidden="true">'
    + '<strong></strong><span>F</span><span>G</span><span>Q</span><span>MODE</span>'
    + '</div><div class="surround-eq-grid">'
    + bands.map((band, index) => surroundEqBand(
      band, index, speaker.index, writable)).join('') + '</div></div>';
}

function surroundSpeakerHTML(data) {
  const count = data.speaker_count || data.speakers?.length || 16;
  const speaker = surroundSpeaker(SURROUND_SPEAKER, data);
  const eqWritable = data.write?.eq?.enabled === true && speaker.readback === true;
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
    <div class="surround-eq"><div class="surround-subhd"><h4>16-band EQ · single view</h4>
      <span class="surround-readonly">${eqWritable
        ? 'experimental write · one field at a time' : 'read-only · mode bytes stay raw'}</span></div>
      ${surroundEqGraph(speaker)}
      ${surroundEqGrid(speaker, eqWritable)}</div>
    <p class="surround-note">${eqWritable
      ? 'EQ changes write one frequency, gain, Q, or raw mode field at a time after a fresh readback; speaker delay, level and phase remain read-only.'
      : 'The per-speaker 0x87 frame is decoded for EQ readback. Its delay, level and phase head bytes remain candidate mappings, so the browser controls stay read-only.'}</p>
  </section>`;
}

function surroundEqDisplay(field, value) {
  if (field === 'frequency') return surroundNumber(value, 0) + ' Hz';
  if (field === 'gain') return surroundNumber(value, 2) + ' dB';
  if (field === 'q') return surroundNumber(value, 2);
  if (field === 'mode') return surroundHex(value);
  return surroundNumber(value);
}

function surroundEqPaint(input) {
  if (!input) return;
  const field = input.dataset.surroundEqField;
  const value = Number(input.value);
  const output = input.closest('.surround-eq-knob')?.querySelector(
    '[data-surround-eq-value]');
  if (output) output.textContent = surroundEqDisplay(field, value);
  const pointer = input.closest('.mixer-knob')?.querySelector('i');
  if (pointer) pointer.style.transform = 'translateX(-50%) rotate('
    + surroundKnobAngle(value, +input.min, +input.max, field === 'frequency') + 'deg)';
}

function initSurroundEqControls(host) {
  host.querySelectorAll('[data-surround-eq-input]').forEach(input => {
    if (!input.disabled && input.type === 'range'
        && typeof wirePrecisionRange === 'function') wirePrecisionRange(input);
    surroundEqPaint(input);
  });
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
  initSurroundEqControls(host);
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
      const eq = event.target.closest?.('[data-surround-eq-input]');
      if (eq) {
        surroundEqPaint(eq);
        return;
      }
      const input = event.target.closest('[data-surround-global]');
      if (!input) return;
      const value = Number(input.value);
      const unit = input.dataset.surroundGlobal === 'delay_ms' ? 'ms' : 'dB';
      const readout = host.querySelector(`[data-surround-value="${input.dataset.surroundGlobal}"]`);
      if (readout) readout.textContent = `${surroundNumber(value)} ${unit}`;
    });
    const setBassModal = (modal, open) => {
      if (!modal) return;
      modal.hidden = !open;
      host.querySelector('[data-surround-bass-open]')?.setAttribute(
        'aria-expanded', String(open));
      if (open) modal.querySelector('[data-surround-bass-close]')?.focus();
    };
    host.addEventListener('click', event => {
      const open = event.target.closest?.('[data-surround-bass-open]');
      if (open) {
        setBassModal(host.querySelector('[data-surround-bass-modal]'), true);
        return;
      }
      const modal = event.target.closest?.('[data-surround-bass-modal]');
      const close = event.target.closest?.('[data-surround-bass-close]');
      if (modal && (close || event.target === modal)) setBassModal(modal, false);
    });
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      const modal = host.querySelector('[data-surround-bass-modal]');
      if (modal && !modal.hidden) setBassModal(modal, false);
    });
    host.addEventListener('change', event => {
      const eq = event.target.closest?.('[data-surround-eq-input]');
      if (eq && !eq.disabled) {
        surroundEqPaint(eq);
        post('/api/surround/eq', {
          speaker: Number(eq.dataset.surroundEqSpeaker),
          band: Number(eq.dataset.surroundEqBand),
          parameter: eq.dataset.surroundEqField,
          value: Number(eq.value),
        });
        return;
      }
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
