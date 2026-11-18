"use strict";

// This page loads only profile/catalog metadata. No device rack or stream starts.
let PROFILE = null;
function reportMessage(_key, title, message) {
  const status = document.getElementById('afx-preview-status') || document.getElementById('afx-studio-error');
  if (status) status.textContent = `${title}: ${message}`;
}
function clearMessage() {}

async function startAfxStudio() {
  try {
    const response = await fetch('/api/profile');
    if (!response.ok) throw new Error('Could not load the device profile.');
    PROFILE = await response.json();
    const capacity = afxCapacity();
    if (!capacity) throw new Error('AFX panel capacity is unavailable for this profile.');
    AFX_WINDOW = window;
    mountAfxWindow(window, capacity);
    document.querySelector('h1').textContent = 'AFX · Panel studio';
    for (const [slot, effect] of ['pultec_meq', 'pultec_eqp', 'powergate', 'powerex', 'deesser'].entries())
      if (slot < capacity.slots) await previewAfxEffect(slot, effect);
    document.getElementById('afx-preview-status').textContent = 'Local panels · drag knobs, use Shift for fine adjustment, or select a fixed frequency position.';
  } catch (error) { reportMessage('studio', 'Panel studio', error.message); }
}
window.addEventListener('DOMContentLoaded', () => { void startAfxStudio(); });
