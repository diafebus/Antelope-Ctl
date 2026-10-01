// Hardware-free AFX popup lifecycle checks: node tools/test_webui_afx.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {ROOT} = require('./webui_sources.cjs');

const html = fs.readFileSync(path.join(ROOT, 'webui/static/index.html'), 'utf8');
assert.match(html, /data-rtab="matrix"[^]*?id="afxopen"[^]*?data-rtab="mix1"/);
// The routing tab delegate must not treat the popup button as a tab switch.
const launcherHTML = html.match(/<button[^>]*id="afxopen"[^>]*>/)[0];
assert.doesNotMatch(launcherHTML, /\btabbtn\b|data-rtab=/);

const button = {
  expanded: 'false', on: false,
  classList: {toggle(_name, on) { button.on = on; }},
  setAttribute(_name, value) { button.expanded = value; },
  addEventListener(_name, handler) { button.click = handler; },
};
const messages = new Map();
const parentEvents = {};
let openCount = 0, blocked = false, lastPopup;
const context = vm.createContext({
  PROFILE: JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/orion_studio_sc.json'), 'utf8')),
  document: {getElementById: () => button},
  window: {
    addEventListener(name, handler) { parentEvents[name] = handler; },
    open() {
      openCount++;
      if (blocked) return null;
      const events = {};
      const node = () => ({
        addEventListener(name, handler) { this[name] = handler; },
        focus() { this.focused = true; },
      });
      const nodes = Object.fromEntries(['afx-device', 'afx-channel', 'afx-channel-name',
        'afx-rack-title', 'afx-rack', 'afx-preview-status', 'afx-slot-list'].map(id => [id, node()]));
      const device = nodes['afx-device'], closeButton = node();
      const popup = {
        closed: false, focused: 0, events, device, closeButton, nodes,
        document: {
          body: {innerHTML: '', addEventListener() {}}, open() {}, write() {}, close() {},
          getElementById(id) { return nodes[id]; },
          querySelector() { return closeButton; },
        },
        addEventListener(name, handler) { events[name] = handler; },
        focus() { this.focused++; },
        close() { this.closed = true; events.pagehide?.(); },
      };
      lastPopup = popup;
      return popup;
    },
  },
  reportMessage: (key, title, body) => messages.set(key, {title, body}),
  clearMessage: key => messages.delete(key),
  fetch() { throw new Error('The capacity popup must not make device or account requests'); },
  post() { throw new Error('The capacity popup must not issue device writes'); },
});
// Capacity-only behavior must stay request-free when no device pilot is enabled.
context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = false;
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx-memorycat.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx-test.js'), 'utf8'), context);

// Orion dimensions come from its profile; slots are unknown, never fake empty.
button.click();
const first = lastPopup;
assert.equal((first.document.body.innerHTML.match(/<option /g) || []).length, 32);
assert.equal((first.document.body.innerHTML.match(/class="afx-channel"/g) || []).length, 1);
assert.equal((first.document.body.innerHTML.match(/class="afx-rack-unit"/g) || []).length, 8);
assert.match(first.document.body.innerHTML, /state unavailable/);
assert.equal(first.device.textContent, context.PROFILE.device.label || context.PROFILE.device.name);
assert.equal(button.expanded, 'true');
assert.equal(first.nodes['afx-channel'].focused, true);

// Channel selection repaints only that rack and is bounded by the profile.
first.nodes['afx-channel'].change({target: {value: '31'}});
assert.equal(first.nodes['afx-channel-name'].textContent, 'AFX 32');
assert.equal(first.nodes['afx-channel'].value, '31');
assert.match(first.nodes['afx-rack-title'].textContent, /AFX 32/);
assert.equal((first.nodes['afx-rack'].innerHTML.match(/class="afx-rack-unit"/g) || []).length, 8);
assert.match(first.nodes['afx-rack'].innerHTML, /AFX 32, slot 1: state unavailable/);
const lastRack = first.nodes['afx-rack'].innerHTML;
for (const value of ['32', '-1', '1.5', 'not-a-channel']) {
  first.nodes['afx-channel'].change({target: {value}});
  assert.equal(first.nodes['afx-rack'].innerHTML, lastRack);
}
button.click();
assert.equal(openCount, 1);
assert.equal(first.focused, 2);
first.events.keydown({key: 'Escape'});
assert.equal(first.closed, true);
assert.equal(button.expanded, 'false');

