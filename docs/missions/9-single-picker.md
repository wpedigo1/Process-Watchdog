# Mission 9 — Collapse Watch/Leftovers Into One Picker

Product-design change requested by the repository owner: the two-list design (Watch This
App + Eat These Leftovers, both browsing the same process pool) was redundant. Result: PASS.

Before Mission 9: 120 tests. After: 124 tests (120 unchanged and green + 4 new; two
obsolete `set_locked` tests replaced).

## What changed (`watchdog_ui.py` only; schema and core untouched)

- `watchdogDialog` now has ONE `ProcessPicker` (`selectmode="extended"`), prefilled on
  Retrain with the saved watched app plus all meal targets.
- Below it, a read-only `ttk.Combobox` labeled "Closes and triggers cleanup:" names which
  selected item triggers cleanup. Its values repopulate on every selection change
  (`<<TreeviewSelect>>`, plus an explicit notification after programmatic refreshes, which
  Tk does not emit on its own). If the current choice is still selected it is kept;
  otherwise the previously-saved watched name is restored; otherwise the first selected
  name. Empty selection disables the combobox.
- `_save` reads the selection once; the combobox's name picks the watched app (error
  "Pick which selected app should trigger cleanup." if it matches nothing); everything
  else becomes `meal_targets` via the existing `_dedupe`. Empty selection keeps the
  existing "Pick an app to watch first." error verbatim.
- Removed dead code: `ProcessPicker.set_locked`, the `_locked` state, the locked-row
  rendering and its tag styling, the dialog's second picker and its Browse/Add-filename
  row, `_watch_changed`, `_browse_watch_exe`, `_add_watch_manual`, and the now-unused
  `existing_app_ident`. (The `selectmode == "browse"` special case inside
  `ProcessPicker.add_manual` was left alone: unused but out of this mission's stated
  removal scope.) Verified nothing else referenced any of it before removal.
- Mission 3's protection checks (`_guard_protected`) apply unchanged to the single list.

## Why a combobox instead of click-order tracking

Click-order tracking would require accumulating `<<TreeviewSelect>>` deltas to reconstruct
selection order — fragile across Ctrl-click deselects, group selections, refreshes, and
programmatic selection changes, and hard to test deterministically. A combobox makes the
designation explicit, visible, directly editable, and trivially assertable; it also gives
the user a place to see and change the trigger app without re-clicking.

## Subtlety found while implementing

`Treeview.selection_set`/`selection_remove` do not emit `<<TreeviewSelect>>` in Tk 8.6, so
the picker now notifies its `on_select` after programmatic refreshes change the selection.
The picker's constructor refresh deliberately does NOT notify (the callback is installed
after that first refresh) so the notification can't fire into a half-built dialog — found
via a real teardown traceback in the first test run, not by inspection.

## Tests

`tests/test_watchdog_dialog_init.py` rewritten: the two `set_locked` tests (testing
removed code) are gone; a Retrain prefill test verifies the saved selection and watch
designation; five new combobox tests cover the required behaviors:

1. Three selected items populate the combobox with those three names (current choice kept
   while still valid, per spec).
2. Changing the combobox changes which item becomes `watched_app` on save; the other two
   become `meal_targets`.
3. Deselecting the designated item falls back to the first remaining selected name.
4. Save with nothing selected shows the existing "Pick an app to watch first." error.
5. Save with a selection but no valid designation shows the new designation error.

Full suite: `Ran 124 tests ... OK`.

## Screenshot

`docs/missions/9-single-picker-assets/single_picker_dialog.png` (536x799, real desktop
session): the dialog with three items added and selected, the single list showing all
three (selection highlighted — 337 accent-colored pixels measured in the list area), and
the combobox below the list reading "ChatGPT.exe" with the label "Closes and triggers
cleanup:". Geometric checks from the capture run: combobox inside the dialog at
y=515 (490x21), Save button bottom at 783 within the 799px frame.
