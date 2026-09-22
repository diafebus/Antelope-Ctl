"use strict";

// Surround monitor, bass management, and speaker EQ UI.

// ---- surround monitor ---------------------------------------------------
let SURROUND = null;
let SURROUND_SPEAKER = 0;
let SURROUND_BUILT = false;
let SURROUND_BASS_WINDOW = null;

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
    head_readback: false,
    bypass: false,
    bypass_readback: false,
    bands: [],
  };
}

function surroundSpeakerOverview(data) {
  const global = data?.global || {};
  const count = Number(data?.speaker_count || data?.speakers?.length || 16);
  const flag = (mask, index) => (Number(mask || 0) & (1 << index)) !== 0;
  const nodes = Array.from({length: count}, (_, index) => {
    const speaker = surroundSpeaker(index, data);
    const active = speaker.active !== false;
    const selected = index === SURROUND_SPEAKER;
    const bypassed = speaker.bypass === true;
    const muted = flag(global.mute_mask, index);
    const dimmed = flag(global.dim_mask, index);
    const label = speaker.label || `Speaker ${index + 1}`;
    const states = `<span class="surround-speaker-flags" aria-label="${surroundEscape(label)} state">
      <i class="${bypassed ? 'on' : ''}" title="${bypassed ? 'Bypassed' : 'Processing active'}">B</i>
      <i class="${muted ? 'on' : ''}" title="${muted ? 'Muted' : 'Not muted'}">M</i>
      <i class="${dimmed ? 'on' : ''}" title="${dimmed ? 'Dimmed' : 'Not dimmed'}">D</i>
    </span>`;
    return `<button type="button" class="surround-speaker-node${active ? '' : ' inactive'}${selected ? ' selected' : ''}"
      data-surround-speaker-select="${index}"${active ? '' : ' disabled'}
      title="${surroundEscape(label)}${active ? ' · select speaker' : ' · inactive for this layout'}"
      aria-pressed="${selected ? 'true' : 'false'}" aria-label="${surroundEscape(label)}${active ? '' : ', inactive'}">
      <b>${index + 1}</b><strong>${surroundEscape(label)}</strong>${states}</button>`;
  }).join('');
  return `<section class="surround-speaker-overview" aria-label="Surround speaker overview">
    <div class="surround-overview-head"><strong>Speakers</strong>
      <span class="surround-meta">B bypass · M mute · D dim</span></div>
    <div class="surround-speaker-map">${nodes}</div>
  </section>`;
}

function surroundRangeInput(field, label, value, range, unit, writable, step = 0.1) {
  const [min, max] = range;
  const fallback = field === 'delay_ms' ? min : 0;
  const current = Number.isFinite(Number(value)) ? Number(value) : fallback;
  const display = Number.isFinite(Number(value))
    ? `${surroundNumber(value)} ${unit}` : 'waiting';
  const angle = surroundKnobAngle(current, min, max);
  return `<div class="surround-monitor-knob">
    <span class="surround-monitor-label">${surroundEscape(label)}</span>
    <output class="mixer-readout surround-monitor-readout" data-surround-value="${field}">${display}</output>
    <div class="mixer-knob surround-monitor-dial" title="${surroundEscape(label)} · drag up/down for precision">
      <i style="transform:translateX(-50%) rotate(${angle}deg)"></i>
      <input type="range" data-surround-global="${field}" min="${min}" max="${max}"
        step="${step}" value="${current}"
        data-precision-drag-pixels="${field === 'level_db' ? 760 : 40}"${writable ? '' : ' disabled'}
        aria-label="${surroundEscape(label)}">
    </div>
    <span class="surround-readonly">${writable ? 'drag ↑↓ · wheel' : 'read-only'}</span>
  </div>`;
}

const SURROUND_FORMAT_CHANNEL_ORDER = {
  '2.0': [1, 3],
  '2.1': [1, 3, 4],
  '3.0': [1, 3, 2],
  '3.1': [1, 3, 2, 4],
  '4.0': [1, 3, 2, 5],
  '4.1': [1, 3, 2, 4, 5],
  '5.0': [1, 3, 2, 7, 10],
  '5.1': [1, 3, 2, 4, 7, 10],
  '5.1.2': [1, 3, 2, 4, 7, 10, 13, 16],
  '5.1.4': [1, 3, 2, 4, 7, 10, 12, 15, 14, 17],
  '7.0': [1, 3, 2, 7, 10, 8, 11],
  '7.0.2': [1, 3, 2, 7, 10, 8, 11, 13, 16],
  '7.1': [1, 3, 2, 4, 7, 10, 8, 11],
  '7.1.2': [1, 3, 2, 4, 7, 10, 8, 11, 13, 16],
  '7.1.4': [1, 3, 2, 4, 7, 10, 8, 11, 12, 15, 14, 17],
  '7.1.6': [1, 3, 2, 4, 7, 10, 8, 11, 12, 15, 13, 16, 14, 17],
  '9.1.2': [1, 3, 2, 4, 7, 10, 8, 11, 6, 9, 13, 16],
  '9.1.4': [1, 3, 2, 4, 7, 10, 8, 11, 6, 9, 12, 15, 14, 17],
  '9.1.6': [1, 3, 2, 4, 7, 10, 8, 11, 6, 9, 12, 15, 13, 16, 14, 17],
};

const SURROUND_BASS_CHANNEL_LABELS = {
  1: 'L', 2: 'C', 3: 'R', 4: 'LFE', 5: 'S',
  6: 'Lw', 7: 'Lss', 8: 'Lrs', 9: 'Rw', 10: 'Rss', 11: 'Rrs',
  12: 'Ltf', 13: 'Ltm', 14: 'Ltr', 15: 'Rtf', 16: 'Rtm', 17: 'Rtr',
};

const SURROUND_BASS_DEFAULT_BLOCK = {
  lp_cutoff_hz: 80,
  hp_cutoff_hz: 80,
  lp_bypass: false,
  hp_bypass: false,
  lp_order: 0,
  hp_order: 0,
  fader_db: 0,
  fader_mute: false,
  fader_solo: false,
  readback: false,
};

function surroundBassFormatOption(data) {
  const format = data?.global?.format;
  return (data?.write?.format?.options || []).find(item => item?.name === format)
    || null;
}

function surroundBassChannelOrder(data) {
  const option = surroundBassFormatOption(data);
  if (Array.isArray(option?.channel_order) && option.channel_order.length) {
    return option.channel_order.map(Number).filter(Number.isFinite);
  }
  const format = data?.global?.format;
  const fallback = SURROUND_FORMAT_CHANNEL_ORDER[format];
  if (fallback) return [...fallback];
  const count = Number(data?.active_speaker_count || data?.speaker_count || 0);
  return Array.from({length: count}, (_, index) => index + 1);
}

function surroundBassChannelLabel(channelId) {
  return SURROUND_BASS_CHANNEL_LABELS[channelId] || `CH${channelId}`;
}

function surroundBassGroup(channelId) {
  if (channelId === 4) return 'lfe';
  if ([1, 2, 3].includes(channelId)) return 'front';
  if (channelId >= 12 && channelId <= 17) return 'height';
  return 'surround';
}

function surroundBassChannels(data) {
  const global = data?.global || {};
  const blocks = global.bass_mgmt_channels || [];
  const blocksByChannel = new Map();
  blocks.forEach((block, index) => {
    if (!block || block.channel_id == null) return;
    const channelId = Number(block.channel_id);
    if (Number.isFinite(channelId) && !blocksByChannel.has(channelId)) {
      blocksByChannel.set(channelId, {...block, _wireSlot: Number.isInteger(
        Number(block.slot)) ? Number(block.slot) : index});
    }
  });
  const filterTypes = global.bass_mgmt_filter_types || {};
  const channels = surroundBassChannelOrder(data).map((channelId, orderSlot) => {
    const identified = blocksByChannel.get(channelId);
    const positional = blocks[orderSlot];
    const selected = identified || positional || null;
    const wireSlot = identified ? identified._wireSlot : (
      Number.isInteger(Number(positional?.slot)) ? Number(positional.slot) : orderSlot);
    return {
      channelId,
      slot: wireSlot,
      orderSlot,
      label: surroundBassChannelLabel(channelId),
      group: surroundBassGroup(channelId),
      lfe: channelId === 4,
      filterTypes,
      block: {...SURROUND_BASS_DEFAULT_BLOCK, ...(selected || {}),
        readback: !!selected},
    };
  });
  const lfeIndex = channels.findIndex(channel => channel.lfe);
  if (global.format !== '2.1' && lfeIndex > 0) {
    channels.unshift(channels.splice(lfeIndex, 1)[0]);
  }
  return channels;
}

function surroundBassValue(value, digits = 0, fallback = '–') {
  return Number.isFinite(Number(value)) ? surroundNumber(value, digits) : fallback;
}

function surroundBassOrder(value) {
  return ({0: '2', 1: '4', 2: '8'})[Number(value)] || '–';
}

function surroundBassFieldWritable(write, field) {
  return write?.enabled === true && Array.isArray(write.fields)
    && write.fields.includes(field);
}

function surroundBassMappingSuffix(write) {
  return write?.experimental ? ' · experimental candidate mapping' : '';
}

