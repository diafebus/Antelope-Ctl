// Offline linked-mixer interaction checks: node tools/test_webui_mixer_links.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'webui/static/index.html'), 'utf8');
const source = html.slice(
  html.indexOf('const mixerPendingKey'),
  html.indexOf('function mixerSoloSnapshot'));

const makeInput = value => {
  let current = String(value);
  return {
    get value() { return current; },
    set value(next) { current = String(next); },
  };
};
const makeStrip = () => {
  const controls = {
    '[data-fader]': makeInput(-10),
    '[data-send]': makeInput(-20),
    '[data-fval]': {textContent: ''},
    '[data-sval]': {textContent: ''},
  };
  return {querySelector: selector => controls[selector] || null, controls};
};
const strips = {1: makeStrip(), 2: makeStrip()};
const posted = [];
const context = vm.createContext({
  MIXER: {ranges: {send: [0, 96]}, current: {}},
  MIXER_METERS: null,
  MIX_PENDING: {},
  MIX_PENDING_TTL: 5000,
  MIX_LINKS: {'0:0': true},
  PROFILE: {
    mixer: {
      link_readback: {
        status: 'capture-confirmed', category: 0x0b, index: 3,
        record_count: 24, selector_ranges: {'0': [0, 7], '1': [16, 23]},
      },
    },
  },
  document: {
    querySelector: selector => {
      const match = selector.match(/data-ch="(\d+)"/);
      return match ? strips[match[1]] || null : null;
    },
    querySelectorAll: () => [],
  },
  post: (path, body) => posted.push({path, body}),
  mixerFaderLabel: value => value ? `−${value} dB` : '0 dB',
  mixerSendLabel: (value, max) => value >= max ? '−∞' : `−${value} dB`,
  mixerPanLabel: value => value === 0 ? 'C' : value < 0 ? `L${-value}` : `R${value}`,
  paintMixerFader: () => {},
  paintMixerKnob: () => {},
});
vm.runInContext(source, context);

context.mirrorLinkedMixField(0, 1, 'fader', 37);
assert.equal(strips[2].controls['[data-fader]'].value, '-37');
assert.equal(strips[2].controls['[data-fval]'].textContent, '−37 dB');
assert.equal(context.MIX_PENDING['0:2:fader'].value, 37);

context.mirrorLinkedMixField(0, 1, 'send', 96);
assert.equal(strips[2].controls['[data-send]'].value, '-96');
assert.equal(strips[2].controls['[data-sval]'].textContent, '−∞');
assert.equal(context.MIX_PENDING['0:2:send'].value, 96);

context.postLinkedMix(0, 1, {send: 44});
assert.equal(JSON.stringify(posted.map(x => x.body)), JSON.stringify([
  {mix: 0, channel: 1, send: 44},
  {mix: 0, channel: 2, send: 44},
]));

// A link in Mix 1 must not make the same pair linked in another mix.
const beforeOtherMix = posted.length;
context.mirrorLinkedMixField(1, 1, 'fader', 55);
assert.equal(posted.length, beforeOtherMix);
context.postLinkedMix(1, 1, {send: 44});
context.postLinkedMix(1, 1, {mute: true});
context.postLinkedSolo(1, 1, true);
assert.equal(JSON.stringify(posted.slice(beforeOtherMix).map(x => x.body)), JSON.stringify([
  {mix: 1, channel: 1, send: 44},
  {mix: 1, channel: 1, mute: true},
  {mix: 1, channel: 1, on: true},
]));

// Pan commits share the same mix/channel scope and can be centered directly.
assert.match(html, /pan\.addEventListener\('dblclick', e => \{\s*e\.preventDefault\(\);\s*commitMixerPan\(m, ch, pan, pval, 0\);\s*\}\);/s);
const pan = {value: -17};
const panReadout = {textContent: ''};
context.commitMixerPan(1, 3, pan, panReadout, 0);
assert.equal(pan.value, 0);
assert.equal(panReadout.textContent, 'C');
assert.equal(context.MIX_PENDING['1:3:pan'].value, 0);
assert.equal(JSON.stringify(posted.at(-1).body), JSON.stringify({mix: 1, channel: 3, pan: 0}));

// The API request also carries the mix so the backend can address the
// corresponding hardware link domain.
context.setMixLink(1, 0, true);
assert.equal(JSON.stringify(posted.at(-1).body), JSON.stringify({mix: 1, pair: 0, enabled: true}));
assert.equal(context.MIX_LINKS['0:0'], true);
assert.equal(context.MIX_LINKS['1:0'], true);

// A complete Zen Go q0b/03 response seeds only the visible pair ranges;
// reserved selectors are still required for completeness but do not create
// UI pairs.
const linkedRecords = Array.from({length: 24}, (_, record_index) => ({
  record_index, linked: record_index === 1 || record_index === 17,
}));
assert.equal(context.syncMixerLinksFromReadback({layouts: [{
  category: 0x0b, index: 3, safe: true, current: {'3': linkedRecords},
}]}), true);
assert.equal(context.MIX_LINKS['0:0'], undefined);
assert.equal(context.MIX_LINKS['1:0'], undefined);
assert.equal(context.MIX_LINKS['0:1'], true);
assert.equal(context.MIX_LINKS['1:1'], true);

// Partial responses must leave the cached state untouched.
const partial = linkedRecords.slice(0, 23);
partial[0] = {record_index: 0, linked: false};
assert.equal(context.syncMixerLinksFromReadback({layouts: [{
  category: 0x0b, index: 3, safe: true, current: {'3': partial},
}]}), false);
assert.equal(context.MIX_LINKS['0:0'], undefined);
console.log('WebUI linked mixer checks passed (live fader/Send mirror and paired posts).');
