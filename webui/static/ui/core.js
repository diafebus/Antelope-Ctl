"use strict";

// Shared UI state, persistence, messages, and API helpers.
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
let PROFILE = null, MODES = [], N_CH = 12, HIZ = new Set(), GAIN_RANGE = {}, N_PAIRS = 0;
let ROUTING = null, MIXER = null, STRUCTURED = null, MIXER_METERS = null, ACTIVE_MIX = 0;
let UI_FEATURES = {}, AURAVERB = null, MIXER_SOURCES = {}, AURAVERB_LOCAL = null;
const MIX_PENDING = {}, MIX_PENDING_TTL = 5000;
let MIX_SOLO_RESTORE = {};
let MIX_LINKS = {};
let RB_VER = -1, LINK_RB_VER = -1, ONLINE = false;
let EMU_CHANNELS = new Set();
const MESSAGES = new Map();

function renderMessages() {
  const body = $('#messagesbody'), btn = $('#messagesbtn');
  if (!body || !btn) return;
  body.innerHTML = [...MESSAGES.values()].map(m =>
    `<article class="message"><b>${m.title}</b><div>${m.body}</div></article>`).join('')
    || '<p class="message">No messages.</p>';
  btn.classList.toggle('has', MESSAGES.size > 0);
}
function reportMessage(key, title, body) {
  MESSAGES.set(key, {title, body}); renderMessages();
}
function clearMessage(key) { if (MESSAGES.delete(key)) renderMessages(); }
function setMessagesOpen(open) {
  const panel = $('#messagespanel'), btn = $('#messagesbtn');
  panel.hidden = !open; btn.setAttribute('aria-expanded', String(open));
}
$('#messagesbtn').addEventListener('click', () => setMessagesOpen($('#messagespanel').hidden));
$('[data-messages-close]').addEventListener('click', () => setMessagesOpen(false));
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('#messagespanel').hidden) setMessagesOpen(false);
});

// ---- emuMic / mic modeling ------------------------------------------
// Preamps 5-12 (EMU button is Mic-mode-gated). The controls remain
// browser-side for now because the write path has no verified round-trip;
// the profile-driven protocol readback panel separately shows category 0x16.
// v1: on/off + the model-0 polar-pattern morph (0 omni / 50 card / 100 fig-8).
// Model picker is a follow-up (the available list is account-bound, not on
// the device -- see profiles/mic_models.json).
const EMU = loadEmu();
const hasEmu = ch => UI_FEATURES?.mic_modeling?.enabled !== false && EMU_CHANNELS.has(ch);
const emuOn  = ch => !!(EMU[ch] && EMU[ch].on);
const emuPat = ch => (EMU[ch] && EMU[ch].pattern != null) ? EMU[ch].pattern : 50;
function loadEmu() {
  try { return JSON.parse(localStorage.getItem('preampEmu') || '{}') || {}; }
  catch (_) { return {}; }
}
function saveEmu() {
  try { localStorage.setItem('preampEmu', JSON.stringify(EMU)); } catch (_) {}
}