function surroundBassKnob(value, label, field, channel, bassWrite) {
  const current = Number.isFinite(Number(value)) ? Number(value) : 80;
  const angle = surroundKnobAngle(current, 20, 320, true);
  const writable = surroundBassFieldWritable(bassWrite, field);
  return '<div class="mixer-knob-control bass-knob-control">'
    + '<output class="mixer-readout bass-readout" data-bass-readout>'
    + surroundBassValue(current) + ' Hz</output>'
    + '<div class="mixer-knob bass-knob" title="' + surroundEscape(label) + '">'
    + '<i style="transform:translateX(-50%) rotate(' + angle + 'deg)"></i>'
    + '<input type="range" data-bass-input data-bass-knob data-logarithmic="true"'
    + ' data-bass-field="' + surroundEscape(field) + '" data-bass-slot="'
    + channel.slot + '" min="20" max="320" step="1" value="' + current
    + '"' + (writable ? '' : ' disabled') + ' aria-label="'
    + surroundEscape(label) + '"></div></div>';
}

function surroundBassChip(value, label, className = '') {
  return '<div class="bass-chip ' + className + '" title="'
    + surroundEscape(label) + '"><span>' + surroundEscape(value) + '</span></div>';
}

function surroundBassFilterType(value, label, field, channel, bassWrite) {
  const configured = bassWrite?.filter_type_values?.[field];
  const values = Array.isArray(configured) ? configured.map(item =>
    typeof item === 'object' ? item : {value: item, label: item}) : [];
  if (!values.length) return surroundBassChip(value, label, 'bass-filter-type');
  const current = value == null ? values[0].value : value;
  const writable = surroundBassFieldWritable(bassWrite, field);
  const hasCurrent = values.some(item => String(item.value) === String(current));
  const unknown = hasCurrent ? '' : '<option selected disabled value="">'
    + surroundEscape(current) + '</option>';
  const options = values.map(item => '<option value="'
    + surroundEscape(item.value) + '"'
    + (String(item.value) === String(current) ? ' selected' : '') + '>'
    + surroundEscape(item.label ?? item.value) + '</option>').join('');
  return '<select class="bass-chip bass-filter-type" data-bass-input'
    + ' data-bass-filter-type="true" data-bass-field="'
    + surroundEscape(field) + '" data-bass-slot="' + channel.slot
    + '" aria-label="' + surroundEscape(label) + '" title="'
    + surroundEscape(label + surroundBassMappingSuffix(bassWrite)) + '"'
    + (writable ? '' : ' disabled') + '>' + unknown + options + '</select>';
}

function surroundBassOrderControl(value, label, field, channel, bassWrite) {
  const current = surroundBassOrder(value);
  const writable = surroundBassFieldWritable(bassWrite, field);
  const options = ['2', '4', '8'].map(order => '<option value="' + order + '"'
    + (order === current ? ' selected' : '') + '>' + order + '</option>').join('');
  return '<select class="bass-chip bass-order-control" data-bass-input'
    + ' data-bass-field="' + surroundEscape(field) + '" data-bass-slot="'
    + channel.slot + '" aria-label="' + surroundEscape(label) + '"'
    + (writable ? '' : ' disabled') + '>' + options + '</select>';
}

function surroundBassBypass(on, label, field, channel, bassWrite) {
  const writable = surroundBassFieldWritable(bassWrite, field);
  return '<button class="bass-bypass' + (on ? ' on' : '') + '" type="button"'
    + ' data-bass-input data-bass-boolean="true" data-bass-field="'
    + surroundEscape(field) + '" data-bass-slot="' + channel.slot
    + '" aria-pressed="' + (on ? 'true' : 'false') + '"'
    + (writable ? '' : ' disabled') + ' title="' + surroundEscape(label)
    + '">BP</button>';
}

function surroundBassFilter(channel, side, bassWrite) {
  const block = channel.block;
  const highPass = side === 'hp';
  const cutoff = highPass ? block.hp_cutoff_hz : block.lp_cutoff_hz;
  const bypass = highPass ? block.hp_bypass : block.lp_bypass;
  const order = highPass ? block.hp_order : block.lp_order;
  const cutoffField = highPass ? 'hp_cutoff_hz' : 'lp_cutoff_hz';
  const bypassField = highPass ? 'hp_bypass' : 'lp_bypass';
  const orderField = highPass ? 'hp_order' : 'lp_order';
  const typeField = highPass ? 'hp_filter_type' : 'lp_filter_type';
  const label = (highPass ? 'High-pass' : 'Low-pass') + ' ' + channel.label;
  const filterType = channel.filterTypes?.[highPass ? 'hp' : 'lp']
    ?? (channel.lfe && !highPass ? 'L-R' : 'BW');
  if (channel.lfe && highPass) {
    return '<div class="bass-filter bass-filter-empty" aria-hidden="true"></div>';
  }
  return '<div class="bass-filter bass-filter-' + side + '">'
    + '<div class="bass-filter-spacer"></div>'
    + surroundBassKnob(cutoff, label + ' cutoff', cutoffField, channel, bassWrite)
    + surroundBassFilterType(filterType, label + ' filter type', typeField,
      channel, bassWrite)
    + surroundBassOrderControl(order, label + ' filter order',
      orderField, channel, bassWrite)
    + surroundBassBypass(bypass, label + ' bypass', bypassField, channel, bassWrite)
    + '</div>';
}

function surroundBassFader(channel, bassWrite) {
  const fader = Number.isFinite(Number(channel.block.fader_db))
    ? Number(channel.block.fader_db) : 0;
  const configuredRange = bassWrite.fader_range_db;
  const range = Array.isArray(configuredRange) && configuredRange.length === 2
    ? configuredRange.map(Number) : [-60, 16];
  const min = Number.isFinite(range[0]) ? range[0] : -60;
  const max = Number.isFinite(range[1]) ? range[1] : 16;
  const rangeValue = Math.max(min, Math.min(max, fader));
  const faderWritable = surroundBassFieldWritable(bassWrite, 'fader_db');
  const muteWritable = surroundBassFieldWritable(bassWrite, 'fader_mute');
  const soloWritable = surroundBassFieldWritable(bassWrite, 'fader_solo');
  const soloOn = !!channel.block.fader_solo;
  return '<div class="bass-mixer-section">'
    + '<output class="mxval bass-fader-value" data-bass-readout data-bass-fader-readout'
    + ' title="' + (faderWritable ? 'Double-click to enter an exact dB value' : 'Read-only') + '">'
    + surroundBassValue(fader, 1) + 'dB</output>'
    + '<input class="mxval bass-fader-value bass-fader-number" type="number"'
    + ' data-bass-fader-number min="' + min + '" max="' + max + '" step="0.1"'
    + ' value="' + rangeValue + '" hidden aria-label="'
    + surroundEscape(channel.label) + ' bass-management fader dB value">'
    + '<div class="mixer-fader-row bass-fader-row">'
    + '<div class="mixer-fader-well">'
    + '<span class="mixer-fader-thumb" aria-hidden="true">'
    + '<img class="mixer-fader-art" src="/webui/assets/fader-shadow.svg" alt="" draggable="false">'
    + '</span>'
    + '<input class="mixer-fader" type="range" data-fader data-bass-fader data-bass-input'
    + ' data-bass-field="fader_db" data-bass-slot="' + channel.slot + '"'
    + ' min="' + min + '" max="' + max + '" step="0.1" value="' + rangeValue
    + '" data-precision-drag-pixels="760'
    + '"' + (faderWritable ? '' : ' disabled') + ' aria-label="'
    + surroundEscape(channel.label) + ' bass-management fader">'
    + '</div>'
    + '<div class="mixer-meter bass-meter" title="Bass-management meter unavailable pending Launcher capture">'
    + '<i class="unavailable" data-bass-meter></i></div>'
    + '</div>'
    + '<div class="bass-mixer-buttons">'
    + '<button type="button" class="bass-mixer-button bass-mute'
    + (channel.block.fader_mute ? ' on' : '') + '" data-bass-input'
    + ' data-bass-boolean="true" data-bass-field="fader_mute" data-bass-slot="'
    + channel.slot + '" aria-pressed="' + (channel.block.fader_mute ? 'true' : 'false')
    + '"' + (muteWritable ? '' : ' disabled') + ' aria-label="'
    + surroundEscape(channel.label) + ' mute">M</button>'
    + '<button type="button" class="bass-mixer-button bass-solo'
    + (soloOn ? ' on' : '') + '" data-bass-input'
    + ' data-bass-boolean="true" data-bass-field="fader_solo" data-bass-slot="'
    + channel.slot + '" aria-pressed="' + (soloOn ? 'true' : 'false')
    + '"' + (soloWritable ? '' : ' disabled') + ' title="'
    + surroundEscape(channel.label + ' solo' + surroundBassMappingSuffix(bassWrite))
    + '" aria-label="' + surroundEscape(channel.label) + ' solo">S</button>'
    + '</div></div>';
}

function surroundBassStrip(channel, bassWrite) {
  return '<article class="bass-strip bass-group-' + channel.group
    + '" data-bass-channel="' + channel.channelId + '" data-bass-slot="'
    + channel.slot + '">'
    + '<header class="bass-strip-header"><strong>' + surroundEscape(channel.label) + '</strong></header>'
    + surroundBassFilter(channel, 'hp', bassWrite)
    + surroundBassFilter(channel, 'lp', bassWrite)
    + surroundBassFader(channel, bassWrite)
    + '</article>';
}

function surroundBassLink(label, field, linkStates, bassWrite) {
  const linkIcon = typeof LINK_ICON === 'string' ? LINK_ICON : '↔';
  const writable = field && surroundBassFieldWritable(bassWrite, field);
  const on = !!(field && linkStates?.[field]);
  if (!field) {
    return '<button class="bass-link" type="button" disabled title="'
      + surroundEscape(label + ' · mapping pending capture') + '" aria-label="'
      + surroundEscape(label) + '">' + linkIcon + '</button>';
  }
  return '<button class="bass-link' + (on ? ' on' : '')
    + '" type="button" data-bass-input data-bass-boolean="true"'
    + ' data-bass-field="' + surroundEscape(field)
    + '" data-bass-slot="0" aria-pressed="' + (on ? 'true' : 'false')
    + '"' + (writable ? '' : ' disabled') + ' title="'
    + surroundEscape(label + surroundBassMappingSuffix(bassWrite))
    + '" aria-label="' + surroundEscape(label) + '">' + linkIcon + '</button>';
}

