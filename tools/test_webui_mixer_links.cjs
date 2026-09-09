// Offline linked-mixer interaction checks: node tools/test_webui_mixer_links.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'webui/static/index.html'), 'utf8');
const source = html.slice(
  html.indexOf('const mixerPendingKey'),
  html.indexOf('function selectMixer'));

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
  MIX_LINKS: {0: true},
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
console.log('WebUI linked mixer checks passed (live fader/Send mirror and paired posts).');