// ---- preamp-pair link -------------------------------------------------
// Persisted per-viewer fallback for the physical preamp link domain. Zen Go's
// mapped q0b/03 table is a mixer-link bitmap, not this preamp state.
// pair N = channels 2N & 2N+1.
const LINKS = loadLinks();
const pairOf    = ch => ch >> 1;
const partnerOf = ch => ch ^ 1;
const isLinked  = ch => pairOf(ch) < N_PAIRS && !!LINKS[pairOf(ch)];
function loadLinks() {
  try { return JSON.parse(localStorage.getItem('preampLinks') || '{}') || {}; }
  catch (_) { return {}; }
}
function saveLinks() {
  try { localStorage.setItem('preampLinks', JSON.stringify(LINKS)); } catch (_) {}
}
const GEAR_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M12 8C9.79 8 8 9.79 8 12C8 14.21 9.79 16 12 16C14.21 16 16 14.21 16 12C16 9.79 14.21 8 12 8ZM10 12C10 10.9 10.9 10 12 10C13.1 10 14 10.9 14 12C14 13.1 13.1 14 12 14C10.9 14 10 13.1 10 12Z"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M10.7673 1.01709C10.9925 0.999829 11.2454 0.99993 11.4516 1.00001L12.5484 1.00001C12.7546 0.99993 13.0075 0.999829 13.2327 1.01709C13.4989 1.03749 13.8678 1.08936 14.2634 1.26937C14.7635 1.49689 15.1915 1.85736 15.5007 2.31147C15.7454 2.67075 15.8592 3.0255 15.9246 3.2843C15.9799 3.50334 16.0228 3.75249 16.0577 3.9557L16.1993 4.77635L16.2021 4.77788C16.2369 4.79712 16.2715 4.81659 16.306 4.8363L16.3086 4.83774L17.2455 4.49865C17.4356 4.42978 17.6693 4.34509 17.8835 4.28543C18.1371 4.2148 18.4954 4.13889 18.9216 4.17026C19.4614 4.20998 19.9803 4.39497 20.4235 4.70563C20.7734 4.95095 21.0029 5.23636 21.1546 5.4515C21.2829 5.63326 21.4103 5.84671 21.514 6.02029L22.0158 6.86003C22.1256 7.04345 22.2594 7.26713 22.3627 7.47527C22.4843 7.7203 22.6328 8.07474 22.6777 8.52067C22.7341 9.08222 22.6311 9.64831 22.3803 10.1539C22.1811 10.5554 21.9171 10.8347 21.7169 11.0212C21.5469 11.1795 21.3428 11.3417 21.1755 11.4746L20.5 12L21.1755 12.5254C21.3428 12.6584 21.5469 12.8205 21.7169 12.9789C21.9171 13.1653 22.1811 13.4446 22.3802 13.8461C22.631 14.3517 22.7341 14.9178 22.6776 15.4794C22.6328 15.9253 22.4842 16.2797 22.3626 16.5248C22.2593 16.7329 22.1255 16.9566 22.0158 17.14L21.5138 17.9799C21.4102 18.1535 21.2828 18.3668 21.1546 18.5485C21.0028 18.7637 20.7734 19.0491 20.4234 19.2944C19.9803 19.6051 19.4613 19.7901 18.9216 19.8298C18.4954 19.8612 18.1371 19.7852 17.8835 19.7146C17.6692 19.6549 17.4355 19.5703 17.2454 19.5014L16.3085 19.1623L16.306 19.1638C16.2715 19.1835 16.2369 19.2029 16.2021 19.2222L16.1993 19.2237L16.0577 20.0443C16.0228 20.2475 15.9799 20.4967 15.9246 20.7157C15.8592 20.9745 15.7454 21.3293 15.5007 21.6886C15.1915 22.1427 14.7635 22.5032 14.2634 22.7307C13.8678 22.9107 13.4989 22.9626 13.2327 22.983C13.0074 23.0002 12.7546 23.0001 12.5484 23H11.4516C11.2454 23.0001 10.9925 23.0002 10.7673 22.983C10.5011 22.9626 10.1322 22.9107 9.73655 22.7307C9.23648 22.5032 8.80849 22.1427 8.49926 21.6886C8.25461 21.3293 8.14077 20.9745 8.07542 20.7157C8.02011 20.4967 7.97723 20.2475 7.94225 20.0443L7.80068 19.2237L7.79791 19.2222C7.7631 19.2029 7.72845 19.1835 7.69396 19.1637L7.69142 19.1623L6.75458 19.5014C6.5645 19.5702 6.33078 19.6549 6.11651 19.7146C5.86288 19.7852 5.50463 19.8611 5.07841 19.8298C4.53866 19.7901 4.01971 19.6051 3.57654 19.2944C3.2266 19.0491 2.99714 18.7637 2.84539 18.5485C2.71718 18.3668 2.58974 18.1534 2.4861 17.9798L1.98418 17.14C1.87447 16.9566 1.74067 16.7329 1.63737 16.5248C1.51575 16.2797 1.36719 15.9253 1.32235 15.4794C1.26588 14.9178 1.36897 14.3517 1.61976 13.8461C1.81892 13.4446 2.08289 13.1653 2.28308 12.9789C2.45312 12.8205 2.65717 12.6584 2.82449 12.5254L3.47844 12.0054V11.9947L2.82445 11.4746C2.65712 11.3417 2.45308 11.1795 2.28304 11.0212C2.08285 10.8347 1.81888 10.5554 1.61972 10.1539C1.36893 9.64832 1.26584 9.08224 1.3223 8.52069C1.36714 8.07476 1.51571 7.72032 1.63732 7.47528C1.74062 7.26715 1.87443 7.04347 1.98414 6.86005L2.48605 6.02026C2.58969 5.84669 2.71714 5.63326 2.84534 5.45151C2.9971 5.23637 3.22655 4.95096 3.5765 4.70565C4.01966 4.39498 4.53862 4.20999 5.07837 4.17027C5.50458 4.1389 5.86284 4.21481 6.11646 4.28544C6.33072 4.34511 6.56444 4.4298 6.75451 4.49867L7.69141 4.83775L7.69394 4.8363C7.72844 4.8166 7.7631 4.79712 7.79791 4.77788L7.80068 4.77635L7.94225 3.95571C7.97723 3.7525 8.02011 3.50334 8.07542 3.2843C8.14077 3.0255 8.25461 2.67075 8.49926 2.31147C8.80849 1.85736 9.23648 1.49689 9.73655 1.26937C10.1322 1.08936 10.5011 1.03749 10.7673 1.01709ZM14.0938 4.3363C14.011 3.85634 13.9696 3.61637 13.8476 3.43717C13.7445 3.2858 13.6019 3.16564 13.4352 3.0898C13.2378 3.00002 12.9943 3.00002 12.5073 3.00002H11.4927C11.0057 3.00002 10.7621 3.00002 10.5648 3.0898C10.3981 3.16564 10.2555 3.2858 10.1524 3.43717C10.0304 3.61637 9.98895 3.85634 9.90615 4.3363L9.75012 5.24064C9.69445 5.56333 9.66662 5.72467 9.60765 5.84869C9.54975 5.97047 9.50241 6.03703 9.40636 6.13166C9.30853 6.22804 9.12753 6.3281 8.76554 6.52822C8.73884 6.54298 8.71227 6.55791 8.68582 6.57302C8.33956 6.77078 8.16643 6.86966 8.03785 6.90314C7.91158 6.93602 7.83293 6.94279 7.70289 6.93196C7.57049 6.92094 7.42216 6.86726 7.12551 6.7599L6.11194 6.39308C5.66271 6.2305 5.43809 6.14921 5.22515 6.16488C5.04524 6.17811 4.87225 6.23978 4.72453 6.34333C4.5497 6.46589 4.42715 6.67094 4.18206 7.08103L3.72269 7.84965C3.46394 8.2826 3.33456 8.49907 3.31227 8.72078C3.29345 8.90796 3.32781 9.09665 3.41141 9.26519C3.51042 9.4648 3.7078 9.62177 4.10256 9.9357L4.82745 10.5122C5.07927 10.7124 5.20518 10.8126 5.28411 10.9199C5.36944 11.036 5.40583 11.1114 5.44354 11.2504C5.47844 11.379 5.47844 11.586 5.47844 12C5.47844 12.414 5.47844 12.621 5.44354 12.7497C5.40582 12.8887 5.36944 12.9641 5.28413 13.0801C5.20518 13.1875 5.07927 13.2876 4.82743 13.4879L4.10261 14.0643C3.70785 14.3783 3.51047 14.5352 3.41145 14.7349C3.32785 14.9034 3.29349 15.0921 3.31231 15.2793C3.33461 15.501 3.46398 15.7174 3.72273 16.1504L4.1821 16.919C4.4272 17.3291 4.54974 17.5342 4.72457 17.6567C4.8723 17.7603 5.04528 17.8219 5.2252 17.8352C5.43813 17.8508 5.66275 17.7695 6.11199 17.607L7.12553 17.2402C7.42216 17.1328 7.5705 17.0791 7.7029 17.0681C7.83294 17.0573 7.91159 17.064 8.03786 17.0969C8.16644 17.1304 8.33956 17.2293 8.68582 17.427C8.71228 17.4421 8.73885 17.4571 8.76554 17.4718C9.12753 17.6719 9.30853 17.772 9.40635 17.8684C9.50241 17.963 9.54975 18.0296 9.60765 18.1514C9.66662 18.2754 9.69445 18.4367 9.75012 18.7594L9.90615 19.6637C9.98895 20.1437 10.0304 20.3837 10.1524 20.5629C10.2555 20.7142 10.3981 20.8344 10.5648 20.9102C10.7621 21 11.0057 21 11.4927 21H12.5073C12.9943 21 13.2378 21 13.4352 20.9102C13.6019 20.8344 13.7445 20.7142 13.8476 20.5629C13.9696 20.3837 14.011 20.1437 14.0938 19.6637L14.2499 18.7594C14.3055 18.4367 14.3334 18.2754 14.3923 18.1514C14.4502 18.0296 14.4976 17.963 14.5936 17.8684C14.6915 17.772 14.8725 17.6719 15.2344 17.4718C15.2611 17.4571 15.2877 17.4421 15.3141 17.427C15.6604 17.2293 15.8335 17.1304 15.9621 17.0969C16.0884 17.064 16.167 17.0573 16.2971 17.0681C16.4295 17.0791 16.5778 17.1328 16.8744 17.2402L17.888 17.607C18.3372 17.7696 18.5619 17.8509 18.7748 17.8352C18.9547 17.8219 19.1277 17.7603 19.2754 17.6567C19.4502 17.5342 19.5728 17.3291 19.8179 16.919L20.2773 16.1504C20.536 15.7175 20.6654 15.501 20.6877 15.2793C20.7065 15.0921 20.6721 14.9034 20.5885 14.7349C20.4895 14.5353 20.2921 14.3783 19.8974 14.0643L19.1726 13.4879C18.9207 13.2876 18.7948 13.1875 18.7159 13.0801C18.6306 12.9641 18.5942 12.8887 18.5564 12.7497C18.5215 12.6211 18.5215 12.414 18.5215 12C18.5215 11.586 18.5215 11.379 18.5564 11.2504C18.5942 11.1114 18.6306 11.036 18.7159 10.9199C18.7948 10.8126 18.9207 10.7124 19.1725 10.5122L19.8974 9.9357C20.2922 9.62176 20.4896 9.46479 20.5886 9.26517C20.6722 9.09664 20.7065 8.90795 20.6877 8.72076C20.6654 8.49906 20.5361 8.28259 20.2773 7.84964L19.8179 7.08102C19.5728 6.67093 19.4503 6.46588 19.2755 6.34332C19.1277 6.23977 18.9548 6.1781 18.7748 6.16486C18.5619 6.14919 18.3373 6.23048 17.888 6.39307L16.8745 6.75989C16.5778 6.86725 16.4295 6.92093 16.2971 6.93195C16.167 6.94278 16.0884 6.93601 15.9621 6.90313C15.8335 6.86965 15.6604 6.77077 15.3142 6.57302C15.2877 6.55791 15.2611 6.54298 15.2345 6.52822C14.8725 6.3281 14.6915 6.22804 14.5936 6.13166C14.4976 6.03703 14.4502 5.97047 14.3923 5.84869C14.3334 5.72467 14.3055 5.56332 14.2499 5.24064L14.0938 4.3363Z"/>
</svg>`;
const POPOUT_ICON = `<svg viewBox="0 0 36 36" aria-hidden="true" fill="currentColor">
  <path d="M27,33H5a2,2,0,0,1-2-2V9A2,2,0,0,1,5,7H15V9H5V31H27V21h2V31A2,2,0,0,1,27,33Z"/>
  <path d="M18,3a1,1,0,0,0,0,2H29.59L15.74,18.85a1,1,0,1,0,1.41,1.41L31,6.41V18a1,1,0,0,0,2,0V3Z"/>