function surroundBassRail(bassWrite = {}, linkStates = {}) {
  const field = name => Array.isArray(bassWrite.link_fields)
    && bassWrite.link_fields.includes(name) ? name : null;
  const link = (label, name) => surroundBassLink(
    label, field(name), linkStates, bassWrite);
  return '<aside class="bass-rail">'
    + '<div class="bass-rail-head"></div>'
    + '<section class="bass-rail-filter"><strong>HIGH PASS</strong>'
    + '<span>CUTOFF ' + link('Link high-pass cutoff', 'link_hp_cutoff') + '</span>'
    + '<span>FILTER TYPE ' + link('Link high-pass filter type', 'link_hp_filter_type') + '</span>'
    + '<span>FILTER ORDER ' + link('Link high-pass order', 'link_hp_order') + '</span>'
    + '<span>BYPASS ' + link('Link high-pass bypass', 'link_hp_bypass') + '</span></section>'
    + '<section class="bass-rail-filter"><strong>LOW PASS</strong>'
    + '<span>CUTOFF ' + link('Link low-pass cutoff', 'link_lp_cutoff') + '</span>'
    + '<span>FILTER TYPE ' + link('Link low-pass filter type', 'link_lp_filter_type') + '</span>'
    + '<span>FILTER ORDER ' + link('Link low-pass order', 'link_lp_order') + '</span>'
    + '<span>BYPASS ' + link('Link low-pass bypass', 'link_lp_bypass') + '</span></section>'
    + '<section class="bass-rail-mixer"><strong>MIXER</strong>'
    + '<span>CONTROL ' + link('Link mixer controls', 'link_mixer') + '</span></section></aside>';
}

function surroundBassManagement(data, bassWrite = data?.write?.bass || {}) {
  const channels = surroundBassChannels(data);
  if (!channels.length) return '<p class="surround-empty">No active bass-management channels in this format.</p>';
  return '<div class="bass-board-scroll"><div class="bass-board" style="--bass-count:'
    + channels.length + '">' + surroundBassRail(bassWrite,
      data?.global?.bass_mgmt_links || {})
    + channels.map(channel => surroundBassStrip(channel, bassWrite)).join('') + '</div></div>';
}

function surroundBassWindowHTML(data) {
  const global = data?.global || {};
  const channels = surroundBassChannels(data);
  const bassWrite = data?.write?.bass || {};
  const format = global.format || 'unknown';
  const candidateNote = bassWrite.experimental
    ? 'filter type, link, and solo are experimental candidates'
    : 'filter type, link, and solo confirmed by readback';
  const bassStatus = bassWrite.enabled
    ? (bassWrite.experimental ? 'experimental read/write' : 'read/write')
    : (Array.isArray(bassWrite.formats) && bassWrite.formats.length
      ? 'read-only · select ' + bassWrite.formats.join(' / ') + ' to enable'
      : 'read-only');
  return '<div class="surround-bass-dialog" style="--bass-count:' + channels.length
    + '" role="dialog" aria-modal="true"'
    + ' aria-labelledby="surround-bass-title">'
    + '<div class="surround-bass-window-hd"><strong id="surround-bass-title">BASS MANAGEMENT</strong>'
    + '<span class="surround-meta">' + surroundEscape(format) + ' · '
    + channels.length + ' strips</span>'
    + '<button class="modal-x" type="button" data-surround-bass-close aria-label="close">&times;</button></div>'
    + '<div class="surround-bass-window-bd">'
    + '<div class="bass-toolbar"><span>HIGH PASS · LOW PASS · MIXER</span>'
    + '<span class="surround-readonly">'
    + surroundEscape(bassStatus)
    + ' · ' + candidateNote + '; meters pending</span></div>'
    + surroundBassManagement(data, bassWrite)
    + '<p class="surround-note bass-note">Only the strips active in the selected Surround format are shown. In 2.1 the strips run L · R · LFE, with LFE highlighted in purple; larger layouts keep the compact LFE-first presentation. Known writes cover cutoffs, filter order, bypass, faders, mute, filter type, Link, and Solo. '
    + surroundEscape(bassWrite.note || 'Bass Management meters remain unavailable.') + '</p>'
    + '</div></div>';
}

function surroundBassPopupHTML(data) {
  return '<main class="surround-bass-popup-page">'
    + surroundBassWindowHTML(data) + '</main>';
}

function surroundBassPaint(input) {
  if (!input) return;
  const field = input.dataset.bassField;
  if (field === 'fader_db') {
    const value = Number(input.value);
    const output = input.closest('.bass-mixer-section')?.querySelector(
      '[data-bass-fader-readout]');
    if (output) output.textContent = `${surroundBassValue(value, 1)}dB`;
    const number = input.closest('.bass-mixer-section')?.querySelector(
      '[data-bass-fader-number]');
    if (number?.hidden) number.value = String(value);
    paintSurroundBassFader(input.closest('.bass-strip'), input.value);
    return;
  }
  const value = Number(input.value);
  const output = input.closest('.bass-knob-control')?.querySelector(
    '[data-bass-readout]');
  if (output) output.textContent = `${surroundBassValue(value)} Hz`;
  const pointer = input.closest('.bass-knob')?.querySelector('i');
  if (pointer) pointer.style.transform = 'translateX(-50%) rotate('
    + surroundKnobAngle(value, +input.min, +input.max, true) + 'deg)';
}

function surroundBassFaderFraction(value, min = -60, max = 16) {
  const number = Number(value);
  const low = Number(min), high = Number(max);
  if (!Number.isFinite(number) || !Number.isFinite(low)
      || !Number.isFinite(high) || high === low) return 0.5;
  return Math.max(0, Math.min(1, (high - number) / (high - low)));
}

function paintSurroundBassFader(strip, value) {
  if (!strip) return;
  const fader = strip.querySelector('[data-bass-fader]');
  const thumb = strip.querySelector('.mixer-fader-thumb');
  const art = strip.querySelector('.mixer-fader-art');
  if (!fader || !thumb) return;
  // The native range is inset by 4px on both ends of the well. Use its
  // actual client height so the artwork follows the same travel as the
  // hidden input, rather than the larger containing well.
  const span = fader.clientHeight || 114;
  const fraction = surroundBassFaderFraction(value, fader.min, fader.max);
  // Match the native range thumb's 20 px travel rather than compressing the
  // visible artwork into a much shorter 50 px handle range.
  const trackHandle = 20;
  const pos = trackHandle / 2 + fraction * Math.max(0, span - trackHandle);
  thumb.style.setProperty('--fader-pos', pos.toFixed(1) + 'px');
  // Set the actual artwork position as well as the CSS variable. This keeps
  // newly opened popup windows accurate even if their stylesheet settles a
  // frame after the first paint.
  if (!art) return;
  const artHeight = art.getBoundingClientRect().height || 66;
  art.style.top = (4 + pos - artHeight / 2).toFixed(1) + 'px';
}

function surroundBassInputValue(input) {
  if (input.dataset.bassBoolean === 'true') return input.classList.contains('on');
  if (input.dataset.bassFilterType === 'true' || input.tagName === 'SELECT') {
    return input.value;
  }
  const value = Number(input.value);
  if (!Number.isFinite(value)) return null;
  return value;
}

function postSurroundBassInput(input) {
  if (!input || input.disabled) return;
  const value = surroundBassInputValue(input);
  if (value == null) return;
  post('/api/surround/bass', {
    channel: Number(input.dataset.bassSlot),
    field: input.dataset.bassField,
    value,
  });
}

function surroundBassFaderSnap(value, fader) {
  const number = Number(value), min = Number(fader?.min), max = Number(fader?.max);
  const step = Number(fader?.step) || 0.1;
  if (![number, min, max, step].every(Number.isFinite) || step <= 0 || max < min) {
    return null;
  }
  const snapped = min + Math.round((number - min) / step) * step;
  return Math.max(min, Math.min(max, snapped));
}

function beginSurroundBassFaderEdit(readout) {
  const section = readout?.closest('.bass-mixer-section');
  const fader = section?.querySelector('[data-bass-fader]');
  const number = section?.querySelector('[data-bass-fader-number]');
  if (!fader || !number || fader.disabled) return;
  readout.hidden = true;
  number.hidden = false;
  number.value = fader.value;
  number.focus();
  number.select();
}

function finishSurroundBassFaderEdit(number, commit = true) {
  const section = number?.closest('.bass-mixer-section');
  const fader = section?.querySelector('[data-bass-fader]');
  const readout = section?.querySelector('[data-bass-fader-readout]');
  if (!fader || !readout) return;
  const value = surroundBassFaderSnap(number.value, fader);
  if (value != null) {
    fader.value = String(value);
    surroundBassPaint(fader);
    if (commit) postSurroundBassInput(fader);
  }
  number.hidden = true;
  readout.hidden = false;
}

