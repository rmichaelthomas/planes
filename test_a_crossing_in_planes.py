"""test_a_crossing_in_planes.py — paint/a_crossing.planes, driven through
the PERSISTENT-KERNEL calling convention (Horizon Phase 2 Build 2's own
port: world-init/advance, not the showcase path's prelude-injected
state/event/tick single-pass re-interpretation).

REWRITTEN, NOT JUST PATCHED — mirrors js/test/a_crossing_scene.test.mjs's
own rewrite exactly (see that file's header for the full rationale): every
test here existed before this build, manually composing a
`state`/`event`/`tick`/`seed` prelude and calling `interpreter.run_file(...)`
to re-interpret the WHOLE file each time, reading the result back out of
`host.files["state.json"]`. paint/a_crossing.planes no longer writes
`state.json` at all (the kernel's own snapshot substrate replaces it — see
that file's header) and has no top-level logic left to re-run — every bit
of it moved into world-init/advance function bodies. This file preserves
every ORIGINAL assertion's intent against the new calling convention.
"""
import unittest

from host import TestHost
from interp import to_host
from world_runtime import WorldRuntime


class CrossingFixtureTests(unittest.TestCase):
    def boot(self):
        return WorldRuntime("paint/a_crossing.planes", host=TestHost())

    def init(self, rt):
        rt.init()
        lines, _trace = rt.take_output()
        return to_host(rt.world.value), lines

    def step(self, rt, events=None):
        rt.advance(events)
        lines, _trace = rt.take_output()
        return to_host(rt.world.value), lines

    def step_n(self, rt, n, events=None):
        state, lines = None, None
        for _ in range(n):
            state, lines = self.step(rt, events)
        return state, lines

    def test_ready_fixture_writes_crossing_state(self):
        state, lines = self.init(self.boot())
        self.assertEqual(state["status"], "crossing-ready")
        self.assertEqual(state["need"], "care")
        self.assertEqual(state["phase"], "choosing")
        self.assertEqual(state["progress"], 0)
        self.assertIn("scene protocol 1", lines)
        self.assertIn("scene environment bright-passage afternoon rolu-grandi-3", lines)

    def test_shelter_choice_delays_the_simulated_crossing(self):
        rt = self.boot()
        self.init(rt)
        state, _lines = self.step(rt, [{"kind": "route", "choice": "shelter"}])
        self.assertEqual(state["status"], "crossing-delayed")

    def test_all_route_outcomes_match_the_javascript_fixtures(self):
        for choice, status in (
            ("reserve", "crossing-refused"),
            ("depart", "crossing-active"),
        ):
            with self.subTest(choice=choice):
                rt = self.boot()
                self.init(rt)
                state, _lines = self.step(rt, [{"kind": "route", "choice": choice}])
                self.assertEqual(state["status"], status)

    def test_needs_and_tick_progress_are_owned_by_planes(self):
        for choice, selected in (
            ("care", "clinic-beacon"),
            ("education", "radio-mast"),
            ("work", "market"),
        ):
            with self.subTest(choice=choice):
                rt = self.boot()
                self.init(rt)
                state, _lines = self.step(rt, [{"kind": "need", "choice": choice}])
                self.assertEqual(state["need"], choice)
                self.assertEqual(state["selected"], selected)
                self.assertEqual(state["phase"], "planning")

        # A persistent kernel ticks one at a time — no "jump to tick N" the
        # old per-call re-interpretation model had (see the JS sibling
        # test's own comment on this). depart consumes tick 0; 80 more
        # self-driving ticks (events=None) land exactly at tick 80.
        rt = self.boot()
        self.init(rt)
        self.step(rt, [{"kind": "route", "choice": "depart"}])
        underway, _lines = self.step_n(rt, 80)
        self.assertEqual(underway["progress"], 0.5)
        arrived, _lines = self.step_n(rt, 80)  # tick 81 .. 160
        self.assertEqual(arrived["status"], "crossing-arrived")
        self.assertEqual(arrived["progress"], 1)

    def test_power_radio_and_selection_events_thread_state(self):
        rt = self.boot()
        self.init(rt)
        clinic, _lines = self.step(rt, [{"kind": "power", "choice": "clinic"}])
        self.assertEqual(clinic["selected"], "clinic-beacon")
        self.assertEqual(clinic["minutes"], 84)

        radio, _lines = self.step(rt, [{"kind": "radio", "choice": "relay"}])
        self.assertEqual(radio["radio"], "relayed")

        selected, _lines = self.step(rt, [{"kind": "select", "subject": "fog-capture"}])
        self.assertEqual(selected["selected"], "fog-capture")
        self.assertEqual(selected["minutes"], radio["minutes"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CrossingFixtureTests)
    result = unittest.TextTestRunner().run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{passed}/{result.testsRun} passing")
    raise SystemExit(0 if result.wasSuccessful() else 1)
