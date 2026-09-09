# webui/assets

Source art that is **actually wired into the UI** (`static/index.html`).
Distinct from `../ideas/`, which is the scratch / exploration dump.

Most art is inlined into `index.html`; the mixer fader art is the exception.
`server.py` serves `assets/` at `/webui/assets/` so the full fader shadow can
remain as a source SVG. Editing an asset still requires checking the UI against
the changed source.

## Preamp knob

| file | used for |
|------|----------|
| `PreampUI.svg` | full preamp-strip mockup -- layout reference |
| `preamp-knob.svg` | preamp gain knob shapes -- bezel / body / pointer / cap (lifted into `.knob` inline SVG; bezel is a translucent white ring) |
| `PreampUI-KNOB-level.svg` | 270 deg level ring + white fill arc round the preamp knob |

## Monitor A / B knob

| file | |
|------|--|
| `mon-knob-lit.svg` | **in use.** Pure-SVG glossy knob, ~2 KB, scalable. Offset radial gradient + edge vignette for the dome, `feSpecularLighting` filter for the hotspot. Inlined into `index.html` by `monKnobSVG()` (ids namespaced per instance). `<g data-rot>` = the rotating indicator. Tune via the `fePointLight x/y/z` and the filter's `surfaceScale` / `specularConstant` / `specularExponent` / `stdDeviation`. |
| `mon-knob.svg` / `mon-knob-dot.svg` | earlier photoreal masters (Inkscape). The face is a **mesh gradient** -> exports as 456 quad paths + ~450 gradient refs = ~490 KB. Superseded by `mon-knob-lit.svg`; kept for reference. |

## Virtual mixer

| file | used for |
|------|----------|
| `fader-shadow.svg` | compact vertical mixer fader well, shown behind the moving thumb in the Mix 1–4 tabs |

## History

`../ideas/vol-knob.svg` was the first monitor-knob art (photoreal, dot baked
in). It got split into `mon-knob.svg` + `mon-knob-dot.svg` here because a
baked-in shine that rotates with the knob looks fake. A hand-built
low-shape-count knob (`vol-knob-lite.svg`) was tried in between and dropped --
see git history if it's ever wanted back.