function initSurroundBassControls(host) {
  host.querySelectorAll('[data-bass-knob]').forEach(input => {
    if (!input.disabled && typeof wirePrecisionRange === 'function') {
      wirePrecisionRange(input);
    }
    surroundBassPaint(input);
  });
  const repaintFaders = () => host.querySelectorAll('[data-bass-fader]').forEach(input => {
    if (!input.disabled && typeof wirePrecisionRange === 'function') {
      wirePrecisionRange(input);
    }
    surroundBassPaint(input);
  });
  repaintFaders();
  // A newly opened popup can paint once before its external stylesheet has
  // produced the final layout. Repaint on the next frame so the thumb starts
  // at the position represented by the restored dB value.
  const view = host.ownerDocument?.defaultView;
  if (typeof view?.requestAnimationFrame === 'function') {
    view.requestAnimationFrame(() => view.requestAnimationFrame(repaintFaders));
  }
  // The popup's stylesheet can finish after its first layout frame.  Repaint
  // once it loads as well, so the artwork uses the final (not zero-height)
  // range rail instead of merely the correct numeric readout.
  host.ownerDocument?.querySelector('link[href*="surround.css"]')
    ?.addEventListener('load', repaintFaders, {once: true});
}

function surroundBassWindowIsOpen() {
  return SURROUND_BASS_WINDOW && !SURROUND_BASS_WINDOW.closed;
}

function setSurroundBassLauncherState(open) {
  document.querySelector('[data-surround-bass-open]')?.setAttribute(
    'aria-expanded', String(open));
}

function initSurroundBassPopup(popup) {
  const host = popup?.document?.body;
  if (!host) return;
  if (host.dataset.surroundBassPopupWired !== '1') {
    host.addEventListener('input', event => {
      const bass = event.target.closest?.('[data-bass-input]');
      if (bass) surroundBassPaint(bass);
    });
    host.addEventListener('change', event => {
      const number = event.target.closest?.('[data-bass-fader-number]');
      if (number) {
        finishSurroundBassFaderEdit(number);
        return;
      }
      const bass = event.target.closest?.('[data-bass-input]');
      if (bass && !bass.disabled) postSurroundBassInput(bass);
    });
    host.addEventListener('dblclick', event => {
      const readout = event.target.closest?.('[data-bass-fader-readout]');
      if (readout) beginSurroundBassFaderEdit(readout);
    });
    host.addEventListener('keydown', event => {
      const number = event.target.closest?.('[data-bass-fader-number]');
      if (!number) return;
      if (event.key === 'Enter') {
        event.preventDefault();
        finishSurroundBassFaderEdit(number);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        finishSurroundBassFaderEdit(number, false);
      }
    });
    host.addEventListener('click', event => {
      const close = event.target.closest?.('[data-surround-bass-close]');
      if (close) {
        popup.close();
        return;
      }
      const bassBoolean = event.target.closest?.(
        '[data-bass-input][data-bass-boolean]');
      if (!bassBoolean || bassBoolean.disabled) return;
      const on = !bassBoolean.classList.contains('on');
      bassBoolean.classList.toggle('on', on);
      bassBoolean.setAttribute('aria-pressed', String(on));
      postSurroundBassInput(bassBoolean);
    });
    host.dataset.surroundBassPopupWired = '1';
  }
  initSurroundBassControls(host);
}

function refreshSurroundBassWindow() {
  if (!surroundBassWindowIsOpen()) {
    SURROUND_BASS_WINDOW = null;
    setSurroundBassLauncherState(false);
    return;
  }
  const popup = SURROUND_BASS_WINDOW;
  popup.document.body.innerHTML = surroundBassPopupHTML(SURROUND);
  initSurroundBassPopup(popup);
}

function openSurroundBassWindow() {
  if (!SURROUND) return;
  if (surroundBassWindowIsOpen()) {
    SURROUND_BASS_WINDOW.focus();
    return;
  }
  const popup = window.open('', 'antelopeBassManagement',
    'popup=yes,location=no,toolbar=no,menubar=no,status=no,'
    + 'scrollbars=yes,resizable=yes,width=1240,height=760');
  if (!popup) {
    if (typeof reportMessage === 'function') {
      reportMessage('comm', 'Bass Management popup blocked',
        'Allow popups for this page to open Bass Management in a separate window.');
    }
    return;
  }
  SURROUND_BASS_WINDOW = popup;
  const d = popup.document;
  d.open();
  d.write('<!doctype html><html><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>Bass Management — antelope-ctl</title>'
    + '<link rel="stylesheet" href="/webui/static/app.css">'
    + '<link rel="stylesheet" href="/webui/static/surround.css?v=surround-controls-v11">'
    + '</head><body class="bass-popup-body"></body></html>');
  d.close();
  d.body.innerHTML = surroundBassPopupHTML(SURROUND);
  popup.addEventListener('pagehide', () => {
    if (SURROUND_BASS_WINDOW !== popup) return;
    SURROUND_BASS_WINDOW = null;
    setSurroundBassLauncherState(false);
  }, {once: true});
  setSurroundBassLauncherState(true);
  initSurroundBassPopup(popup);
  popup.focus();
}

function surroundGlobalHTML(data) {
  const global = data.global;
  const write = data.write || {};
  const writable = write.enabled === true;
  const delayRange = write.delay_ms_range?.length === 2 ? write.delay_ms_range : [0.6, 4.5];
  const levelRange = write.level_db_range?.length === 2 ? write.level_db_range : [-60, 16];
  const format = global?.format || (global?.lfe_present ? '2.1' : '2.0');
  const formatWrite = write.format || {};
  const eqPositionWrite = write.eq_position || {};
  const eqPositionWritable = eqPositionWrite.enabled === true;
  const eqPosition = global?.eq_post ? 'post' : 'pre';
  const eqPositionValues = eqPositionWrite.fields?.length
    ? eqPositionWrite.fields : ['pre', 'post'];
  const eqPositionOptions = eqPositionValues.map(value =>
    '<option value="' + surroundEscape(value) + '"'
      + (value === eqPosition ? ' selected' : '') + '>'
      + surroundEscape(String(value).toUpperCase()) + '</option>').join('');
  const formatItems = formatWrite.options?.length
    ? formatWrite.options
    : SURROUND_FORMAT_OPTIONS.map(name => ({
      name, writable: name === '2.0' || name === '2.1',
    }));
  const formatOptions = formatItems.map(item => {
    const name = typeof item === 'string' ? item : item.name;
    const safeName = surroundEscape(name);
    const optionWritable = typeof item === 'string'
      ? name === '2.0' || name === '2.1' : item.writable === true;
    return '<option value="' + safeName + '"' + (name === format ? ' selected' : '')
      + (optionWritable ? '' : ' disabled') + '>' + safeName + '</option>';
  }).join('');
  const flags = global
    ? `${surroundHex(global.flags_a_raw)} / ${surroundHex(global.flags_b_raw)}`
    : 'waiting for readback';
  return `<section class="surround-card">
    <div class="surround-card-hd"><div><h3>Global monitor</h3>
      <p class="surround-meta">category 0x1b · ${surroundEscape(flags)}</p></div>
      <span class="surround-state">${global ? surroundEscape(format) : 'WAITING'}</span></div>
    <div class="surround-global-body">
      <div class="surround-global-overview">
        <label class="surround-format-picker"><span>Format</span>
          <select data-surround-format aria-label="Surround format" title="${surroundEscape(formatWrite.note || 'Only 2.0 and 2.1 are enabled for normal writes')}"${formatWrite.enabled ? '' : ' disabled'}>${formatOptions}</select>
          <small>${formatWrite.enabled ? '2.0 / 2.1 writable' : 'read-only'}</small></label>
        ${surroundSpeakerOverview(data)}
      </div>
      <div class="surround-global-rail">
        <section class="surround-global-controlbox">
          <div class="surround-global-knob-row">
            ${surroundRangeInput('delay_ms', 'Global delay', global?.global_delay_ms,
              delayRange, 'ms', writable, Number(write.delay_step_ms) || 0.1)}
            ${surroundRangeInput('level_db', 'Global level', global?.level_db,
              levelRange, 'dB', writable, Number(write.level_step_db) || 0.1)}
          </div>
          <label class="surround-monitor-select"><span class="surround-monitor-label">EQ position</span>
            <select data-surround-eq-position aria-label="Surround EQ position"
              title="${surroundEscape(eqPositionWrite.note || 'EQ PRE/POST write status unavailable')}"
              ${eqPositionWritable ? '' : ' disabled'}>${eqPositionOptions}</select>
            <span class="surround-readonly">${eqPositionWritable
              ? (eqPositionWrite.experimental ? 'experimental writable' : 'writable')
              : 'read-only'}</span></label>
          <div class="surround-global-bass"><span>Bass management <i>${global?.bass_mgmt_on ? 'ON' : 'OFF'}</i></span>
            <button class="btn surround-bass-open" type="button" data-surround-bass-open aria-haspopup="dialog" aria-expanded="${surroundBassWindowIsOpen() ? 'true' : 'false'}">OPEN</button></div>
        </section>
      </div>
    </div>
    <p class="surround-note">${surroundEscape(write.note ||
      'Only the verified global delay and level path can be written.')}</p>
  </section>`;
}

