# Orion modulation capture and panels

The owner-labelled `antelope-orion-afx-modulation-tab.pcapng` and accompanying
explanation establish V12 Chorus and demo BBD-Chorus parameter observations.
Analysis date: 2026-10-02. Capture SHA-256:
`4aae1e81def915a851287d62ae77d05e092e471c18ac9608f5890a3bae25d21c`.
Raw captures remain in the ignored archive. These are captured write facts,
not verified runtime parameter contracts.

| Effect | Field / display label | Absolute HID offset | Observed raw range | Source frames |
| --- | --- | --- | --- | --- |
| V12, type70 | humanize / Humanize | 20 | 0=Off, 1=On | 96657, 98883 |
| V12 | voices / Voices | 21 | 1–12 | 39951–42061 |
| V12 | delay / Delay | 22 | 1–100 | 43075–47137 |
| V12 | depth / Detune | 23 | 0–100 | 47899–53453 |
| V12 | color / Colorize | 24 | 0–100 | 76705–76979, 84549–84659 |
| V12 | colorShifter / Clr Shifter | 25 | 0–255, unsigned | 79863–84041 |
| V12 | space / Space | 26 | 0–100 | 68745–75539, 85777–85883 |
| V12 | feedback / Feedback | 27 | 0–100 | 54211–57947 |
| V12 | pan / Pan | 29 | 0–180, centre90 | 86595–92303 |
| V12 | mix / Dry/Wet | 30 | 0–100 | 92861–95793 |
| V12 | gain / Gain | 31 | 0–255, unsigned | 58959–64553 |
| BBD, type78 | level / Level Control | 20 | 0–100 | 210447–215783 |
| BBD | intensity / Chorus Intensity | 21 | 0–100 | 216443–221735 |
| BBD | rate / Vibrato Rate | 22 | 0–100 | 224185–224403, 228819–229529 |
| BBD | depth / Vibrato Depth | 23 | 0–100 | 222393–222667, 227191–228009, 230593–232091 |
| BBD | chvibrato / Chorus-Vibrato | 24 | 0=Vibrato, 1=Chorus | 190895, 191805, 225671 |

V12 uses length`0x20`, selector`0xd5`, explicit data length`0x0e`; BBD uses
length`0x1c`, selector`0xd5`, explicit data length`0x0a`. Both address type at18,
instance at19 and send a complete block at20 onwards. V12 byte28 (`presetIndex`)
stays0; BBD bytes25/26/27 (`type`, `bypass`, `peakmeter`) stay0/0/96.
Preserve these opaque bytes. Constant values are not defaults, measured preset
indices, stereo-mode polarity, bypass semantics or meter scales.

V12 Gain and Clr Shifter sweep continuously through127 up to255; signed int8
would corrupt their values. Physical scales remain unknown. The owner's Pan
display is −90..+90 around0, corresponding to raw0/90/180. The owner reports
Colorize and Clr Shifter unlock after increasing Space; this is presentation
behavior, not a claim about device enforcement.

The capture contains 490 V12 writes (245 right1→left0 mirrored pairs) and170
BBD writes (85 pairs), each identical block apart from instance addressing and
within20ms. Host mirroring does not establish audible operation or verified
restoration. V12 initial voices4 ends1; BBD first/last blocks match without a
fresh readback. There are no tagged queries or parameter replies in this capture.
Selector`0x98` bypass gestures send1 then0 milliseconds apart: V12 frames
99971/99977,101121/101125; BBD232899–232913,234191–234203. Isolated enable
polarity remains unverified. Owner-labelled demo access does not imply ownership.

The WebUI has separate V12 and BBD panel modules and shared gesture primitives.
Local preview exposes labelled knobs and switches without device writes. Loaded
V12/BBD slots now show their panel with unknown values and disabled parameter/
power controls. Existing captured load/move/remove and link behavior is retained.
No new tagged query, writer, instance capacity or classic getter bound is enabled.
Fresh state replies and bounded write/read/restore evidence are still required.

The layouts follow [V12's public panel](https://en.antelopeaudio.com/products/v12-chorus/)
and [BBD's public panel](https://en.antelopeaudio.com/products/bbd-chorus/): two
rows of five V12 knobs, and four BBD knobs with stereo/modulation switches.
Artwork is original; no vendor assets or implementation are copied. Knob bodies
and rings stay still, pointers turn, and native range inputs provide keyboard
access without visible sliders. Unknown effect meter state stays unknown.

Gazelle [profiles PR21](https://github.com/Gazelle-ctl/gazelle-device-profiles/pull/21)
uses the same identifiers, raw ranges, polarity and display grouping for every
Synergy Core profile. Each repository keeps its own runtime contract and
independently authored implementation. Shared definitions are discoverable on
all models; Orion capture evidence does not confirm another model's writes.
