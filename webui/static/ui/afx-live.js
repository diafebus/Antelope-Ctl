"use strict";

// One request at a time; keep the latest full block for each instance.
const AFX_LIVE_PENDING = new Map();
let AFX_LIVE_TIMER = null;
let AFX_LIVE_INFLIGHT = false;

function afxLiveChanged(draft) {
  if (!draft.parameterAvailable) return;
  if (draft.livePaused) {
    if (afxWindowIsOpen()) AFX_WINDOW.document.getElementById('afx-preview-status').textContent =
      'Live controls paused after a failed send. Click Retry live controls to send the displayed settings.';
    return;
  }
  if (!afxTestActive() || !AFX_TEST_STATE.online || !AFX_TEST_STATE.writes_enabled) return;
  const values = Object.fromEntries(Object.entries(draft.values).map(([id, value]) => [id, Number(value)]));
  if (Object.values(draft.values).some(value => value == null)) return;
  AFX_LIVE_PENDING.set(draft.instance, {channel: AFX_CHANNEL, values, session: AFX_TEST_SESSION, draft});
  if (AFX_LIVE_TIMER == null && !AFX_LIVE_INFLIGHT)
    AFX_LIVE_TIMER = setTimeout(afxLiveFlush, 60);
}

async function afxLiveFlush() {
  AFX_LIVE_TIMER = null;
  if (!AFX_LIVE_PENDING.size || AFX_LIVE_INFLIGHT) return;
  if (!afxWindowIsOpen() || !afxTestActive() || !AFX_TEST_STATE.online || !AFX_TEST_STATE.writes_enabled) {
    AFX_LIVE_PENDING.clear();
    return;
  }
  if (AFX_TEST_BUSY) { AFX_LIVE_TIMER = setTimeout(afxLiveFlush, 60); return; }
  const [instance, pending] = AFX_LIVE_PENDING.entries().next().value;
  AFX_LIVE_PENDING.delete(instance);
  if (pending.session !== AFX_TEST_SESSION || pending.channel !== AFX_CHANNEL
      || pending.draft !== AFX_TEST_DRAFTS.get(instance) || pending.draft.livePaused
      || !afxTestSlots(pending.channel)?.some(row => row.type === 73 && row.instance === instance)) {
    if (AFX_LIVE_PENDING.size) AFX_LIVE_TIMER = setTimeout(afxLiveFlush, 60);
    return;
  }
  AFX_LIVE_INFLIGHT = true;
  AFX_TEST_BUSY = true;
  const popup = AFX_WINDOW;
  try {
    const response = await fetch('/api/afx/memorycat-test/parameters', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({channel: pending.channel, instance, values: pending.values}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Live parameter write failed');
    if (AFX_TEST_SESSION === pending.session && AFX_TEST_DRAFTS.get(instance) === pending.draft) {
      for (const update of result.updated_instances || []) {
        (AFX_TEST_STATE.parameters ||= {})[String(update.instance)] = {...update.values};
        if (update.verified)
          (AFX_TEST_STATE.parameter_states ||= {})[String(update.instance)] = {
            values: {...update.values}, bypassed: update.bypassed, source: 'readback'};
        const partnerDraft = AFX_TEST_DRAFTS.get(update.instance);
        if (partnerDraft && partnerDraft !== pending.draft && !AFX_LIVE_PENDING.has(update.instance)) {
          for (const control of partnerDraft.effect.controls)
            partnerDraft.values[control.id] = control.kind === 'enum'
              ? String(update.values[control.id]) : update.values[control.id];
          partnerDraft.parameterAvailable = true;
          partnerDraft.parameterSource = update.verified ? 'readback' : 'last-sent';
          partnerDraft.bypassed = update.bypassed;
        }
      }
      (AFX_TEST_STATE.parameters ||= {})[String(instance)] = {...pending.values};
      pending.draft.liveReady = true;
      if (AFX_WINDOW === popup && !popup.closed) {
        const selectedVerified = result.updated_instances?.find(update => update.instance === instance)?.verified ?? result.verified;
        if (selectedVerified) {
          pending.draft.parameterSource = 'readback';
          pending.draft.bypassed = result.bypassed;
          (AFX_TEST_STATE.parameter_states ||= {})[String(instance)] = {
            values: {...pending.values}, bypassed: result.bypassed, source: 'readback'};
        } else pending.draft.parameterSource = 'last-sent';
        popup.document.getElementById('afx-preview-status').textContent = result.verified
          ? `Live settings verified by device readback${result.mirrored ? ' · linked pair' : ''}`
          : 'Live settings sent · some instance readbacks unavailable';
        AFX_PANELS.get(pending.draft.effect.id).updateLiveStatus(pending.draft, popup.document);
      }
    }
    // Do not repaint the rack during a drag: it would destroy pointer capture.
  } catch (error) {
    AFX_LIVE_PENDING.clear();
    const draft = AFX_TEST_DRAFTS.get(instance);
    if (draft === pending.draft) draft.livePaused = true;
    if (AFX_WINDOW === popup && !popup.closed) {
      popup.document.getElementById('afx-preview-status').textContent = error.message + '. Live sending paused; click Retry live controls to resume.';
      if (draft === pending.draft) AFX_PANELS.get(draft.effect.id).updateLiveStatus(draft, popup.document);
    }
    // Failed device writes are never automatically retried.
  } finally {
    AFX_LIVE_INFLIGHT = false;
    AFX_TEST_BUSY = false;
    if (AFX_LIVE_PENDING.size) AFX_LIVE_TIMER = setTimeout(afxLiveFlush, 60);
  }
}

AFX_DEVICE_RACK.parameterChanged = afxLiveChanged;
