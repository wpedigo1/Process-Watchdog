import unittest
from unittest.mock import patch

import watchdog_core as watchdog_app


def _make_watchdog(enabled=True, watched_app=True, meal_targets=None, wd_id="wd1", name="WD"):
    if meal_targets is None:
        meal_targets = [{"name": "app.exe", "exe": ""}]
    return {
        "id": wd_id,
        "name": name,
        "enabled": enabled,
        "watched_app": {"name": "app.exe", "exe": ""} if watched_app else None,
        "meal_targets": meal_targets,
    }


class WatcherLoopTests(unittest.TestCase):
    def _drive(self, script, enabled=True, grace=10.0, poll=1.0, max_iter=None, watchdog=None):
        """Runs Watcher.run() deterministically.

        open_trigger_names returns script[i] on iteration i, the fake clock
        advances 15s per iteration (enough to clear the 10s grace), and the
        fake sleep stops the watcher after max_iter iterations.
        """
        if watchdog is None:
            watchdog = _make_watchdog(enabled=enabled)
        cfg = {"poll_interval": poll, "grace_seconds": grace, "watchdogs": [watchdog]}
        watcher = watchdog_app.Watcher(get_config=lambda: cfg)
        max_iter = max_iter if max_iter is not None else len(script)
        state = {"iter": 0, "t": 1000.0}

        def fake_open(trigger):
            if not trigger:
                return []
            i = min(state["iter"], len(script) - 1)
            return script[i]

        def fake_sleep(_secs):
            state["iter"] += 1
            state["t"] += 15.0
            if state["iter"] >= max_iter:
                watcher.stop()

        def fake_time():
            return state["t"]

        with patch.object(watchdog_app, "open_trigger_names", side_effect=fake_open), \
             patch.object(watchdog_app, "kill_processes",
                          return_value=watchdog_app.KillResult([], [])) as mock_kill, \
             patch.object(watchdog_app.time, "sleep", side_effect=fake_sleep), \
             patch.object(watchdog_app.time, "time", side_effect=fake_time):
            watcher.run()
        return watcher, mock_kill

    def test_start_closed_does_not_kill(self):
        watcher, mock_kill = self._drive([[], []], max_iter=2)
        mock_kill.assert_not_called()

    def test_open_then_closed_then_grace_elapses_kills_once(self):
        watcher, mock_kill = self._drive(
            [["app.exe"], [], [], []], max_iter=4
        )
        mock_kill.assert_called_once_with([{"name": "app.exe", "exe": ""}], detail=True)

    def test_kill_called_with_detail_true(self):
        # Criterion 6: Watcher.run calls kill_processes with detail=True.
        watcher, mock_kill = self._drive(
            [["app.exe"], [], [], []], max_iter=4
        )
        mock_kill.assert_called_once()
        _args, kwargs = mock_kill.call_args
        self.assertTrue(kwargs.get("detail", False))

    def test_on_kill_fires_even_with_nothing_found(self):
        # Criterion 6: on_kill fires even when nothing was found to eat (zero
        # results), not just on a nonzero count. kill_processes returns an
        # empty KillResult here.
        watchdog = _make_watchdog()
        cfg = {"poll_interval": 1.0, "grace_seconds": 10.0, "watchdogs": [watchdog]}
        watcher = watchdog_app.Watcher(get_config=lambda: cfg)
        calls = []
        watcher.on_kill = lambda rid, name, killed, failed: calls.append((rid, name, killed, failed))
        state = {"iter": 0, "t": 1000.0}

        def fake_open(trigger):
            script = [["app.exe"], [], []]
            return script[min(state["iter"], 2)]

        def fake_sleep(_secs):
            state["iter"] += 1
            state["t"] += 15.0
            if state["iter"] >= 3:
                watcher.stop()

        def fake_time():
            return state["t"]

        with patch.object(watchdog_app, "open_trigger_names", side_effect=fake_open), \
             patch.object(watchdog_app, "kill_processes",
                          return_value=watchdog_app.KillResult([], [])) as mock_kill, \
             patch.object(watchdog_app.time, "sleep", side_effect=fake_sleep), \
             patch.object(watchdog_app.time, "time", side_effect=fake_time):
            watcher.run()
        mock_kill.assert_called_once()
        # on_kill fired even though nothing was killed / failed
        self.assertEqual(len(calls), 1)
        rid, name, killed, failed = calls[0]
        self.assertEqual(rid, "wd1")
        self.assertEqual(name, "WD")
        self.assertEqual(killed, [])
        self.assertEqual(failed, [])

    def test_reopen_before_grace_cancels_kill(self):
        watcher, mock_kill = self._drive(
            [["app.exe"], [], ["app.exe"], ["app.exe"]], max_iter=4
        )
        mock_kill.assert_not_called()

    def test_disabled_watchdog_never_kills(self):
        watcher, mock_kill = self._drive(
            [["app.exe"], ["app.exe"], ["app.exe"], ["app.exe"]],
            enabled=False, max_iter=4
        )
        mock_kill.assert_not_called()

    def test_null_watched_app_never_triggers(self):
        # watched_app=None is the ambiguous/legacy-ambiguous state: it must not
        # schedule or perform any cleanup until Retrain sets a watched app.
        watchdog = _make_watchdog(
            watched_app=False,
            meal_targets=[{"name": "helper.exe", "exe": ""}],
        )
        watcher, mock_kill = self._drive(
            [["app.exe"], [], [], [], ["app.exe"]], max_iter=5, watchdog=watchdog
        )
        mock_kill.assert_not_called()
        self.assertEqual(watcher.get_open()["wd1"], [])


class WatcherStateTests(unittest.TestCase):
    def test_get_pending_returns_remaining_seconds_only_for_pending(self):
        watcher = watchdog_app.Watcher(get_config=lambda: {})
        watcher._pending_kill_at = {"wd1": 1010.0, "wd2": 990.0}
        with patch.object(watchdog_app.time, "time", return_value=1000.0):
            pending = watcher.get_pending()
        self.assertEqual(pending["wd1"], 10.0)
        self.assertEqual(pending["wd2"], 0.0)
        self.assertNotIn("wd3", pending)

    def test_get_pending_empty_when_nothing_pending(self):
        watcher = watchdog_app.Watcher(get_config=lambda: {})
        watcher._pending_kill_at = {}
        with patch.object(watchdog_app.time, "time", return_value=1000.0):
            self.assertEqual(watcher.get_pending(), {})

    def test_get_open_reflects_blocking_names(self):
        watcher = watchdog_app.Watcher(get_config=lambda: {})
        watcher._open_names = {"wd1": ["app.exe"], "wd2": []}
        self.assertEqual(watcher.get_open(), {"wd1": ["app.exe"], "wd2": []})


if __name__ == "__main__":
    unittest.main()
