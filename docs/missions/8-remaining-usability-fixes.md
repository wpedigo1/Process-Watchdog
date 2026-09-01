# Mission 8 — Guide Text Contrast, Spinbox Arrows, Button Grouping

Three usability defects found by the repository owner using the Mission 7 build. All fixed
in `watchdog_ui.py` with rendered-pixel verification. Result: PASS.

Before Mission 8: 114 tests. After: 120 tests (114 unchanged and green + 6 new).

## Defect F — Trainer's Guide text unreadable

Same root cause as Mission 7's Spinbox bug, different widget: `tk.Text` (the guide body)
was never in `apply_theme`'s type-dispatch, so the generic recursion pass darkened its
background while its foreground stayed Tk's default black.

Fix: `elif cls == "Text":` branch setting `bg=entry_bg, fg=fg, insertbackground=fg`.

Tests (`TextThemeTests`): rendered `Text` fg equals the palette fg for dark AND light
palettes; `insertbackground` matches fg. Rendered evidence: the real Trainer's Guide
capture shows the text widget with `fg #FFFFFF` on the dark theme, and the pixel scan of
the text area found 625 light (text) pixels against 18,658 dark (background) pixels.

## Defect G — Spinbox arrows still invisible

Mission 7 set `bg`/`fg`/`insertbackground` but not `buttonbackground` — the separate Tk
option controlling the increment/decrement arrow area.

Fix: `buttonbackground=palette["entry_bg"]` added to the existing Spinbox branch.

Tests (`SpinboxButtonBackgroundTests`): `buttonbackground` equals `entry_bg` for both
palettes. Screenshot evidence (as the brief warned, config value alone is not proof):
`grace_spinbox_closeup.png` (3x zoom of the real rendered spinbox). Pixel scan of the
rendered spinbox rect found 69 unique colors; the 17px arrow strip alone contains 12,
including the arrow glyphs (0,0,0 / 9,9,10) rendered against the #2D2D30
buttonbackground — the arrows are visibly distinct from the near-black window background
(#202020). Honest note: the arrows still draw in Tk's own glyph style (dark on the
entry_bg strip), not user-selectable colors; they now contrast against their strip and the
strip contrasts against the window.

## Defect H — Two-row button split reads as arbitrary

Mission 7's split fixed the clipping but read as overflow, not intent.

Fix: a 1px horizontal separator `tk.Frame` between the management row and the
whole-window row, colored by a new tiny `_blend(bg, fg, 0.25)` helper (#585858 in dark,
#B6B6B6 in light) and explicitly recolored AFTER `apply_theme` in both `__init__` and
`show()` (which would otherwise repaint every Frame to the window background). Chose a
separator over section labels: it marks the boundary without adding text clutter, and the
row contents themselves (dog actions left, window actions right) now read as two groups.

Tests (`ButtonRowSeparatorTests`): separator exists, height 1, bg distinct from the
window bg and equal to the blend value; geometrically positioned BETWEEN the rows
(below `Rehome Dog`, above `Trainer's Guide`); `_blend` pinned by direct assertions.

Screenshot evidence (`button_area_two_sections.png`, a full-width crop of both rows plus
separator): captured separator row is a solid distinct gray line (sampled (77,77,77) —
the config value is #585858; the capture shows a slightly darker rendition of the same
line, still clearly distinct from the #202020 background). Visual read: management
buttons (Add Watchdog / Retrain / toggle / Rehome Dog) on the left of the first row; a
thin divider; "Trainer's Guide" and "Hide Dogs in the Doghouse" right-aligned below it.
In my judgment this now reads as two deliberate sections rather than overflow — the
divider plus the right-alignment of the second row does the work.

## Screenshots (committed under `docs/missions/8-remaining-usability-assets/`)

- `trainers_guide_readable.png` — Trainer's Guide, real desktop session, light-on-dark
  text verified by pixel counts above.
- `grace_spinbox_closeup.png` — 3x zoom of the grace-period Spinbox with arrow strip.
- `main_window_two_sections.png` — full main window.
- `button_area_two_sections.png` — crop of the button area showing the separator.

## Validation

```
python -m unittest discover -s tests -t . -v -> Ran 120 tests ... OK
```

## Remaining

None from this mission. The picker redesign is Mission 9, explicitly out of scope here.