blocked = true;
button.click();
assert.equal(button.on, false);
assert.ok(messages.has('afx-popup'));
blocked = false;
button.click();
assert.equal(messages.has('afx-popup'), false);
lastPopup.closeButton.click();
assert.equal(button.expanded, 'false');
button.click();
assert.match(lastPopup.document.body.innerHTML, /<option value="31" selected>AFX 32<\/option>/);
lastPopup.close();

// Missing or invalid capacity does not inherit Orion's counts.
context.PROFILE = {};
const before = openCount;
button.click();
context.PROFILE = {afx: {channel_count: 32, slots_per_channel: 0}};
button.click();
assert.equal(openCount, before);

// Another declared capacity and an untrusted label remain presentation data.
context.PROFILE = {afx: {channel_count: 2, slots_per_channel: 3},
  device: {label: '<img src=x onerror=alert(1)>'}};
button.click();
assert.equal((lastPopup.document.body.innerHTML.match(/class="afx-rack-unit"/g) || []).length, 3);
assert.equal((lastPopup.document.body.innerHTML.match(/<option /g) || []).length, 2);
assert.match(lastPopup.document.body.innerHTML, /<option value="0" selected>AFX 1<\/option>/);
assert.doesNotMatch(lastPopup.document.body.innerHTML, /<img/);
assert.equal(lastPopup.device.textContent, context.PROFILE.device.label);
lastPopup.close();
assert.equal(button.expanded, 'false');
button.click();
parentEvents.pagehide();
assert.equal(lastPopup.closed, true);
assert.equal(button.on, false);
async function checkEffectPreviews() {
  context.PROFILE = JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/orion_studio_sc.json'), 'utf8'));
  context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = false;
  const effect = JSON.parse(fs.readFileSync(path.join(ROOT, 'profiles/afx_effects.json'), 'utf8'))
    .effects.find(item => item.id === 'memory_brigade');
  const implementation = effect.implementations.find(item => item.profile === 'orion_studio_sc.json');
  const controls = Object.entries(implementation.control_encodings).map(([id, field]) => ({
    id, label: field.label, kind: field.kind, range: field.display_range, options: field.options,
  }));
  let requests = 0;
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/afx/catalog');
    assert.equal(options, undefined, 'Preview must use a metadata GET only');
    requests++;
    return {ok: true, json: async () => ({mode: 'preview', device_writes: false,
      effects: [{id: effect.id, name: effect.name, controls}]})};
  };
  button.click();
  vm.runInContext('selectAfxChannel(0)', context);
  await vm.runInContext("previewAfxEffect(0, 'memory_brigade')", context);
  const popup = lastPopup;
  assert.equal(requests, 1);
  assert.equal((popup.nodes['afx-rack'].innerHTML.match(/type="range"/g) || []).length, 6);
  assert.equal((popup.nodes['afx-rack'].innerHTML.match(/class="afx-mode-button"/g) || []).length, 4);
  assert.match(popup.nodes['afx-rack'].innerHTML, /Local preview/);
  assert.match(popup.nodes['afx-preview-status'].textContent, /do not load an effect/);

  const properties = {}, output = {};
  const group = {style: {setProperty(name, value) { properties[name] = value; }},
    querySelector() { return output; }};
  const input = {dataset: {afxSlot: '0', afxControl: 'level'}, value: '100',
    closest() { return group; }, matches() { return true; }};
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(output.textContent, '100');
  assert.equal(properties['--afx-turn'], '135deg');
  input.value = '101';
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(output.textContent, '100', 'Out-of-range input cannot change a draft');
  input.value = '0';
  popup.nodes['afx-rack'].input({target: input});
  assert.equal(properties['--afx-turn'], '-135deg');
  input.value = '42';
  popup.nodes['afx-rack'].input({target: input});

  // Dragging a knob changes only the draft; another pointer cannot move it.
  const handlers = {};
  const knobGroup = {querySelector: selector => selector === 'input' ? input : output,
    style: group.style};
  input.closest = () => knobGroup;
  const knob = {dataset: {afxSlot: '0'},
    closest: () => knobGroup,
    setPointerCapture(id) { this.pointer = id; },
    hasPointerCapture(id) { return this.pointer === id; },
    releasePointerCapture() { this.pointer = null; },
    addEventListener(name, handler) { handlers[name] = handler; },
    removeEventListener(name) { delete handlers[name]; }};
  const knobTarget = {closest: selector => selector === '[data-afx-slot]' || selector === '[data-afx-knob]' ? knob : null};
  popup.nodes['afx-rack'].pointerdown({target: knobTarget, button: 0, pointerId: 7,
    clientY: 100, preventDefault() {}});
  handlers.pointermove({pointerId: 8, clientY: 0});
  assert.equal(input.value, '42');
  handlers.pointermove({pointerId: 7, clientY: 80});
  assert.equal(input.value, '52');
  handlers.pointermove({pointerId: 7, clientY: 80, shiftKey: true});
  assert.equal(input.value, '44');
  handlers.pointerup({pointerId: 7});
  assert.equal(knob.pointer, null);
  assert.equal(Object.keys(handlers).length, 0);
  input.value = '42';
  popup.nodes['afx-rack'].input({target: input});

  const modeButton = (value) => ({dataset: {afxSlot: '0', afxMode: 'chrs_vibr', afxValue: value},
    setAttribute(_key, value) { this.pressed = value; }});
  const chorus = modeButton('chorus'), vibrato = modeButton('vibrato');
  for (const option of [chorus, vibrato]) option.parentElement = {querySelectorAll: () => [chorus, vibrato]};
  vibrato.closest = selector => ['[data-afx-slot]', '[data-afx-mode]'].includes(selector) ? vibrato : null;
  popup.nodes['afx-rack'].click({target: vibrato});
  assert.equal(vibrato.pressed, 'true');
  assert.equal(chorus.pressed, 'false');

  // Moving the bottom effect to the top preserves both drafts, including modes.
  await vm.runInContext("previewAfxEffect(7, 'memory_brigade')", context);
  vm.runInContext("AFX_DRAFTS.get('0:7').values.level = 88", context);
  const transfer = {value: '', setData(_type, value) { this.value = value; }, getData() { return this.value; }};
  const handle = {dataset: {afxDrag: '7'}, closest: selector => selector === '[data-afx-drag]' ? handle : null};
  const destination = {dataset: {afxRackSlot: '0'}, closest: selector => selector === '[data-afx-rack-slot]' ? destination : null};
  popup.nodes['afx-rack'].dragstart({target: handle, dataTransfer: transfer, preventDefault() {}});
  assert.equal(transfer.value, '0:7');
  popup.nodes['afx-rack'].drop({target: destination, dataTransfer: transfer, preventDefault() {}});
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:0').values.level", context), 88);
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:1').values.level", context), 42);
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:1').values.chrs_vibr", context), 'vibrato');
  transfer.value = '1:1';
  popup.nodes['afx-rack'].drop({target: destination, dataTransfer: transfer, preventDefault() {}});
  assert.equal(vm.runInContext("AFX_DRAFTS.get('0:0').values.level", context), 88, 'Cross-channel drop cannot move a draft');
  vm.runInContext('moveAfxDraft(1, 0)', context);

  vm.runInContext('selectAfxChannel(1)', context);
  assert.doesNotMatch(popup.nodes['afx-rack'].innerHTML, /type="range"/);
  await vm.runInContext("previewAfxEffect(0, 'memory_brigade')", context);
  assert.equal(requests, 1, 'A local catalog is cached, rather than fetched per control');
  vm.runInContext('selectAfxChannel(0)', context);
  assert.match(popup.nodes['afx-rack'].innerHTML, /value="42"[^]*?data-afx-control="level"/);
  assert.match(popup.nodes['afx-rack'].innerHTML, /aria-pressed="true"[^]*?data-afx-value="vibrato"/);
  popup.close();
  button.click();
  assert.match(lastPopup.document.body.innerHTML, /value="42"[^]*?data-afx-control="level"/);
  const remove = {dataset: {afxRemove: '0'}, closest: selector => selector === '[data-afx-remove]' ? remove : null};
  lastPopup.nodes['afx-rack'].click({target: remove});
  assert.equal((lastPopup.nodes['afx-rack'].innerHTML.match(/type="range"/g) || []).length, 6);
  vm.runInContext("AFX_DRAFTS.delete('0:1')", context);

  // Closing the window during a slow metadata GET must not repaint a new popup.
  let release;
  context.fetch = () => new Promise(resolve => { release = resolve; });
  vm.runInContext('AFX_PREVIEW_CATALOG = null', context);
  const pending = vm.runInContext("previewAfxEffect(2, 'memory_brigade')", context);
  lastPopup.close();
  button.click();
  const reopened = lastPopup;
  release({ok: true, json: async () => ({mode: 'preview', device_writes: false,
    effects: [{id: effect.id, name: effect.name, controls}]})});
  await pending;
  assert.doesNotMatch(reopened.document.body.innerHTML, /type="range"/);
  reopened.close();

  // Connecting reads metadata only; knobs and switches stay drafts until Apply.
  const emptySlots = Array.from({length: 8}, () => ({type: 0, instance: 0}));
  emptySlots[0] = {type: 73, instance: 4};
  const state = {available: true, online: true, writes_enabled: true, slots: emptySlots,
    parameters: {}, session: 1};
  const writes = [];
  let deviceReads = 0;
  context.fetch = async (url, options) => {
    assert.match(url, /^\/api\/afx\/memorycat-test/);
    if (options) {
      assert.equal(options.method, 'POST');
      writes.push({url, body: JSON.parse(options.body)});
    } else deviceReads++;
    return {ok: true, json: async () => options && url.endsWith('/parameters') ? {sent: true, verified: false} : state};
  };
  context.PROFILE.runtime_contracts.afx_memorycat_test.enabled = true;
  vm.runInContext('AFX_CHANNEL = 31', context);
  button.click();
  await new Promise(resolve => setImmediate(resolve));
  const live = lastPopup;
  assert.equal(deviceReads, 1, 'Opening the enabled pilot automatically reads the device rack');
  assert.equal(writes.length, 0, 'Opening the rack must never write to the device');
  assert.equal(live.nodes['afx-channel'].value, '0', 'Open on the supported pilot channel');
  assert.match(live.nodes['afx-rack'].innerHTML, /Device test/);
  assert.equal((live.nodes['afx-rack'].innerHTML.match(/>Load Memory Cat</g) || []).length, 7);
  assert.doesNotMatch(live.nodes['afx-rack'].innerHTML, /Preview Memory/);
  assert.match(live.nodes['afx-slot-list'].innerHTML, /Memory Cat/);
  assert.equal((live.nodes['afx-slot-list'].innerHTML.match(/>Empty</g) || []).length, 7);
  vm.runInContext('selectAfxChannel(1)', context);
  assert.match(live.nodes['afx-preview-status'].textContent, /AFX 1 only/);
  assert.doesNotMatch(live.nodes['afx-rack'].innerHTML, /data-afx-device-load/);
  vm.runInContext('selectAfxChannel(0)', context);
  const apply = {dataset: {afxDeviceApply: '0'}, closest: selector => selector === '[data-afx-device-apply]' ? apply : null};
  live.nodes['afx-rack'].click({target: apply});
  assert.match(live.nodes['afx-preview-status'].textContent, /Select both switch positions/);
  assert.equal(writes.length, 0);
  live.nodes['afx-rack'].input({target: input});
  vm.runInContext("afxTestDraft(0, 0).values.chrs_vibr = '1'; afxTestDraft(0, 0).values.size = '0'", context);
  assert.equal(writes.length, 0, 'Draft edits never send parameters');
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test/parameters', {instance: 4, values: Object.fromEntries(Object.entries(afxTestDraft(0, 0).values).map(([id, value]) => [id, Number(value)]))})", context);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].body.instance, 4);
  assert.equal(writes[0].body.values.level, 42);
  assert.equal(writes[0].body.values.chrs_vibr, 1);
  assert.equal(Object.keys(writes[0].body.values).length, 8);
  assert.match(live.nodes['afx-preview-status'].textContent, /Parameter readback is unavailable/);
  // Instance drafts follow chain reorder and are discarded on reconnection.
  state.slots = [{type: 0, instance: 0}, ...emptySlots.slice(0, 7)];
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).values.level', context), 42);
  state.session = 2;
  await vm.runInContext("afxTestRequest('/api/afx/memorycat-test')", context);
  assert.equal(vm.runInContext('afxTestDraft(0, 1).values.chrs_vibr', context), null);
  assert.equal(writes.length, 1);
  const previewButton = {closest: selector => selector === '[data-afx-test-preview]' ? previewButton : null};
  vm.runInContext('afxTestClick', context)({target: previewButton});
  assert.match(live.nodes['afx-rack'].innerHTML, /Preview Memory/);
  assert.match(live.nodes['afx-preview-status'].textContent, /do not load effects/);
  const refreshButton = {closest: selector => selector === '[data-afx-test-refresh]' ? refreshButton : null};
  vm.runInContext('afxTestClick', context)({target: refreshButton});
  await new Promise(resolve => setImmediate(resolve));
  assert.match(live.nodes['afx-rack'].innerHTML, /data-afx-device-load/);
  assert.equal(writes.length, 1, 'Switching rack views only reads metadata');
  live.close();
  console.log('AFX checks passed (device rack on open, load buttons, previews, drag, Apply, reconnect).');
}

checkEffectPreviews().catch(error => { console.error(error); process.exitCode = 1; });
