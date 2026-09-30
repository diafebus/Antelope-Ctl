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
      const events = {}, device = {}, closeButton = {};
      const popup = {
        closed: false, focused: 0, events, device, closeButton,
        document: {
          body: {innerHTML: ''}, open() {}, write() {}, close() {},
          getElementById() { return device; },
          querySelector() { return {
            addEventListener(_name, handler) { closeButton.click = handler; },
            focus() { closeButton.focused = true; },
          }; },
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
vm.runInContext(fs.readFileSync(path.join(ROOT, 'webui/static/ui/afx.js'), 'utf8'), context);

// Orion dimensions come from its profile; slots are unknown, never fake empty.
button.click();
const first = lastPopup;
assert.equal((first.document.body.innerHTML.match(/class="afx-channel"/g) || []).length, 32);
assert.equal((first.document.body.innerHTML.match(/class="afx-slot"/g) || []).length, 256);
assert.match(first.document.body.innerHTML, /state unavailable/);
assert.equal(first.device.textContent, context.PROFILE.device.label || context.PROFILE.device.name);
assert.equal(button.expanded, 'true');
assert.equal(first.closeButton.focused, true);
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
assert.equal((lastPopup.document.body.innerHTML.match(/class="afx-slot"/g) || []).length, 6);
assert.doesNotMatch(lastPopup.document.body.innerHTML, /<img/);
assert.equal(lastPopup.device.textContent, context.PROFILE.device.label);
lastPopup.close();
assert.equal(button.expanded, 'false');
button.click();
parentEvents.pagehide();
assert.equal(lastPopup.closed, true);
assert.equal(button.on, false);
console.log('AFX popup checks passed (profile capacity, focus, close, blocked popup, no device requests).');
