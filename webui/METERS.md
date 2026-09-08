# Orion meter evidence: current correction and historical review

## Scope and filter

This note gives the current meter contract and preserves the earlier
six-capture research below. Offsets are **full 320-byte report offsets**.
Profile `payload_offset` values are relative to the report payload and
therefore add `0x10`. Free-running `0x75` meter reports require byte 1 ==
`0x1f`; byte 1 == `0x00` is a readback response and is excluded.

The bounded review covered `vumeter-test-ch1.pcapng`,
`audioplaying-audiostop-meter.pcapng`, `vumeters-sinewave.pcapng`,
`preamp1-2-allouts mute.pcapng`, `matrixtest-pre1-cmpplay1-2.pcapng`, and
`mix1-masterfaderplay.pcapng`. These captures establish activity and
correlation only; they do not provide route-independent ownership isolation,
stereo/physical mapping, or a new hardware confirmation.

## Historical six-capture interpretation (superseded)

- Retain full-report `0x73` offsets **157..160** as one provisional mono lane
  per current Mix 1..4 label. DSP activity is observed, but fixed lane
  ownership is low confidence. Do not infer stereo or physical-preamp
  ownership.
- Repeated regions are not universal four-lane mirrors. Across the six
  captures, only `158↔222`, `159↔223`, and `160↔224` are exact throughout;
  first-lane copies `157↔169` and `157↔221` diverge in some captures.
- Playback `0x73` @177/@178 and meter-only `0x75` @34/@35 co-varied nearest in
  time within 5 ms (`r≈0.998`) in the playback capture. The owner is
  unresolved; this is not evidence for L/R, Mix 1 stereo, or physical input.
- `0x75` @32 was described as an aggregate/monitor observation and @33 as a
  flag. The controlled route-correlation result below supersedes those labels.

## Current runtime and documentation boundary

The current profile and Python runtime use full-report `0x73` offsets
**221..232** for physical preamps 1..12. The canonical
`state_report.channel_meter_base_offset` is 221, not 157.

The WebUI publishes these lanes as `input_meters` JSON samples. Each sample
has `raw`, `db`, `clip`, and `silence` fields. Orion currently has no
`state_report` dB or LED calibration, so `db` and `clip` are `null`. Raw 0 is
the top of the observed range, not a CLIP claim. Raw 96 is silence. A missing
sample is unknown.

Calibration is source-specific. The historical `0x75` curve is not used for
the physical `0x73` bank. The route-correlated `0x75` pairs @32/@48 and
@33/@49 have unresolved ownership. They are not aggregate or categorical
lanes.

Offsets 157..160 and 177..178 remain separate provisional output hypotheses.
They do not define the physical-input base. The dated sections below preserve
the earlier research trail and can contain superseded interpretations.

## Correction 2026-09-04: `157+ch` is NOT a fixed preamp-input meter

**The bug:** with `surround_in` (routing dest 14) channels 1/2 patched from
`compplay 1/2` (Computer Play) instead of their original preamp 1/2 default,
the preamp 1/2 meter strips in the UI lit up with the Computer Play signal --
with nothing physically present at the analog preamp 1/2 inputs.

**Root cause found by live test:** re-routed `surround_in` ch1/ch2 to MUTE
while Computer Play kept playing (still audible via headphone/monitor,
routed from `compplay 1/2` independently). State-report bytes 157/158
(`channel_meter_base_offset + 0/1`) dropped to silence (-60 dB) immediately,
proving they track **whatever source is currently patched into `surround_in`
channel N**, not a fixed physical preamp input. The original recapture (see
"Where the real meters are" above) only *happened* to show preamp 1-4
because `surround_in` 1-4 defaulted to preamp 1-4 at capture time -- that
default was never controlled for as a variable.

