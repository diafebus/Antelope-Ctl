const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const JS_FILES = [
  'ui/core.js',
  'ui/inputs.js',
  'ui/settings.js',
  'ui/preamp.js',
  'ui/meters.js',
  'ui/buses.js',
  'ui/routing.js',
  'ui/mixer.js',
  'ui/surround.js',
  'ui/readback.js',
  'ui/boot.js',
];

function readWebUISource() {
  return JS_FILES
    .map(file => fs.readFileSync(path.join(ROOT, 'webui/static', file), 'utf8'))
    .join('\n');
}

module.exports = {ROOT, JS_FILES, readWebUISource};