function surroundSpeakerHeadControl(field, label, speaker, headWrite) {
  const control = headWrite?.controls?.[field] || {};
  const range = Array.isArray(control.range) && control.range.length === 2
    ? control.range.map(Number) : [0, 1];
  const min = Number.isFinite(range[0]) ? range[0] : 0;
  const max = Number.isFinite(range[1]) ? range[1] : 1;
  const step = Number.isFinite(Number(control.step)) ? Number(control.step) : 0.1;
  const head = speaker?.head || {};
  const value = Number(head[field]);
  const current = Number.isFinite(value) ? value : min;
  const writable = headWrite?.enabled === true
    && Array.isArray(headWrite.fields) && headWrite.fields.includes(field)
    && speaker?.head_readback === true;
  const digits = Number.isInteger(Number(control.digits))
    ? Number(control.digits) : 1;
  const unit = control.unit ? ` ${surroundEscape(control.unit)}` : '';
  const display = Number.isFinite(value)
    ? `${surroundNumber(value, digits)}${unit}` : 'waiting';
  const status = writable
    ? (headWrite?.experimental ? 'experimental writable' : 'writable')
    : (speaker?.head_readback ? 'read-only' : 'readback unavailable');
  const angle = surroundKnobAngle(current, min, max);
  const gesture = field === 'level_db' ? ' · double-click = 0.0 dB' : '';
  return `<div class="surround-monitor-knob${writable ? '' : ' surround-disabled'}">
    <span class="surround-monitor-label">${surroundEscape(label)}</span>
    <output class="mixer-readout surround-monitor-readout" data-surround-head-value="${surroundEscape(field)}">${display}</output>
    <div class="mixer-knob surround-monitor-dial" title="${surroundEscape(label)} · drag up/down for precision${gesture}">
      <i style="transform:translateX(-50%) rotate(${angle}deg)"></i>
      <input type="range" data-surround-speaker-head-input
        data-surround-speaker-head-field="${surroundEscape(field)}"
        data-surround-speaker-head="${speaker?.index ?? 0}" min="${min}" max="${max}"
        step="${step}" value="${current}"
        data-precision-drag-pixels="${field === 'level_db' ? 760 : 1000}"${writable ? '' : ' disabled'} aria-label="${surroundEscape(label)}">
    </div>
    <span class="surround-readonly">${status}${writable ? ' · drag ↑↓ · wheel' : ''}</span>
  </div>`;
}

function surroundSpeakerPhaseControl(speaker, headWrite) {
  const head = speaker?.head || {};
  const available = speaker?.head_readback === true
    && typeof head.phase_invert === 'boolean';
  const writable = available && headWrite?.enabled === true
    && Array.isArray(headWrite.fields)
    && headWrite.fields.includes('phase_invert');
  const state = available ? (head.phase_invert ? 'ON' : 'OFF') : 'readback unavailable';
  return `<div class="surround-monitor-toggle${writable ? '' : ' surround-disabled'}">
    <span class="surround-monitor-label">Phase invert</span>
    <button type="button" class="btn surround-speaker-toggle surround-phase-toggle${head.phase_invert ? ' on' : ''}"
      data-surround-speaker-head-toggle data-surround-speaker-head-boolean="true"
      data-surround-speaker-head-field="phase_invert"
      data-surround-speaker-head="${speaker?.index ?? 0}"
      aria-pressed="${head.phase_invert ? 'true' : 'false'}"${writable ? '' : ' disabled'}
      aria-label="Phase invert">${state === 'readback unavailable' ? 'Ø' : state}</button>
    <span class="surround-readonly">${writable
      ? (headWrite?.experimental ? 'experimental writable' : 'writable')
      : state + ' · read-only'}</span></div>`;
}