**Also found:** a second, previously undocumented live meter pair at bytes
**177/178** -- moved in lockstep with 157/158 while `surround_in` 1/2 carried
the Computer Play signal, and *stayed live* after 157/158 were muted (proof
they're a distinct node, not a mirror of 157/158). `headphone_1`,
`headphone_2`, and `monitor_a` were all independently routed from
`compplay 1/2` at the time, so 177/178 is one of those three (or another
node fed by the same source) -- not yet disambiguated. No mirror block
(169-172, 221-224) explains it; those stayed at rest (96) throughout.

**Follow-up 2026-09-05 -- oscillator testing, and a procedural gotcha that
invalidates most of the rapid live-poking above.**

The user pointed out the internal test-tone oscillator (`params.oscillator`,
`SET_GLOBAL 0x0a`; insert into a destination via routing-matrix source bank
`0x0c`) is the right tool here -- a controlled, repeatable signal instead of
relying on real playback content of unknown/changing level. A temporary
`/api/_debug_osc` endpoint was added to `webui/server.py` (raw packed-byte
write) to drive it, then removed again once testing was done -- it never
shipped.

**Procedural bug found first:** `Device.submit()` (`webui/server.py`) queues
writes and returns immediately -- the HTTP response does NOT wait for the
hardware write to actually land. A route write in particular does a
read-modify-write over a query/write round trip (up to ~1.5 s). Several
rapid automated sweeps (insert oscillator into destination N, sleep 1-2.5 s,
poll, move on) were racing this queue: some "no movement" and some
inconsistent same-tone-different-byte results are very likely just reading
stale state before the queued write had actually executed, **not** real
device behaviour. Anything from that period (a claimed 157/158-tracks-
`surround_in` correlation via mute, "compplay to surround 3/4 didn't
reproduce it", 177/178 as a second live node, a "dynamic top-N active
channel slot" theory tested with two simultaneous destinations) should be
treated as **unreliable** -- plausible in the moment, but not verified under
real timing.

**What actually held up** with generous (5 s) settle time between every
single write and the next poll: routing the oscillator into **`mix_ch1`
(routing dest 10) channel 0** lit byte 157 to `18` raw (matching the
configured -18 dBFS tone) with nothing else in the whole 150-235 block
moving. That's the one trustworthy oscillator data point from this session.
It's consistent with -- but does not by itself prove -- the working theory
that `157+ch` tracks per-mix-strip or per-internal-node content rather than
a fixed physical preamp input; it does NOT resolve why the original
per-channel recapture (top of this file) also correlated with preamp 1-4,
nor confirm/deny the `surround_in` correlation the user observed live (that
observation itself is real -- the CP1/2-on-preamp-1/2-meters bug report that
started this thread -- only the *mechanism* explanation attempted afterward
is suspect).

**Where this stands:** `157+ch` is confirmed **not** to be a reliable,
single-purpose "preamp N analog input" meter -- multiple unrelated routing
configurations can make it show non-preamp content. The exact selection
rule (which internal node ends up on which byte, whether it's fixed per
destination or dynamic) is still open, and untangling it further by
API-polling is proving unreliable even for someone being careful about
timing -- a live capture with the OUT + IN endpoints (matching the project's
usual protocol methodology, see PROTOCOL.md) is the more likely way to
actually resolve this. All routing changed during this session (and the
one from the 2026-09-04 entry) was restored to its pre-test state.

## 2026-09-05, step 1: `157+ch` tracks `surround_in` routing (later shown incomplete)

Decisive-looking test, immune to the async-queue timing issue above because
the signal source was a real external tone (mic + 1 kHz), not a queued
device command:

1. `surround_in` ch1/ch2 reset to preamp 1 / preamp 2 (their apparent
   original default).
2. Mic + 1 kHz tone into **preamp 1** physically -> byte **157 = 6** raw
   (-6 dB), matching mirror byte **221 = 5**. Byte 159 (channel 3's slot)
   stayed at the noise floor (~90).
3. Mic moved to **preamp 2** -> byte **158 = 5** raw (-5 dB), matching
   mirror byte **222 = 5**; byte 157/221 fell back to the floor (~76/81,
   decaying).

This was real and reproducible, but turned out to be necessary, not
sufficient -- see step 2 below, which supersedes the "it's `surround_in`
specifically" conclusion.

## 2026-09-05, step 2 -- CONFIRMED: it's a shared dynamic pool, not a fixed per-bus tap

With the mic still live on **preamp 2** (showing at byte 158 via
`surround_in` ch2, untouched), that SAME preamp-2 signal was also routed
into **`mix_ch1` strip 1** (routing dest 10, channel 0) -- a completely
different internal bus, unrelated to `surround_in`. Result: byte **157**
lit up to match (`5`, same as 158), even though `surround_in` ch1 had
nothing routed into it the whole time. Several nearby bytes (159-162,
169-170, 221-226) also picked up partial/attenuated readings at the same
moment. Reverted (`mix_ch1` ch0 back to `surround 1`) immediately after.

**Conclusion:** `channel_meter_base_offset` (157, +169/+221 mirrors) is a
**shared, dynamically-allocated pool of active-signal slots**, not a fixed
tap on any single bus. It is not "the preamp meter" and it is not "the
`surround_in` meter" -- it appears to reflect whichever internal signal
path(s) currently carry audio, drawn from at least `surround_in` and
`mix_ch` strips (untested: `afx_in`, `com_rec`, direct preamp taps, others).
It shows correct preamp levels only when (a) `surround_in` 1-12 defaults
straight-through from preamp 1-12 -- this device's apparent factory
default -- AND (b) nothing else active in the device is competing for the
same slot(s). Both conditions hold by default for a user who never touches
routing, which is why this looked like a clean per-preamp meter for so
long, and why the ORIGINAL bug report (Computer Play on `surround_in` 1/2
showing up as "preamp 1/2" signal) was real. No independent, routing-proof
preamp meter was found anywhere in the 150-235 block during this whole
investigation.

**`com_rec` does NOT feed the pool** (tested 2026-09-05): with preamp 1
already showing live at byte 157 via `surround_in` ch1, also routing that
same preamp 1 into `com_rec` (routing dest 6) channel 4 -- previously
`preamp 5`, at rest -- produced zero change anywhere in the 150-235 block;
byte 161 (that channel's slot) stayed at the same faint residual level as
before. Restored to `preamp 5` after. So the pool is not "anything
patched anywhere" -- `com_rec` (what the DAW sees for recording) is
excluded, which makes sense for a live hardware monitoring meter and rules
out one plausible-sounding but wrong theory.

**Not yet known:**
- The exact allocation rule -- what determines which slot a given active
  bus/channel claims, and what happens when more signals are active than
  there are slots (12, plus 2 mirror copies of the same 12). Every test in
  this session had at most 2 simultaneous signals.
- The full set of buses that feed the pool -- confirmed in: `surround_in`,
  `mix_ch1`. Confirmed NOT in: `com_rec`. Untested: `mix_ch2-4`, `afx_in`,
  ADAT/S-PDIF returns, a possible independent preamp tap.
- Whether this is resolvable at all by further live polling, or needs a
  real USB capture (matching the project's usual methodology, see
  PROTOCOL.md) with several simultaneous, independently-identifiable
  signals to actually map the allocation logic.

**Practical upshot for the webui:**
- As long as nothing unusual is routed, the existing preamp meter strips
  behave as expected for normal tracking use -- most users will never hit
  this.
- Routing anything onto `surround_in`, or feeding a `mix_ch` strip while
  the corresponding preamp is otherwise idle, can make a "preamp N" meter
  show content that has nothing to do with that physical input, with zero
  indication in the UI that this happened. Worth a caveat near the meter
  strips, or at minimum in the routing UI when `surround_in`/`mix_ch` are
  touched.

**Still open from the earlier (unreliable-timing) pass:**
- Identify the 177/178 pair from the 2026-09-04 entry, if it's real at all
  (only observed during the unreliable async-timing period -- not
  reproduced under careful timing since).

## 2026-09-05, step 3 -- historical 177/178 observation (owner unresolved)

Cross-checked against the real Windows Launcher, which changed the picture:

- With `surround_in` 1/2 confirmed on Computer Play (via the Launcher's own
  UI, not this tool), the real Launcher's **Preamp tab meters showed
  nothing** -- clean, routing-isolated, exactly as physical-input meters
  should behave. This directly contradicts treating `157+ch` as "the
  preamp meter" -- whatever it is, it is not what the Launcher's preamp
  strips read.
- Two capture files (`vumetertest.pcapng`, `audioplaying-audiostop-meter.pcapng`,
  both in the sandbox repo root, gitignored) were pulled apart with
  `tshark -Y "usb.data_len==320" -T fields ...` per the project's usual
  capture methodology. Neither contained the `SET_ROUTE` (0x70/0xd3/0x41)
  frame itself (recording started after routing was set up), so the exact
  commanded (bank,idx) can't be read back from these captures -- but the
  live 0x73 state stream is unambiguous on its own.
- In `audioplaying-audiostop-meter.pcapng` (30.8s, clean play-then-stop):
  byte **177/178** track real audio content precisely (raw 7-36 while
  playing) and drop to **exactly 96** (dead silence) the instant playback
  stopped -- the cleanest, most complete on/off transition of any byte in
  the whole 320-byte report. Byte 157 also reacted, but never fully
  recovered (settled around ~90, not 96) -- a messier, less-isolated
  signal than 177/178.
- At the same time, live on the real hardware, the user confirmed the
  Launcher's own **Mixer 1 tab, channel 1 meter** was showing this exact
  signal. Mix 1 has 32 input strips but only a stereo (L/R) MASTER output
  -- a single pair of bytes is exactly what a mix bus's own master meter
  should look like, unlike the 12-byte-per-block shape of 157+ch.

**Owner unresolved:** 177/178 are retained as an observed playback-active
pair, not as Mix 1 L/R or any stereo mapping. In the same playback capture,
meter-only `0x75` @34/@35 reports (byte 1 == `0x1f`) co-varied with
`0x73` @177/@178 within 5 ms (`r≈0.998`); this does not establish ownership.
The pair is distinct from the 157..160 candidate lanes, and neither pair is
claimed as a physical-preamp meter. The capture contained no route-command
frame, so route ownership remains unresolved.

**2026-09-05 addendum -- the "channel 1 went missing" scare was a muted route, not a missing register.** A follow-up capture (`preamp1-2-allouts mute.pcapng`) showed byte 157 completely flat despite the user confirming real signal was on preamp 1, while byte 158 correctly tracked preamp 2 -- looked like channel 1 specifically might be broken or metered somewhere else. Checked live: `surround_in` channels 1-4 were ALL set to MUTE at that point (likely a side effect of the "mute all outputs" test setup also muting `surround_in`'s own input routing, which is a distinct thing from the monitor/headphone/line output buses). Restoring `surround_in` ch1/ch2 to preamp 1/preamp 2 immediately brought signal back on both channels, user-confirmed live. So byte 157 is not missing or wrong for channel 1 -- it behaves exactly like channel 2, tied to `surround_in`'s actual routing, and that routing had simply been muted. An older, unrelated capture (`vumeter-test-ch1.pcapng`, 2026-08-26, predating this whole investigation) independently confirms byte 157 (+mirrors 169/221) cleanly tracking real signal fed only into preamp 1, full range down to 0.

This does NOT resolve the separate, deeper question below (why the real Launcher's Preamp tab stays isolated from `surround_in` repatching) -- it only clears up that 157 itself works consistently and symmetrically for both channels once `surround_in` is actually pointed at the preamp.

**Genuinely unresolved, and now the most important open item:** where is
the TRUE preamp (physical-input) meter that the Launcher's Preamp tab
reads, the one that stayed silent through Computer Play on the real
hardware? Not found in either capture (no real mic/physical signal was
present in either), and not found in the earlier live Linux polling
either (see step 1 above) -- everything found so far has turned out to be
downstream/internal-bus content (surround_in, mix_ch1, now likely Mix 1
master), never a byte proven to be isolated to one physical jack. Finding
it needs a capture or live test with a REAL physical signal (mic/line) on
one preamp while Computer Play or another digital source is ALSO active
elsewhere, scanning the WHOLE 320-byte report for a byte that moves with
the physical signal and stays flat through everything else -- the mirror
image of the tests done so far.

## 2026-09-05, step 4 -- historical reframing (superseded by six-capture bounded review)

The historical reframing below is retained as a hypothesis trail, not a
resolved ownership claim. The 2026-09-01 default-route capture showed
activity at offsets 157/158/159/160 when preamps 1-4 were fed, but that
observation does not distinguish fixed Mix ownership from downstream DSP
activity or physical-input metering. The current bounded review therefore
retains one provisional mono candidate lane per Mix 1..4 label, with low
confidence and no stereo/physical inference. The default strip-routing
context was:

- Mix 1 (routing dest 10) strip 1 defaults from `surround 1`, which
  defaults from `surround_in` ch1, which defaults from preamp 1 -- three
  hops of coincidence, not a direct tap.
- Mix 2 (dest 11) has `preamp 1-8` among its 32 default strip sources
  (slots 16-23), so preamp 2 legitimately reaches it.
- Mix 3 / Mix 4 (dest 12/13) likewise carry preamp content among their many
  default sources.

The earlier observations remain useful activity evidence but do not prove
ownership: `surround_in` and `mix_ch1` routing can light candidate bytes, while
`com_rec` did not in the tested setup. Bytes 161-168 were not confirmed to
move in the examined captures, but that is not proof that they are unused.
The 177/178 playback-active pair remains separate and unresolved. Mirror
relations are documented by the bounded six-capture result above, not by the
historical three-copy wording in this trail.

**Physical-preamp ownership remains unresolved.** The examined HID captures
show candidate DSP activity but do not provide route-independent physical
isolation. This is a USB Audio Class device with a separate isochronous audio
endpoint; the Launcher's Preamp tab may derive levels from PCM, but that is
not established here. No HID candidate in this note should be promoted to a
physical-input meter without a capture that isolates a real input from other
sources.

**Net effect for the webui/profile:** `channel_meter_base_offset` (157) is
retained as the canonical base for the current provisional candidate mapping.
The profile and `PROTOCOL.md` qualify it as one mono lane per current Mix 1..4
label with low ownership confidence; this evidence note does not prescribe a
source-code or upstream-CLI change.

**Capture-specific observation:** with default `surround_in` routing, live
signals on preamps 1 and 2 produced distinct values at 157/158 and the
corresponding 222 lane matched in that capture. This demonstrates activity
under that route, not route-independent physical ownership; first-lane mirror
relationships are not universal.

**Profile status:** `profiles/orion_studio_sc.json` retains
`channel_meter_base_offset` 157 and four provisional mapping entries. Its
notes and the `157-176` / `221-232` unresolved entries now state the
six-capture limits, precise later mirror table, unresolved 177/178 owner, and
strict `0x75` byte-1 filter.
