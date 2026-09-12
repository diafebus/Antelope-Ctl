"use strict";

// ---- boot + live feed (SSE) ---------------------------------------
function markOffline(text) {
  ONLINE = false;
  applyMeters([]);
  applyMixerMeters(null);
  applyOutputMeters(null);
  reportMessage('connection', 'Device connection', text);
  const st = $('#status'); st.className = 'offline'; st.textContent = text;
  $('#main').classList.add('offline');
}

function profileLabel(namespace, key, fallback) {
  const value = PROFILE?.labels?.[namespace]?.[key];
  if (value && typeof value === 'object') return value.label || value.name || fallback;
  return value || fallback;
}

function profileSpaceLabel(space, values, fallback) {
  const spec = PROFILE?.labels?.spaces?.[space];
  const format = spec && typeof spec === 'object' ? spec.item_format : null;
  if (!format) return fallback;
  return format.replace(/\{(\w+)\}/g,
    (_, key) => values[key] == null ? `{${key}}` : values[key]);
}

function featureLabel(key, fallback) {
  const feature = PROFILE?.webui?.features?.[key] || PROFILE?.features?.[key];
  return feature?.label || fallback;
}

function setSectionHeading(selector, label) {
  const heading = document.querySelector(`${selector} .sechd`);
  if (heading?.firstChild) heading.firstChild.nodeValue = `${label} `;
}

function applyProfileCapabilities() {
  const cap = PROFILE.webui || {};
  const featureEnabled = (key, fallback) => {
    const feature = UI_FEATURES?.[key];
    return feature ? feature.enabled !== false : fallback;
  };
  const inputs = featureEnabled('inputs', true);
  const digital = featureEnabled('digital_inputs', true) && (DIG.adat.n || DIG.spdif.n);
  const buses = featureEnabled('buses', true);
  const settings = featureEnabled('settings', true);
  const routing = cap.routing === true && featureEnabled('routing', true);
  const mixer = cap.mixer === true && featureEnabled('mixer', true);
  const surround = cap.surround === true && featureEnabled('surround', false);
  $('[data-tab="inputs"]').hidden = !inputs;
  $('[data-pane="inputs"]').hidden = !inputs;
  $('[data-tab="adat"]').hidden = !digital;
  $('[data-pane="adat"]').hidden = !digital;
  if (!digital && $('[data-pane="adat"]').previousElementSibling) $('[data-tab="inputs"]').classList.add('active');
  $('#busessec').hidden = !buses;
  $('#gearbtn').hidden = !settings;
  const section = $('#routesec');
  section.hidden = !routing && !mixer && !surround;
  const matrixTab = $('#routetabs [data-rtab="matrix"]');
  matrixTab.hidden = !routing;
  $('[data-rpane="matrix"]').hidden = !routing;
  $$('#routetabs [data-rtab^="mix"]').forEach(btn => {
    const n = Number(btn.dataset.rtab.slice(3));
    btn.hidden = !mixer || n > Number(cap.mixes || 0);
  });
  const surroundTab = $('#routetabs [data-rtab="surround"]');
  if (surroundTab) surroundTab.hidden = !surround;
  const surroundPane = $('[data-rpane="surround"]');
  if (surroundPane) surroundPane.hidden = !surround;
  const active = $('#routetabs .tabbtn.active');
  if (active?.hidden) {
    const first = [...$('#routetabs').querySelectorAll('.tabbtn')]
      .find(btn => !btn.hidden);
    if (first) first.click();
  }
}

async function boot() {
  try {
    PROFILE = await getJSON('/api/profile');
  } catch (_) {
    markOffline('daemon unreachable — retrying');
    return setTimeout(boot, 1500);
  }
  $('#dev').textContent = PROFILE.device?.label || PROFILE.device?.name || '';   // which profile the daemon picked
  const profileFeatures = PROFILE.webui?.features;
  UI_FEATURES = profileFeatures ? {...profileFeatures} : {};
  // Older daemons did not include the presentation registry in /api/profile.
  // The profile's explicit AuraVerb command is a safe compatibility fallback;
  // current daemons still take the normal device_ui.py path above.
  if (!profileFeatures && PROFILE.frame?.auraverb_command) {
    UI_FEATURES.auraverb = {enabled: true, mix: 0, label: AV_DISPLAY_NAME};
  }
  MIX_LINKS = loadMixLinks();
  loadMixerSources();
  const m = PROFILE.params?.input_mode?.values || PROFILE.channels?.modes || {};
  MODES = Object.values(m);
  GAIN_RANGE = PROFILE.params?.gain?.per_mode_range
    || PROFILE.params?.gain?.range_by_mode || {};
  HIZ = new Set(PROFILE.channels?.hiz_channels || []);
  N_CH = (PROFILE.channels?.count) || (PROFILE.channels?.count_confirmed) ||
         ((PROFILE.constraints?.channel_bounds?.max ?? 11) + 1);
  N_PAIRS = PROFILE.frame?.link_command
    ? (PROFILE.channels?.link_pairs?.count ?? Math.floor(N_CH / 2)) : 0;
  EMU_CHANNELS = new Set(PROFILE.frame?.micmodeling_command?.channels || []);
  if (EMU_CHANNELS.size) {
    MIC_MODELS = await getJSON('/api/mic_models').catch(() => ({}));
    EMU_MIC = loadEmuMic() || (MIC_MODELS.user_owned?.mics || [])[0]
      || Object.keys(MIC_MODELS.modelling_mics || {}).filter(k => k[0] !== '_')[0] || 'edge_duo';
  }
  DIG.adat.n = PROFILE.adat?.count || 0;
  DIG.adat.pairs = PROFILE.adat?.link_pairs?.count || 0;
  DIG.adat.range = PROFILE.params?.adat_gain?.range || [-6, 12];
  DIG.spdif.n = PROFILE.spdif?.count || 0;
  DIG.spdif.pairs = PROFILE.spdif?.link_pairs?.count || 0;
  DIG.spdif.range = PROFILE.params?.spdif_gain?.range || [-6, 12];

  $('[data-tab="inputs"]').textContent = profileLabel('sections', 'inputs', 'Inputs');
  $('[data-tab="adat"]').textContent = profileLabel('sections', 'digital_inputs', 'ADAT / S/PDIF');
  setSectionHeading('#busessec', featureLabel('buses', profileLabel('sections', 'outputs', 'Output buses')));
  setSectionHeading('#routesec', featureLabel('routing', profileLabel('sections', 'routing', 'Routing')));
  setSectionHeading('#readbacksec', profileLabel('sections', 'diagnostics', 'Protocol readback'));
  const matrixTab = $('#routetabs [data-rtab="matrix"]');
  if (matrixTab) matrixTab.textContent = featureLabel('routing', 'Routing');
  const surroundTab = $('#routetabs [data-rtab="surround"]');
  if (surroundTab) surroundTab.textContent = featureLabel('surround', 'Surround');

  applyProfileCapabilities();
  document.documentElement.style.setProperty('--meter-grad', meterGradient());
  buildChannels(N_CH);
  buildDig('adat');
  buildDig('spdif');
  initTabs();
  if (surroundTab && !surroundTab.hidden) buildSurround();
  buildSettings();
  buildClockBar();
  connect();
}

function connect() {
  const es = new EventSource('/api/stream');
  es.onmessage = e => { try { applyState(JSON.parse(e.data)); } catch (_) {} };
  es.onerror = () => markOffline('reconnecting…');   // EventSource retries on its own
}

boot();
