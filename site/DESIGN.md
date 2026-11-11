# Dashboard design

A research terminal for sceptical readers. The data is the hero: deep black
space, hairline borders, precise charts, and accents that always mean the
same thing. Restraint everywhere except the finding itself.

## Tokens

One file, [`styles/tokens.css`](styles/tokens.css); the site may use nothing
outside it.

| token | value | meaning |
|---|---|---|
| `--bg` | `#05060A` | page |
| `--surface` / `--surface-2` | `#0B0D14` / `#11141D` | cards, nested panels |
| `--border` | `#1C2130` | 1px hairlines, chart gridlines |
| `--text` / `--text-muted` / `--text-faint` | `#F2F4F8` / `#8A93A6` / `#4A5263` | copy hierarchy |
| `--cobalt` / `--cobalt-soft` | `#2F5BFF` / `#6E8BFF` | NEAR-native series, links, focus |
| `--lime` | `#C6FF1A` | supported by the evidence / headline metric |
| `--coral` | `#FF5C7A` | evidence against / REJECTED — equal weight to lime, deliberately |
| `--amber` | `#FFB020` | inconclusive |
| `--glow-*` | `0 0 24px @ 0.3` | the one permitted glow: active chart or selected card, never text |
| `--radius` / `--s1..--s8` | `14px` / 8px grid | shape and rhythm |

Colour is never the only signal: every verdict chip carries its word and a
glyph (✕ ✓ ~), and the heatmap cells carry text labels.

## Type

- **Display** — Space Grotesk 500/700, tight (-0.02em), big headlines that
  state findings in plain words.
- **Body** — Inter 400/600, 17px, 1.6.
- **Mono** — JetBrains Mono for SQL, table ids, axis ticks, window lines and
  verdict chips. All numbers render in tabular figures.

Self-hosted (`fonts/`, OFL), `font-display: swap`, nothing loaded from a
third party.

## Charts

Observable Plot (vendored, pinned). Every chart carries: a title that states
the finding, labelled axes with units, a source line naming the table and the
date filter, a Show SQL toggle, and a Download CSV link. Series colours:
cobalt = NEAR native, lime = cross-chain/headline, coral = against, grey =
context. Gridlines in `--border`. No 3D charts, no dual axes.

The sensitivity heatmap uses three steps — against (coral) / flat (amber) /
with the prediction (lime) — each cell labelled with its percentage and
direction; the pre-registered default cell is outlined.

## Sample

[`design-sample.html`](design-sample.html) renders the hero, the live
scoreboard, one real evidence panel (H1) and the real 27-cell heatmap, all
from `data/metrics.json`. Serve with `python3 -m http.server -d site` or
`make site-preview`.

## Motion

Motion is decoration on top of a page that is complete without it. An inline
script adds `html.motion` only when the reader has not asked for reduced
motion and `IntersectionObserver` exists; every hidden-until-revealed rule is
scoped under that class, so without it each element renders in its final
state.

- **Hero field** — a canvas of dots streaming into a dashed "bot filter"
  line; most turn coral and fall away, a few pass and brighten. It encodes no
  data and draws no numbers. Paused off-screen and in background tabs; one
  still frame under reduced motion.
- **Intro** — headline words rise in sequence; the animations are removed
  once played (`html.settled`) so no composited layer holds the text.
- **Counters** — hero stats count up from a dash to the value in
  `metrics.json` when they enter the viewport.
- **Charts** — lines draw in once on first view (stroke-dash), then areas,
  dots and labels fade in; inline styles are cleared afterwards. Resizes
  re-render without animating. Crosshair tooltips on every series.
- **Sections** — fade-and-rise reveal; cards, heatmap cells and timeline
  items stagger. Scoreboard cards tilt and carry a cursor spotlight on
  fine pointers only.
- **Chrome** — scroll progress bar, scroll-spy nav, back-to-top, and a
  bull/base/bear focus switcher.
