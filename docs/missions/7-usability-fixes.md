# Mission 7 — Usability Defects Found By The Repository Owner

Five independently confirmed usability/UX defects found by actually using the packaged app
after the punch board was closed. All five fixed; all five covered by geometric/rendered
assertions (not "does it raise"). Result: PASS.

Before Mission 7: 99 tests. After Mission 7: 114 tests (99 unchanged and green + 15 new).

## Defect A — Train/Retrain Save/Cancel unreachable (dialog overflow)

Root cause: fixed `520x760` geometry, no scroll container, and the button row packed LAST.
At the owner's font/DPI the content height exceeded 760px, pushing Save/Cancel outside the
window (confirmed from the owner's screenshot: the leftovers list ended flush with the
window bottom, no buttons).

Fix (`watchdog_ui.py`, `watchdogDialog.__init__`):
1. The Save/Cancel row is now packed FIRST with `side="bottom"` — pack reserves
   bottom-anchored space in packing order, so the buttons always have room.
2. Everything between the header and the buttons (name field, Watch This App, Eat These
   Leftovers, filter/add rows, note) now lives in a scrollable container: `Canvas` +
   vertical `Scrollbar` + inner `Frame` (with `scrollregion` tracking, width-sync, and
   MouseWheel scrolling).
3. `minsize` raised to `(480, 500)`. Button reachability does NOT depend on window size.

Geometric test (`tests/test_usability.py::DialogButtonsReachableTests`): Save and Cancel
must lie entirely inside the dialog's visible bounds at BOTH the default size and a forced
`460x500` size, asserted via `winfo_rooty() + winfo_height()` against the dialog bounds.
Additionally `test_dialog_minsize_is_generous_floor` pins the new minsize.

Rendered evidence (real desktop session, PrintWindow capture
`docs/missions/7-usability-assets/train_dialog_default.png`, 536x799 incl. frame):

```
Save rect in capture:   (485, 757, 520, 783)   window height 799 -> fully inside
Cancel rect in capture: (432, 757, 479, 783)   fully inside
PASS save_button_rendered_distinct | unique_colors_in_save_rect=15
```

The Save/Cancel row is visibly the bottom-most content, above nothing, inside the frame.

## Defect B — Main window button row overflow (buttons clipped)