</svg>`;
const LINK_ICON = `<svg class="lkico" viewBox="0 0 22 22" aria-hidden="true">
  <path d="M8 16 H6.5 A4.2 4.2 0 0 1 6.5 7.6 H8"/>
  <path d="M14 7.6 H15.5 A4.2 4.2 0 0 1 15.5 16 H14"/>
  <line class="lk-whole" x1="7.4" y1="11.8" x2="14.6" y2="11.8"/>
  <line class="lk-broken" x1="7.4" y1="11.8" x2="9.7" y2="11.8"/>
  <line class="lk-broken" x1="12.3" y1="11.8" x2="14.6" y2="11.8"/>
</svg>`;

async function post(path, body) {
  if (!ONLINE) return;
  try {
    const r = await fetch(path, {method:'POST', headers:{'content-type':'application/json'},
                                body:JSON.stringify(body)});
    if (!r.ok) {
      const detail = await r.text();
      if (r.status === 404 && path === '/api/auraverb') {
        reportMessage('comm', `${AV_DISPLAY_NAME} API unavailable`,
          'The running daemon is older than this WebUI. Stop the old server, '
          + 'restart <code>python3 server.py</code> from the current webui directory, '
          + 'then hard-refresh the page. ' + detail);
      } else {
        reportMessage('comm', 'Control command failed', `${path}: ${detail}`);
      }
    }
  } catch (_) { reportMessage('comm', 'Connection lost', `Unable to send ${path}.`); }
}
async function getJSON(path) { return (await fetch(path)).json(); }

// ---- preamp strips ----------------------------------------------------
// Knob shapes lifted from assets/preamp-knob.svg; centre (54.840942, 52.983658),
// bezel r 12.5. Value 0..1 maps to a 270° sweep (-135°..+135° from 12 o'clock),
// which lines the pointer up with the level ring's own opening.
const KNOB_C = '54.840942 52.983658';
const KNOB_A0 = -135, KNOB_SWEEP = 270;
// Rotary controls use a deliberately longer drag distance than their visual
// size. This keeps a small mouse movement from making a large parameter jump.
const KNOB_DRAG_PIXELS = 240;
// Level ring round the knob, straight from assets/PreampUI-KNOB-level.svg (a
// 270° band, r 14.5..15.5, gap at the bottom) -- its raw `d` shifted so its
// centre sits on the knob centre.
const RING_BAND_D = 'M 46.819364,42.810307 A 15.5,15.5 0 0 0 31.319019,58.310136 '
  + '15.5,15.5 0 0 0 35.858793,69.27019 l 0.70745,-0.706933 '
  + 'a 14.5,14.5 0 0 1 -4.247285,-10.253121 14.5,14.5 0 0 1 14.500406,-14.49989 '
  + '14.5,14.5 0 0 1 14.499891,14.49989 14.5,14.5 0 0 1 -4.247286,10.253121 '
  + 'l 0.70745,0.706933 A 15.5,15.5 0 0 0 62.319194,58.310136 '
  + '15.5,15.5 0 0 0 46.819364,42.810307 Z';
const RING_BAND_SHIFT = 'translate(8.021578 -5.326478)';
// The white "where's the pot" fill: an arc on the band centre-line (r 15),
// same -135°..+135° span as the pointer, revealed by stroke-dashoffset.
// Real length (15 * 270° in rad), not pathLength -- some renderers ignore that.
const RING_D = 'M 44.234 63.591 A 15 15 0 1 1 65.448 63.591';
const RING_LEN = 70.69;
function modeRange(mode) {
  const key = String(mode || '').toLowerCase();
  const range = GAIN_RANGE[mode] || GAIN_RANGE[key];
  return Array.isArray(range) && range.length === 2
    ? range.map(Number) : [-6, 75];
}
