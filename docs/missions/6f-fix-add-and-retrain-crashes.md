# Mission 6F — Fix Add and Retrain Crashes

Result: PASS.

## Root causes and fixes

The Mission 5 dialog header read `watchdog.get(...)` before `watchdog=None` was normalized to
an empty dictionary. Add Watchdog therefore crashed during every dialog construction. The
normalization now runs immediately after geometry and icon setup, before the logo/header or any
other access to `watchdog`. The existing heading logic is unchanged.

The Mission 2 locked meal row passed `disabled=True` to `ttk.Treeview.item()`, but Treeview has
no per-item `-disabled` option. Every refresh with a watched app raised `TclError` after clearing
the tree. The row now uses a `locked` tag configured with a gray foreground.

## Meal-target data loss

Real-Tk coverage confirms that a manually added meal target remains selected and is returned by
`get_selected()` after the picker has a locked watched-app row. The locked row is not recorded in
`_leaf_ident`, so technical selection of that display-only row cannot add it to meal targets;
`watchdogDialog._save` also retains its existing watched-app exclusion/deduplication.

## Tests

Before Mission 6F: 94 tests. After Mission 6F: 98 tests.

The four added tests instantiate real Tk widgets in the Windows desktop session. They cover Add
construction with `watchdog=None`, named Retrain construction, locked-row refresh, and preservation
of a manually added meal target while locked mode is active. Process enumeration is patched to an
empty result for deterministic, non-destructive widget tests; Tk and ttk widgets are not mocked.

Validation observed `UI OK`, `IMPORT OK`, and `Ran 98 tests ... OK`.

## Remaining

Mission 6D defect 1 (picker parent-pid display, referred to as defect #4 in the Mission 6F brief)
remains open. The full Mission 6D release-QA pass must be rerun, so no final acceptance gate is
declared met.
