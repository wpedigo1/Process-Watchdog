# Mission 5 — System Theme, Accent Color, Logo, Layout

## What changed

**`watchdog_core.py`** — two new read-only, fail-safe detection functions (nothing
else touched):
- `detect_windows_theme()` — reads `AppsUseLightTheme` (DWORD 1=light, 0=dark) from
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`. Missing
  key/value → light (the Windows default), never raises.
- `get_accent_color()` — reads `AccentColor` (DWORD) from
  `HKCU\Software\Microsoft\Windows\DWM`, stored as `0xAABBGGRR`. Extracted with bit
  masks (`(v>>0)&0xFF`=R, `(v>>8)&0xFF`=G, `(v>>16)&0xFF`=B). Any failure → `"#0078D4"`.
- `_read_reg_dword(key, name, default)` — common wrapper; returns `default` on any
  failure (non-Windows, missing key/value, wrong type, exception). Never raises.

**`watchdog_ui.py`**:
- `_PALETTES` — two entries: light `bg #F3F3F3 / fg #000000 / entry_bg #FFFFFF`,
  dark `bg #202020 / fg #FFFFFF / entry_bg #2D2D30`.
- `_build_palette()` — picks the palette by theme and injects `accent = get_accent_color()`.
- `apply_theme(widget, palette)` — one recursive plain-tk color pass over
  `winfo_children()` (Button, Label, Frame, Toplevel, Entry), plus `ttk.Style`
  `configure`/`map` for `Treeview` (selection background = accent). Unknown widget
  types are left alone; no widget types are changed.
- `load_logo_img(pixels)` — `PIL.Image.open(resource_path("icon.ico")).resize((N,N))`
  → `ImageTk.PhotoImage`. Reuses existing `resource_path` (source vs. `_MEIPASS`).
- Logos and layout (below).
- `ConfigWindow.refresh_tree()` now calls `_update_pack_status()` to recompute the
  "{enabled} of {total} watchdogs on watch" line.

## Theme-apply call sites (criterion 3)

Each window runs detection + apply once after its widgets are built:

- `watchdogDialog.__init__`:
  ```python
  self._palette = _build_palette()
  apply_theme(self, self._palette)
  ```
- `UserGuideWindow.__init__`:
  ```python
  self._palette = _build_palette()
  apply_theme(self, self._palette)
  ```
- `RehomeDialog.__init__`:
  ```python
  self._palette = _build_palette()
  apply_theme(self, self._palette)
  ```
- `ConfigWindow.__init__`:
  ```python
  self._palette = _build_palette()
  apply_theme(self.root, self._palette)
  ```

## Theme recheck on leaving the doghouse (criterion 4)

`ConfigWindow.show()` re-runs detection/apply each time the window is shown from the
tray (one-shot tied to an existing UI event; no polling, no watcher):

```python
def show(self):
    self._palette = _build_palette()
    apply_theme(self.root, self._palette)
    self.root.deiconify()
    self.root.lift()
    self.refresh_tree()
```

This replaced the old body (`deiconify()` + `lift()`); the stale duplicate `show()`
near the end of `ConfigWindow` was removed.

## Logo PhotoImage references (criterion 5)

Each window keeps its `PhotoImage` as an instance attribute so Tkinter does not GC it:

- `ConfigWindow`: `self._logo_img = load_logo_img(48)`
- `watchdogDialog`: `self._logo_img = load_logo_img(40)`
- `UserGuideWindow`: `self._logo_img = load_logo_img(32)`

## Layout

- `ConfigWindow` header row: 48×48 logo upper-left + `APP_NAME` beside it.
- One pack-status line below the header: `f"{enabled} of {total} watchdogs on
  watch"`, recomputed in `refresh_tree` (no separate polling path).
- Existing button row grouping and geometry/minsize preserved (layout pass only, no
  redesign, no removed/reordered functionality).

## Tests

Added `tests/test_theme_accent.py` (8 tests): theme 1→light, 0→dark, missing→light
default, accent byte-order decode (`0x00FF8000`→`#0080FF`, `0xAABBCCDD`→`#DDCCBB`),
missing accent→`#0078D4`, `_read_reg_dword` never raises when winreg fails, and
non-Windows returns default. Pure functions covered; widget theming left to source
inspection per this codebase's no-automated-widget-test precedent.

## Before / after test counts

- Before: **78** tests (given base; re-ran and confirmed passing before edits).
- After: **86** tests — all pass (`Ran 86 tests ... OK`).

## Manual-visual / inspection-pending items (not claimed verified)

- Rendered contrast in light and dark modes, logo scaling, accent restraint, and
  control clipping at display-scaling settings were confirmed by source inspection
  and color-value review only. They require running the app / structure-rendering to
  verify visually.
