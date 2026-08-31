# Mission 6A — Trainer's Guide Rewrite, Timer, Bite Animation Tuning

Mission 6 (Doghouse Animation, Trainer's Guide, and Release QA) split in two. This is the
content/timing half: guide content + countdown + bite-animation timing/sizing. Final release QA
is a separate follow-up mission.

## What changed (all in `watchdog_ui.py`)

### 1. `COUNTDOWN_SECONDS`

```python
COUNTDOWN_SECONDS = 30
```

`15` → `30` (was `COUNTDOWN_SECONDS = 15`). The visible countdown itself, `_tick`, and all
timer-expiration wiring are unchanged.

### 2. Bite animation timing/size

```python
def animate_eaten(win, on_done, bites=5, bite_delay_ms=160):
```

- `bites=7` → `5`, `bite_delay_ms=150` → `160`: 5 × 160 ms = **800 ms** total, the ~0.8 s target.

```python
bite_r = max(14, h // 3)
```

- `bite_r = max(10, h // 4)` → `max(14, h // 3)`: a third of the window height instead of a
  quarter, and a larger 14 px floor — more visible, more obvious bites.

### Untouched (wiring confirmed identical)

- `hide()`, `_close_now`, `_tick` — the call sites that route every trigger point into
  `animate_eaten` are byte-for-byte unchanged; only the default parameter values above changed.
- The restore-region line `_user32.SetWindowRgn(hwnd, None, True)` and the failure-fallback
  paths (`_user32 is None or _gdi32 is None` → `on_done()`; outer `except Exception: on_done()`)
  are untouched.
- `animate_eaten`'s signature and call sites are unchanged.

### 3. `GUIDE_TEXT` rewrite

Full new text, with section headers:

```
Built by Black Anvil

WHAT THIS APP DOES
Process Watchdog is a hungry dog that eats leftover background
processes for you. You pick one app it keeps its eye on, plus any
helper processes that should go away when that app closes. LET THE
DOG EAT!!!

ONE WATCHED APP + THE MEAL LIST
Every Watchdog watches exactly one app, which is always on its own
meal list automatically — you cannot remove it. On top of that you
can add unlimited 'leftover' meal targets: pick a running process
from the list, browse to an offline .exe file, or just type a
filename. Add as many as you like.

GRACE PERIOD (GLOBAL)
When the watched app's window closes, Watchdog waits a grace period
before eating anything, and cancels if the app reopens in time.
There is ONE grace-period setting for every Watchdog — default 10
seconds, adjustable — not a separate setting per dog.

THE DOGHOUSE
Closing the window (the X, or Hide Dogs in the Doghouse) keeps
every Watchdog running in the background. Right-click the tray icon
to reopen, or use the tray Quit to actually exit and starve your
dogs. Only tray Quit truly stops them.

CALL DOG OFF WATCH / PUT DOG ON WATCH
This toggle turns a single Watchdog on or off. Off means it stops
watching and never eats anything; on means it watches again. The
button flips between the two.

RETRAIN / REHOME
Select a Watchdog first. Retrain lets you edit it (change the
watched app or its meal list, fix an ambiguous one). Rehome Dog
deletes it for good, after an on-screen confirmation. Each has its
own confirm text, so this guide won't recite it.

EXACT MATCH VS. NAME MATCH
When the app's exact install location is known, Watchdog matches by
that path — so two different apps that share a filename are never
mixed up. When no path is known, name-only matching is the fallback,
and the picker clearly labels those entries as such.

PROTECTED PROCESSES
Watchdog will never target itself, core Windows system processes, or
anything owned by SYSTEM or a service account — no matter what you
select. The safe ones stay safe.
```

The guide now describes the app as it works today: one watched app + unlimited meal targets,
automatic watched-app inclusion, the single global grace period, doghouse/tray behavior, dynamic
toggling, Retrain/Rehome, exact-path vs. name-only matching, and protected-process exclusion.
Same playful-dog tone as before ("LET THE DOG EAT!!!" retained), no corporate or childish prose,
no profanity, no emoji. The guide's layout/widgets (logo, heading, Text widget, Close button)
are unchanged.

## Validation

- `python -c "import ast;ast.parse(open('watchdog_ui.py',encoding='utf-8').read());print('UI OK')"` → UI OK
- `python -c "import watchdog_ui;print('IMPORT OK')"` → IMPORT OK
- `python -m unittest discover -s tests -t . -v` → Ran 87 tests, OK (Mission 5-FIX added one;
  the 86 baseline + 1)
- `git diff -- watchdog_ui.py` — shown in full below.

## What did NOT change

No wiring changes: `hide()`, `_close_now`, `_tick`'s `animate_eaten` call are otherwise
identical. `watchdog_core.py` and every other file were not touched. No button label, status
string, or dog-language from Mission 4 was changed. `build.bat` was not run (deferred to release
QA).