Root cause: six multi-word buttons in ONE horizontal row at 500px width; the right side
("Hide Dogs in the Doghou—", Trainer's Guide) was clipped with no indication anything was
missing (confirmed from the owner's screenshot).

Fix: `ConfigWindow` geometry `500x460` -> `640x480`; the button area is split into TWO rows —
a management row (Add Watchdog, Retrain, dynamic toggle, Rehome Dog) and a window row
(Hide Dogs in the Doghouse, Trainer's Guide). The split, not the width, is the guarantee.

Geometric test (`tests/test_usability.py::MainWindowButtonsVisibleTests`): after rendering,
EVERY button's `winfo_rootx() + winfo_width()` and `winfo_rooty() + winfo_height()` must be
inside the window's visible bounds, and all expected labels must exist.

Rendered evidence (`docs/missions/7-usability-assets/main_window_640x480.png`, 656x519
incl. frame; packaged exe separately captured as `packaged_main_window.png`):

```
main window buttons: ['Add Watchdog', 'Hide Dogs in the Doghouse', 'Put Dog on Watch',
                      'Rehome Dog', 'Retrain', "Trainer's Guide"]
PASS all_main_buttons_inside
PASS main_window_is_640x480 | client=640x480
packaged child classes: {'TkChild': 7, 'Button': 6, 'Static': 6}  (7th TkChild = new second row)
```

Visual description: management buttons line the left of the first row below the table;
"Trainer's Guide" and "Hide Dogs in the Doghouse" sit fully visible on their own second
row, right-aligned, nothing cut by the window edge.

## Defect C — No status for `watched_app: null` Watchdogs

Root cause: Mission 2's migration correctly preserved `watched_app: null` for ambiguous
legacy configs (the owner's real config has four such Watchdogs), but `_tick_status` had no
branch for it — those dogs showed the same "Waiting for app to open." as healthy idle ones.

Fix: in `_tick_status`, a `watched_app is None` check is the FIRST status branch, ahead of
disabled/pending/open, displaying `"Needs setup — pick a Watch app in Retrain."`. No other
branch's logic or wording changed; no data migration (the owner fixes theirs via Retrain,
now reachable again).

Tests (`NeedsSetupStatusTests`, mocked watcher, real ConfigWindow): the new status renders
for `watched_app: None` alone and takes precedence over disabled, pending, and open states;
a companion test pins the other statuses ("Off watch.", "Hungry — eating in 4s.", "Waiting
for app to open.") as unchanged. Rendered evidence: the live table showed
`row=['Legacy Dog (needs setup)', 'Yes', 'Needs setup — pick a Watch app in Retrain.']`
in the screenshot capture run.

## Defect D — Spinbox digits invisible in dark theme

Root cause: `apply_theme`'s type-dispatch had no `Spinbox` branch, so the generic recursion
pass darkened its background while its foreground stayed Tk's default black — black digits
on near-black. Confirmed precisely.

Fix: `elif cls == "Spinbox":` added, mirroring the `Entry` branch exactly.

Tests (`SpinboxThemeTests`): rendered Spinbox `fg` equals the palette fg for BOTH light and
dark palettes, plus an exact-mirror test proving Spinbox and Entry end up with identical
fg AND bg under both palettes (the recursion's generic pass overrides `entry_bg` to the
window bg for BOTH types — pre-existing behavior, unchanged by this mission; the defect was
the missing explicit fg). Observed: dark fg `#FFFFFF`, light fg `#000000`.

## Defect E — Opaque MSIX group labels in the process picker

Root cause: `get_process_groups` labeled multi-exe groups by install-directory basename;
MSIX/Store installs share opaque per-installation hash directories (the owner's own config:
Claude and ChatGPT under `C:\Program Files\WindowsApps\<PackageName>_<version>_<arch>__<hash>\`),
so groups displayed as raw hashes (e.g. `b99306303521e97e`).

Fix: multi-exe group labels are now the SHORTEST exe filename in the group (case-insensitive
length comparison, ties broken alphabetically). Grouping logic itself unchanged.

Tests (`GroupLabelTests`, mocked `psutil.process_iter`): a two-exe MSIX-hash directory
labels as `ChatGPT.exe` (not the hash); Visual Studio's pair labels as `devenv.exe`; an
equal-length tie resolves alphabetically.

## Validation

```
python -c "...ast.parse watchdog_core..."  -> CORE OK
python -c "...ast.parse watchdog_ui..."    -> UI OK
python -c "import watchdog_core, watchdog_ui, watchdog_app" -> IMPORT OK
python -m unittest discover -s tests -t . -v -> Ran 114 tests ... OK
```

## Screenshots (committed under `docs/missions/7-usability-assets/`)

- `main_window_640x480.png` — source-rendered main window, real desktop session, 656x519
  incl. frame; two button rows fully visible; status column showing the new
  "Needs setup — pick a Watch app in Retrain." for a `watched_app: null` dog.
- `train_dialog_default.png` — Train dialog at default size, 536x799 incl. frame; Save and
  Cancel fully visible at the bottom (pixel-verified rects above); scrollbar present.
- `packaged_main_window.png` — the freshly BUILT `dist\ProcessWatchdog.exe`, first-run
  window on a fresh temp profile: 656x519, 6 Buttons across two rows (7 TkChild frames —
  the second row's Frame), PrintWindow capture; instances closed afterwards.

## Remaining

None from this mission. The pre-existing `Watcher._stop` shadowing quirk noted in Mission 6H
remains a future cleanup candidate (out of scope here).