function surroundSpeakerBypassControl(speaker, bypassWrite) {
  const available = speaker?.bypass_readback === true
    && typeof speaker.bypass === 'boolean';
  const writable = available && bypassWrite?.enabled === true
    && Array.isArray(bypassWrite.fields) && bypassWrite.fields.includes('bypass');
  const on = available && speaker.bypass;
  const state = available ? (on ? 'ON' : 'OFF') : 'readback unavailable';
  return `<div class="surround-monitor-toggle${writable ? '' : ' surround-disabled'}">
    <span class="surround-monitor-label">Bypass processing</span>
    <button type="button" class="btn surround-speaker-toggle surround-bypass-toggle${on ? ' on' : ''}"
      data-surround-speaker-bypass data-surround-speaker="${speaker?.index ?? 0}"
      data-surround-speaker-field="bypass" aria-pressed="${on ? 'true' : 'false'}"${writable ? '' : ' disabled'}
      aria-label="Bypass ${surroundEscape(speaker?.label || 'speaker')} processing"
      title="Bypass all channel processing except level">${state}</button>
    <span class="surround-readonly">${writable
      ? (bypassWrite?.experimental ? 'experimental writable' : 'writable')
      : state + ' · read-only'}</span></div>`;
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

function surroundEqSafeQ(q) {
  const number = Number(q);
  return Number.isFinite(number) && number > 0 ? number : 0.71;
}

function surroundEqSigma(q) {
  return Math.max(0.04, Math.min(2.5, 0.75 / surroundEqSafeQ(q)));
}

function surroundEqBandType(index, mode) {
  const current = Number(mode);
  if (current === 2 || !Number.isFinite(current)) return 'bell';
  if (index === 0) return current === 4 ? 'hpf' : 'lshelving';
  if (index === 15) return current === 3 ? 'lpf' : 'hshelving';
  return 'bell';
}

function surroundEqShelfResponse(gain, frequency, cutoff, q, high) {
  const logFrequency = Math.log2(Math.max(1, Number(frequency)));
  const logCutoff = Math.log2(Math.max(1, Number(cutoff)));
  const transition = Math.max(0.08, Math.min(1, 0.35 / surroundEqSafeQ(q)));
  const distance = Math.max(-60, Math.min(60,
    (logFrequency - logCutoff) / transition));
  const amount = 1 / (1 + Math.exp((high ? -1 : 1) * distance));
  return Number(gain) * amount;
}

function surroundEqPassResponse(frequency, cutoff, q, high) {
  const ratio = Math.max(1e-6, Number(frequency) / Math.max(1, Number(cutoff)));
  const ratioSquared = ratio * ratio;
  const safeQ = Math.max(0.1, Math.min(18, surroundEqSafeQ(q)));
  const denominator = Math.sqrt((1 - ratioSquared) ** 2
    + ratioSquared / (safeQ * safeQ));
  const magnitude = high ? ratioSquared / denominator : 1 / denominator;
  return 20 * Math.log10(Math.max(1e-6, magnitude));
}

function surroundEqBandResponse(band, frequency) {
  const type = surroundEqBandType(band.index, band.mode);
  if (type === 'hpf') return surroundEqPassResponse(
    frequency, band.frequency, band.q, true);
  if (type === 'lpf') return surroundEqPassResponse(
    frequency, band.frequency, band.q, false);
  if (type === 'lshelving') return surroundEqShelfResponse(
    band.gain, frequency, band.frequency, band.q, false);
  if (type === 'hshelving') return surroundEqShelfResponse(
    band.gain, frequency, band.frequency, band.q, true);
  const logFrequency = Math.log2(frequency);
  const distance = (logFrequency - Math.log2(band.frequency))
    / surroundEqSigma(band.q);
  return band.gain * Math.exp(-0.5 * distance * distance);
}

function surroundEqResponseAt(bands, frequency) {
  return bands.reduce((total, band) => total + surroundEqBandResponse(band, frequency), 0);
}

function surroundEqCurvePoints(bands, minFrequency = 20,
                               maxFrequency = 20000, sampleCount = 256) {
  if (!bands.length) return [];
  const start = Number(minFrequency);
  const end = Number(maxFrequency);
  if (!(end > start)) {
    return [{frequency: start, gain: surroundEqResponseAt(bands, start)}];
  }
  return Array.from({length: sampleCount}, (_, index) => {
    const fraction = index / (sampleCount - 1);
    const frequency = start * Math.pow(end / start, fraction);
    return {frequency, gain: surroundEqResponseAt(bands, frequency)};
  });
}

function surroundEqGraph(speaker, writable = false) {
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
  const maxGain = 18;
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
    mode: Number(band.mode),
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
  const gainTicks = [-24, -12, 0, 12, 18];
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
  const curve = surroundEqCurvePoints(bands, minFreq, maxFreq).map(point => ({
    ...point, x: xFor(point.frequency), y: yFor(point.gain),
  }));
  const line = surroundGraphPath(curve);
  const area = line + ' L ' + curve[curve.length - 1].x + ' ' + (top + plotHeight)
    + ' L ' + curve[0].x + ' ' + (top + plotHeight) + ' Z';
  const markers = points.map(point => '<circle cx="' + point.x + '" cy="' + point.y + '" r="4"'
    + (writable ? ' data-surround-eq-point data-surround-eq-speaker="'
      + speaker.index + '" data-surround-eq-band="' + point.index + '"' : '') + '>'
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
    + '<span class="surround-eq-graph-note">' + (writable
      ? 'Drag a point for frequency + gain · wheel over a point adjusts Q · '
      : '') + 'Approximate EQ response from readback · filter shapes follow the selected mode · full 20 Hz–20 kHz display span</span>'
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
    + '<div class="surround-eq-number-row">'
    + '<input type="number" class="mixer-readout surround-eq-number"'
    + ' data-surround-eq-number data-surround-eq-field="'
    + surroundEscape(field) + '" data-surround-eq-speaker="' + speaker
    + '" data-surround-eq-band="' + band + '" min="' + min + '" max="'
    + max + '" step="' + step + '" value="' + surroundNumber(current, digits) + '"'
    + (writable ? '' : ' disabled') + ' aria-label="' + surroundEscape(inputLabel)
    + '">' + (unit ? '<span class="surround-eq-unit">' + surroundEscape(unit.trim()) + '</span>' : '')
    + '</div>'
    + '<div class="mixer-knob surround-knob" title="' + surroundEscape(inputLabel) + '">'
    + '<i style="transform:translateX(-50%) rotate(' + angle + 'deg)"></i>'
    + '<input type="range" data-surround-eq-input data-surround-eq-field="'
    + surroundEscape(field) + '" data-surround-eq-speaker="' + speaker
    + '" data-surround-eq-band="' + band + '" min="' + min + '" max="'
    + max + '" step="' + step + '" value="' + surroundEscape(current) + '"'
    + (logarithmic ? ' data-logarithmic="true"' : '')
    + (writable ? '' : ' disabled') + ' aria-label="' + surroundEscape(inputLabel)
    + '"></div>'
    + '</div>';
}

const SURROUND_EQ_ASSET_BASE = '/webui/assets/srrndeq-bttn-';
const SURROUND_EQ_STATE_LABELS = {
  belldown: 'Bell cut',
  bellup: 'Bell boost',
  flat: 'Flat',
  hpf: 'High-pass',
  lpf: 'Low-pass',
  hshelvingdown: 'High shelving cut',
  hshelvingup: 'High shelving boost',
  lshelvingdown: 'Low shelving cut',
  lshelvingup: 'Low shelving boost',
};

function surroundEqGainState(gain, prefix) {
  const value = Number(gain);
  if (value < 0) return prefix + 'down';
  if (value > 0) return prefix + 'up';
  return 'flat';
}

function surroundEqModeValues(mode, index) {
  const current = Number(mode);
  if (current === 2) return [2];
  const values = index === 0 ? [0, 4] : index === 15 ? [1, 3] : [2];
  if (Number.isFinite(current) && !values.includes(current)) values.unshift(current);
  return values;
}

function surroundEqStateName(gain, index, mode) {
  const type = surroundEqBandType(index, mode);
  if (type === 'hpf' || type === 'lpf') return type;
  return surroundEqGainState(gain, type);
}

function surroundEqStateLabel(state) {
  return SURROUND_EQ_STATE_LABELS[state] || 'Filter type';
}

function updateSurroundEqModeButton(button, mode = button?.dataset?.surroundEqModeValue) {
  if (!button) return;
  const band = Number(button.dataset.surroundEqBand);
  const gain = button.closest('.surround-band')?.querySelector(
    '[data-surround-eq-field="gain"]')?.value;
  const state = surroundEqStateName(gain, band, mode);
  const label = surroundEqStateLabel(state);
  const icon = button.querySelector('[data-surround-eq-state-icon]');
  if (icon) icon.src = SURROUND_EQ_ASSET_BASE + state + '.svg';
  button.dataset.surroundEqModeValue = String(mode);
  button.dataset.surroundEqState = state;
  button.value = String(mode);
  button.title = button.disabled ? label : label + ' · click to change';
  button.setAttribute('aria-label', label + ' for band ' + (band + 1));
}

function surroundEqModeButton(mode, index, speaker, writable, gain) {
  const number = Number(mode);
  const current = Number.isFinite(number) ? number
    : index === 0 ? 0 : index === 15 ? 1 : 2;
  const values = surroundEqModeValues(current, index);
  const state = surroundEqStateName(gain, index, current);
  const label = surroundEqStateLabel(state);
  const enabled = writable && values.length > 1;
  return '<div class="surround-eq-mode">'
    + '<button type="button" class="surround-eq-mode-button"'
    + ' data-surround-eq-mode data-surround-eq-mode-value="' + current
    + '" data-surround-eq-mode-values="' + values.join(',')
    + '" data-surround-eq-state="' + state + '"'
    + ' data-surround-eq-speaker="' + speaker + '" data-surround-eq-band="'
    + index + '"' + (enabled ? '' : ' disabled') + ' aria-label="'
    + surroundEscape(label + ' for band ' + (index + 1)) + '" title="'
    + surroundEscape(enabled ? label + ' · click to change' : label) + '">'
    + '<img class="surround-eq-mode-bg" src="' + SURROUND_EQ_ASSET_BASE
    + 'bg.svg" alt="" aria-hidden="true">'
    + '<img class="surround-eq-mode-icon" data-surround-eq-state-icon src="'
    + SURROUND_EQ_ASSET_BASE + state + '.svg" alt="" aria-hidden="true">'
    + '</button></div>';
}

function surroundEqBand(band, index, speaker, writable) {
  return '<article class="surround-band" data-surround-eq-band="' + index + '">'
    + '<strong>' + (index + 1) + '</strong>'
    + surroundEqKnob('frequency', band.freq_hz, 20, 20000, 1, ' Hz', 0,
      speaker, index, writable, true)
    + surroundEqKnob('gain', band.gain_db, -24, 12, 0.01, ' dB', 2,
      speaker, index, writable)
    + surroundEqKnob('q', band.q, 0.1, 18, 0.01, '', 2,
      speaker, index, writable)
    + surroundEqModeButton(band.mode, index, speaker, writable, band.gain_db)
    + '</article>';
}

function surroundEqGrid(speaker, writable = false) {
  const bands = speaker?.bands || [];
  if (!bands.length) return '<p class="surround-empty">Waiting for the speaker EQ readback.</p>';
  return '<div class="surround-eq-layout">'
    + '<div class="surround-eq-legend" aria-hidden="true">'
    + '<strong></strong><span>F</span><span>G</span><span>Q</span><span></span>'
    + '</div><div class="surround-eq-grid">'
    + bands.map((band, index) => surroundEqBand(
      band, index, speaker.index, writable)).join('') + '</div></div>';
}

function surroundSpeakerHTML(data) {
  const speaker = surroundSpeaker(SURROUND_SPEAKER, data);
  const headWrite = data.write?.speaker_head || {};
  const bypassWrite = data.write?.speaker_bypass || {};
  const headWritable = headWrite.enabled === true && speaker.head_readback === true;
  const bypassWritable = bypassWrite.enabled === true
    && speaker.bypass_readback === true;
  const eqWritable = data.write?.eq?.enabled === true && speaker.readback === true;
  const resetPreset = data.write?.eq?.reset;
  const eqResettable = eqWritable
    && Array.isArray(resetPreset?.frequency_hz)
    && resetPreset.frequency_hz.length === speaker.bands.length;
  const status = speaker.readback ? (speaker.active ? 'ACTIVE' : 'inactive') : 'WAITING';
  return `<section class="surround-card">
    <div class="surround-card-hd"><div><h3>Speaker monitor</h3>
      <p class="surround-meta">category 0x1a · one readback per speaker</p></div>
      <span class="surround-state">${surroundEscape(status)}</span></div>
    <div class="surround-speakerbar">
      <span class="surround-speaker-name">${surroundEscape(speaker.label)}</span>
      <span class="surround-meta">${speaker.readback ? `${speaker.bands.length} EQ bands` : 'waiting for readback'}</span>
    </div>
    <div class="surround-controls surround-speaker-controls">
      ${surroundSpeakerHeadControl('delay_ms', 'Speaker delay', speaker, headWrite)}
      ${surroundSpeakerHeadControl('level_db', 'Speaker level', speaker, headWrite)}
      <div class="surround-speaker-button-group">
        ${surroundSpeakerPhaseControl(speaker, headWrite)}
        ${surroundSpeakerBypassControl(speaker, bypassWrite)}
      </div>
    </div>
    <div class="surround-eq"><div class="surround-subhd"><h4>16-band EQ · single view</h4>
      <div class="surround-eq-actions"><span class="surround-readonly">${eqWritable
        ? (data.write?.eq?.experimental
          ? 'experimental write · drag writes frequency + gain'
          : 'writable · drag writes frequency + gain')
        : 'read-only · filter buttons disabled'}</span>
        <button class="btn surround-eq-reset" type="button" data-surround-eq-reset
          data-surround-eq-speaker="${speaker.index}"${eqResettable ? '' : ' disabled'}
          title="Reset this speaker's EQ to the profile preset">RESET</button></div></div>
      ${surroundEqGraph(speaker, eqWritable)}
      ${surroundEqGrid(speaker, eqWritable)}</div>
    <p class="surround-note">${eqWritable || headWritable || bypassWritable
      ? 'EQ knobs write one field at a time; graph drags write frequency and gain together after a fresh readback. Speaker delay, level, phase invert, and bypass use complete-state read-modify-write paths with an immediate readback comparison when possible.'
      : 'The per-speaker 0x87 frame and global bypass mask are decoded for readback. Speaker delay, level, phase, and bypass writes are available only after their supported 2.0/2.1 contracts and fresh readbacks.'}</p>
  </section>`;
}

function surroundEqDisplay(field, value) {
  if (field === 'frequency') return surroundNumber(value, 0);
  if (field === 'gain') return surroundNumber(value, 2);
  if (field === 'q') return surroundNumber(value, 2);
  if (field === 'mode') return surroundHex(value);
  return surroundNumber(value);
}

function surroundEqPaint(input) {
  if (!input) return;
  const field = input.dataset.surroundEqField;
  const value = Number(input.value);
  const output = input.closest('.surround-eq-knob')?.querySelector(
    '[data-surround-eq-number]');
  if (output) output.value = surroundEqDisplay(field, value);
  const pointer = input.closest('.mixer-knob')?.querySelector('i');
  if (pointer) pointer.style.transform = 'translateX(-50%) rotate('
    + surroundKnobAngle(value, +input.min, +input.max, field === 'frequency') + 'deg)';
  if (field === 'gain') {
    updateSurroundEqModeButton(input.closest('.surround-band')?.querySelector(
      '[data-surround-eq-mode]'));
  }
}

function surroundSpeakerHeadPaint(input) {
  if (!input) return;
  const field = input.dataset.surroundSpeakerHeadField;
  const value = Number(input.value);
  const output = input.closest('.surround-monitor-knob')?.querySelector(
    `[data-surround-head-value="${field}"]`);
  if (output) output.textContent = `${surroundNumber(value, field === 'level_db' ? 1 : 1)} ${field === 'level_db' ? 'dB' : 'ms'}`;
  const pointer = input.closest('.surround-monitor-dial')?.querySelector('i');
  if (pointer) pointer.style.transform = 'translateX(-50%) rotate('
    + surroundKnobAngle(value, +input.min, +input.max) + 'deg)';
}

function surroundGlobalPaint(input) {
  if (!input) return;
  const field = input.dataset.surroundGlobal;
  const value = Number(input.value);
  const unit = field === 'delay_ms' ? 'ms' : 'dB';
  const output = input.closest('.surround-monitor-knob')?.querySelector(
    `[data-surround-value="${field}"]`);
  if (output) output.textContent = `${surroundNumber(value)} ${unit}`;
  const pointer = input.closest('.surround-monitor-dial')?.querySelector('i');
  if (pointer) pointer.style.transform = 'translateX(-50%) rotate('
    + surroundKnobAngle(value, +input.min, +input.max) + 'deg)';
}

function initSurroundSpeakerHeadControls(host) {
  host.querySelectorAll('[data-surround-speaker-head-input]').forEach(input => {
    // Relative vertical dragging avoids the native slider's 1:1 pointer jump,
    // while leaving keyboard changes and the range limits intact.
    if (!input.disabled && typeof wirePrecisionRange === 'function') {
      wirePrecisionRange(input);
    }
    surroundSpeakerHeadPaint(input);
    if (input.disabled || input.dataset.surroundSpeakerHeadField !== 'level_db') return;
    input.addEventListener('dblclick', event => {
      const minimum = Number(input.min);
      const maximum = Number(input.max);
      if (!Number.isFinite(minimum) || !Number.isFinite(maximum)
          || minimum > 0 || maximum < 0) return;
      event.preventDefault();
      input.value = '0';
      surroundSpeakerHeadPaint(input);
      input.dispatchEvent(new Event('change', {bubbles: true}));
    });
  });
}

function initSurroundGlobalControls(host) {
  host.querySelectorAll('[data-surround-global]').forEach(input => {
    if (!input.disabled && typeof wirePrecisionRange === 'function') {
      wirePrecisionRange(input);
    }
    surroundGlobalPaint(input);
  });
}

function postSurroundSpeakerHeadInput(input) {
  if (!input || input.disabled) return;
  const value = input.dataset.surroundSpeakerHeadBoolean === 'true'
    ? input.classList.contains('on') : Number(input.value);
  if (typeof value !== 'boolean' && !Number.isFinite(value)) return;
  post('/api/surround/speaker', {
    speaker: Number(input.dataset.surroundSpeakerHead),
    field: input.dataset.surroundSpeakerHeadField,
    value,
  });
}

function postSurroundSpeakerBypass(input) {
  if (!input || input.disabled) return;
  post('/api/surround/speaker', {
    speaker: Number(input.dataset.surroundSpeaker),
    field: input.dataset.surroundSpeakerField || 'bypass',
    value: input.classList.contains('on'),
  });
}

function surroundEqSnap(value, min, max, step) {
  const number = Number(value);
  const lo = Number(min), hi = Number(max), increment = Number(step);
  if (![number, lo, hi, increment].every(Number.isFinite)
      || increment <= 0 || hi < lo) return null;
  const snapped = lo + Math.round((number - lo) / increment) * increment;
  return Math.max(lo, Math.min(hi, snapped));
}

function postSurroundEqInput(input) {
  if (!input || input.disabled) return;
  surroundEqPaint(input);
  post('/api/surround/eq', {
    speaker: Number(input.dataset.surroundEqSpeaker),
    band: Number(input.dataset.surroundEqBand),
    parameter: input.dataset.surroundEqField,
    value: Number(input.value),
  });
}

function postSurroundEqPoint(speaker, band, frequency, gain) {
  if (!Number.isInteger(speaker) || !Number.isInteger(band)
      || !Number.isFinite(frequency) || !Number.isFinite(gain)) return;
  const localBand = SURROUND?.speakers?.[speaker]?.bands?.[band];
  if (localBand) {
    localBand.freq_hz = frequency;
    localBand.gain_db = gain;
  }
  post('/api/surround/eq/point', {speaker, band, frequency, gain});
}

function surroundEqPointTitle(band, frequency, gain, q) {
  return 'Band ' + (band + 1) + ': ' + surroundNumber(frequency, 0)
    + ' Hz, ' + surroundNumber(gain, 2) + ' dB, Q ' + surroundNumber(q, 2);
}

function surroundEqGraphPaint(svg, host, speaker) {
  const left = 42, top = 14, plotWidth = 906, plotHeight = 204;
  const bands = [...svg.querySelectorAll('[data-surround-eq-point]')].map(point => {
    const band = Number(point.dataset.surroundEqBand);
    const field = name => host.querySelector('[data-surround-eq-input]'
      + '[data-surround-eq-speaker="' + speaker + '"]'
      + '[data-surround-eq-band="' + band + '"]'
      + '[data-surround-eq-field="' + name + '"]');
    const frequency = Number(field('frequency')?.value);
    const gain = Number(field('gain')?.value);
    const q = Number(field('q')?.value);
    const mode = Number(SURROUND?.speakers?.[speaker]?.bands?.[band]?.mode);
    return {index: band, frequency, gain, q, mode};
  }).filter(item => [item.frequency, item.gain, item.q].every(Number.isFinite));
  if (!bands.length) return;
  const curve = surroundEqCurvePoints(bands).map(item => ({
    ...item,
    x: left + Math.log10(item.frequency / 20) / 3 * plotWidth,
    y: top + (18 - Math.max(-24, Math.min(18, item.gain))) / 42 * plotHeight,
  }));
  const line = surroundGraphPath(curve);
  const area = line + ' L ' + curve[curve.length - 1].x + ' ' + (top + plotHeight)
    + ' L ' + curve[0].x + ' ' + (top + plotHeight) + ' Z';
  svg.querySelector('.surround-eq-line')?.setAttribute('d', line);
  svg.querySelector('.surround-eq-area')?.setAttribute('d', area);
}

function initSurroundEqGraphControls(host) {
  host.querySelectorAll('[data-surround-eq-point]').forEach(point => {
    const speaker = Number(point.dataset.surroundEqSpeaker);
    const band = Number(point.dataset.surroundEqBand);
    const selector = field => '[data-surround-eq-input][data-surround-eq-speaker="'
      + speaker + '"][data-surround-eq-band="' + band
      + '"][data-surround-eq-field="' + field + '"]';
    const input = field => host.querySelector(selector(field));
    const frequencyInput = input('frequency');
    const gainInput = input('gain');
    const qInput = input('q');
    const svg = point.ownerSVGElement;
    if (!frequencyInput || !gainInput || !qInput || !svg) return;
    let dragging = false, moved = false, pointerId = null;
    let wheelRemainder = 0, wheelCommitTimer = null;
    let startX = 0, startY = 0, startFrequency = 0, startGain = 0;
    const left = 42, top = 14, plotWidth = 906, plotHeight = 204;
    const graphX = event => {
      const bounds = svg.getBoundingClientRect();
      return (event.clientX - bounds.left) * 960 / Math.max(1, bounds.width);
    };
    const graphY = event => {
      const bounds = svg.getBoundingClientRect();
      return (event.clientY - bounds.top) * 250 / Math.max(1, bounds.height);
    };
    const updateTitle = () => {
      const title = point.querySelector('title');
      const text = surroundEqPointTitle(band, +frequencyInput.value,
        +gainInput.value, +qInput.value);
      if (title) title.textContent = text;
      point.setAttribute('aria-valuetext', text);
    };
    const update = event => {
      // Damp pointer movement to make dense EQ work practical with a mouse.
      const x = Math.max(left, Math.min(left + plotWidth,
        startX + (graphX(event) - startX) / 2.5));
      const y = Math.max(top, Math.min(top + plotHeight,
        startY + (graphY(event) - startY) / 2.5));
      const frequency = surroundEqSnap(20 * Math.pow(1000, (x - left) / plotWidth),
        frequencyInput.min, frequencyInput.max, frequencyInput.step);
      const gain = surroundEqSnap(18 - (y - top) * 42 / plotHeight,
        gainInput.min, gainInput.max, gainInput.step);
      if (frequency == null || gain == null) return;
      frequencyInput.value = String(frequency);
      gainInput.value = String(gain);
      surroundEqPaint(frequencyInput);
      surroundEqPaint(gainInput);
      point.setAttribute('cx', String(left + Math.log10(frequency / 20)
        / 3 * plotWidth));
      point.setAttribute('cy', String(top + (18 - gain) / 42 * plotHeight));
      updateTitle();
      surroundEqGraphPaint(svg, host, speaker);
      moved = moved || frequency !== startFrequency || gain !== startGain;
    };
    const finish = commit => {
      if (!dragging) return;
      const didMove = moved;
      dragging = false;
      point.classList.remove('dragging');
      if (pointerId != null) {
        try { if (point.hasPointerCapture?.(pointerId)) point.releasePointerCapture(pointerId); } catch (_) {}
        pointerId = null;
      }
      if (commit && didMove) postSurroundEqPoint(speaker, band,
        +frequencyInput.value, +gainInput.value);
    };
    point.addEventListener('pointerdown', event => {
      event.preventDefault();
      dragging = true; moved = false; pointerId = event.pointerId;
      startX = graphX(event); startY = graphY(event);
      startFrequency = +frequencyInput.value; startGain = +gainInput.value;
      point.classList.add('dragging');
      point.setPointerCapture(pointerId);
    });
    point.addEventListener('pointermove', event => { if (dragging) update(event); });
    point.addEventListener('pointerup', () => finish(true));
    point.addEventListener('pointercancel', () => finish(false));
    point.addEventListener('lostpointercapture', () => finish(false));
    point.addEventListener('wheel', event => {
      // Wheel is captured only by a graph point; page scrolling stays normal elsewhere.
      event.preventDefault();
      event.stopPropagation();
      // Trackpads emit many tiny pixel deltas while a wheel commonly emits a
      // single large one. Accumulate the former, but cap every event to one
      // Q tick so both controls feel deliberate rather than jumpy.
      const multiplier = event.deltaMode === 1 ? 16
        : event.deltaMode === 2 ? 180 : 1;
      const delta = Number(event.deltaY) * multiplier;
      if (!Number.isFinite(delta) || delta === 0) return;
      if (wheelRemainder && Math.sign(delta) !== Math.sign(wheelRemainder)) {
        wheelRemainder = 0;
      }
      wheelRemainder += delta;
      if (Math.abs(wheelRemainder) < 12) return;
      const direction = Math.sign(wheelRemainder);
      wheelRemainder = 0;
      const value = surroundEqSnap(+qInput.value - direction
        * Number(qInput.step || 0.01), qInput.min, qInput.max, qInput.step);
      if (value == null || value === +qInput.value) return;
      qInput.value = String(value);
      surroundEqPaint(qInput);
      const localBand = SURROUND?.speakers?.[speaker]?.bands?.[band];
      if (localBand) localBand.q = value;
      updateTitle();
      surroundEqGraphPaint(svg, host, speaker);
      if (wheelCommitTimer != null) clearTimeout(wheelCommitTimer);
      wheelCommitTimer = setTimeout(() => {
        wheelCommitTimer = null;
        postSurroundEqInput(qInput);
      }, 140);
    }, {passive: false});
    updateTitle();
  });
}

function postSurroundEqMode(button) {
  if (!button || button.disabled) return;
  const values = String(button.dataset.surroundEqModeValues || '').split(',')
    .map(Number).filter(Number.isFinite);
  if (values.length < 2) return;
  const current = Number(button.dataset.surroundEqModeValue);
  const index = values.indexOf(current);
  const next = values[(index < 0 ? 0 : index + 1) % values.length];
  updateSurroundEqModeButton(button, next);
  const speaker = Number(button.dataset.surroundEqSpeaker);
  const band = Number(button.dataset.surroundEqBand);
  if (SURROUND?.speakers?.[speaker]?.bands?.[band]) {
    SURROUND.speakers[speaker].bands[band].mode = next;
  }
  post('/api/surround/eq', {
    speaker, band, parameter: 'mode', value: next,
  });
}

function surroundEqDefaultValue(input, resetPreset = SURROUND?.write?.eq?.reset) {
  const band = Number(input?.dataset?.surroundEqBand);
  if (!resetPreset || !Number.isInteger(band) || band < 0) return null;
  if (input.dataset.surroundEqField === 'frequency') {
    const value = resetPreset.frequency_hz?.[band];
    return Number.isFinite(Number(value)) ? Number(value) : null;
  }
  if (input.dataset.surroundEqField === 'q') {
    return Number.isFinite(Number(resetPreset.q)) ? Number(resetPreset.q) : null;
  }
  if (input.dataset.surroundEqField === 'gain') {
    return Number.isFinite(Number(resetPreset.gain_db))
      ? Number(resetPreset.gain_db) : null;
  }
  return null;
}

function initSurroundEqControls(host) {
  host.querySelectorAll('[data-surround-eq-input]').forEach(input => {
    if (!input.disabled && input.type === 'range'
        && typeof wirePrecisionRange === 'function') wirePrecisionRange(input);
    surroundEqPaint(input);
    if (input.disabled || input.type !== 'range') return;
    input.addEventListener('dblclick', event => {
      const value = surroundEqDefaultValue(input);
      if (value == null) return;
      event.preventDefault();
      input.value = String(value);
      surroundEqPaint(input);
      input.dispatchEvent(new Event('change', {bubbles: true}));
    });
  });
}

function requestSurroundEqReset(button) {
  if (!button || button.disabled) return;
  const speaker = Number(button.dataset.surroundEqSpeaker);
  const name = button.closest('.surround-card')?.querySelector(
    '.surround-speaker-name')?.textContent || `Speaker ${speaker + 1}`;
  if (typeof window !== 'undefined' && typeof window.confirm === 'function'
      && !window.confirm(`Reset the EQ for ${name}?`)) return;
  button.disabled = true;
  post('/api/surround/eq/reset', {speaker}).finally(() => {
    if (button.isConnected) button.disabled = false;
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
  initSurroundGlobalControls(host);
  initSurroundSpeakerHeadControls(host);
  initSurroundEqControls(host);
  initSurroundEqGraphControls(host);
  initSurroundBassControls(host);
}

async function reloadSurround() {
  const previousFormat = SURROUND?.global?.format;
  SURROUND = await getJSON('/api/surround');
  const count = SURROUND.speaker_count || SURROUND.speakers?.length || 0;
  if (count && SURROUND_SPEAKER >= count) SURROUND_SPEAKER = 0;
  renderSurround();
  if (previousFormat !== SURROUND?.global?.format) refreshSurroundBassWindow();
}

function buildSurround() {
  const host = $('#surround');
  if (!host) return;
  if (!SURROUND_BUILT) {
    host.addEventListener('input', event => {
      const head = event.target.closest?.('[data-surround-speaker-head-input]');
      if (head) {
        surroundSpeakerHeadPaint(head);
        return;
      }
      const eq = event.target.closest?.('[data-surround-eq-input]');
      if (eq) {
        surroundEqPaint(eq);
        return;
      }
      const bass = event.target.closest?.('[data-bass-input]');
      if (bass) {
        surroundBassPaint(bass);
        return;
      }
      const input = event.target.closest('[data-surround-global]');
      if (!input) return;
      surroundGlobalPaint(input);
    });
    host.addEventListener('click', event => {
      const speakerSelect = event.target.closest?.('[data-surround-speaker-select]');
      if (speakerSelect) {
        if (speakerSelect.disabled) return;
        SURROUND_SPEAKER = Number(speakerSelect.dataset.surroundSpeakerSelect) || 0;
        renderSurround();
        return;
      }
      const headToggle = event.target.closest?.(
        '[data-surround-speaker-head-toggle]');
      if (headToggle) {
        if (headToggle.disabled) return;
        const on = !headToggle.classList.contains('on');
        headToggle.classList.toggle('on', on);
        headToggle.textContent = on ? 'ON' : 'OFF';
        headToggle.setAttribute('aria-pressed', String(on));
        postSurroundSpeakerHeadInput(headToggle);
        return;
      }
      const speakerBypass = event.target.closest?.(
        '[data-surround-speaker-bypass]');
      if (speakerBypass) {
        if (speakerBypass.disabled) return;
        const on = !speakerBypass.classList.contains('on');
        speakerBypass.classList.toggle('on', on);
        speakerBypass.textContent = on ? 'ON' : 'OFF';
        speakerBypass.setAttribute('aria-pressed', String(on));
        postSurroundSpeakerBypass(speakerBypass);
        return;
      }
      const reset = event.target.closest?.('[data-surround-eq-reset]');
      if (reset) {
        requestSurroundEqReset(reset);
        return;
      }
      const mode = event.target.closest?.('[data-surround-eq-mode]');
      if (mode) {
        postSurroundEqMode(mode);
        return;
      }
      const bassBoolean = event.target.closest?.(
        '[data-bass-input][data-bass-boolean]');
      if (bassBoolean) {
        if (bassBoolean.disabled) return;
        const on = !bassBoolean.classList.contains('on');
        bassBoolean.classList.toggle('on', on);
        bassBoolean.setAttribute('aria-pressed', String(on));
        postSurroundBassInput(bassBoolean);
        return;
      }
      const open = event.target.closest?.('[data-surround-bass-open]');
      if (open) {
        openSurroundBassWindow();
        return;
      }
    });
    host.addEventListener('change', event => {
      const number = event.target.closest?.('[data-surround-eq-number]');
      if (number && !number.disabled) {
        const range = number.closest('.surround-eq-knob')?.querySelector(
          '[data-surround-eq-input]');
        if (!range || range.disabled) return;
        const value = surroundEqSnap(number.value, range.min, range.max, range.step);
        if (value == null) {
          surroundEqPaint(range);
          return;
        }
        range.value = String(value);
        postSurroundEqInput(range);
        return;
      }
      const eq = event.target.closest?.('[data-surround-eq-input]');
      if (eq && !eq.disabled) {
        postSurroundEqInput(eq);
        return;
      }
      const head = event.target.closest?.('[data-surround-speaker-head-input]');
      if (head && !head.disabled) {
        postSurroundSpeakerHeadInput(head);
        return;
      }
      const bass = event.target.closest?.('[data-bass-input]');
      if (bass && !bass.disabled) {
        postSurroundBassInput(bass);
        return;
      }
      const format = event.target.closest?.('[data-surround-format]');
      if (format && !format.disabled) {
        post('/api/surround/global', {format: format.value});
        return;
      }
      const eqPosition = event.target.closest?.('[data-surround-eq-position]');
      if (eqPosition && !eqPosition.disabled) {
        post('/api/surround/global', {eq_position: eqPosition.value});
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

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    if (SURROUND_BASS_WINDOW && !SURROUND_BASS_WINDOW.closed) {
      SURROUND_BASS_WINDOW.close();
    }
    SURROUND_BASS_WINDOW = null;
  });
}
