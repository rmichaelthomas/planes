import json
import unittest

from host import TestHost
from interp import Interpreter


def crossing_source():
    with open("paint/a_crossing.planes", encoding="utf-8") as fh:
        return fh.read()


def planes_literal(value):
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(planes_literal(item) for item in value) + "]"
    return "{ " + ", ".join(
        f"{key}: {planes_literal(item)}" for key, item in value.items()
    ) + " }"


class CrossingFixtureTests(unittest.TestCase):
    def run_crossing(self, event=None, state=None, tick=0):
        host = TestHost()
        interpreter = Interpreter(host=host)
        interpreter.run(
            f"let tick = {tick}\nlet keys = []\n"
            "let pointer = { x: 0, y: 0, down: false }\n"
            f"let state = {planes_literal(state)}\nlet seed = 481027\n"
            f"let event = {planes_literal(event)}\n"
        )
        interpreter.run_file("paint/a_crossing.planes")
        return host

    def test_ready_fixture_writes_crossing_state(self):
        host = self.run_crossing()
        state = json.loads(host.files["state.json"])
        self.assertEqual(state["status"], "crossing-ready")
        self.assertEqual(state["need"], "care")
        self.assertEqual(state["phase"], "choosing")
        self.assertEqual(state["progress"], 0)
        self.assertIn("scene protocol 1", host.shown)
        self.assertIn("scene environment bright-passage afternoon rolu-grandi-3", host.shown)

    def test_shelter_choice_delays_the_simulated_crossing(self):
        ready = json.loads(self.run_crossing().files["state.json"])
        host = self.run_crossing({"kind": "route", "choice": "shelter"}, ready)
        self.assertEqual(
            json.loads(host.files["state.json"])["status"], "crossing-delayed"
        )

    def test_all_route_outcomes_match_the_javascript_fixtures(self):
        for choice, status in (
            ("reserve", "crossing-refused"),
            ("depart", "crossing-active"),
        ):
            with self.subTest(choice=choice):
                ready = json.loads(self.run_crossing().files["state.json"])
                host = self.run_crossing({"kind": "route", "choice": choice}, ready)
                self.assertEqual(json.loads(host.files["state.json"])["status"], status)

    def test_needs_and_tick_progress_are_owned_by_planes(self):
        ready = json.loads(self.run_crossing().files["state.json"])
        for choice, selected in (
            ("care", "clinic-beacon"),
            ("education", "radio-mast"),
            ("work", "market"),
        ):
            with self.subTest(choice=choice):
                host = self.run_crossing({"kind": "need", "choice": choice}, ready)
                state = json.loads(host.files["state.json"])
                self.assertEqual(state["need"], choice)
                self.assertEqual(state["selected"], selected)
                self.assertEqual(state["phase"], "planning")

        active = json.loads(self.run_crossing(
            {"kind": "route", "choice": "depart"}, ready
        ).files["state.json"])
        underway_host = self.run_crossing(state=active, tick=80)
        underway = json.loads(underway_host.files["state.json"])
        self.assertEqual(underway["progress"], "0.5")
        arrived = json.loads(self.run_crossing(state=underway, tick=160).files["state.json"])
        self.assertEqual(arrived["status"], "crossing-arrived")
        self.assertEqual(arrived["progress"], 1)

    def test_power_radio_and_selection_events_thread_state(self):
        ready_host = self.run_crossing()
        ready = json.loads(ready_host.files["state.json"])
        clinic_host = self.run_crossing({"kind": "power", "choice": "clinic"}, ready)
        clinic = json.loads(clinic_host.files["state.json"])
        self.assertEqual(clinic["selected"], "clinic-beacon")
        self.assertEqual(clinic["minutes"], 84)

        radio_host = self.run_crossing({"kind": "radio", "choice": "relay"}, clinic)
        radio = json.loads(radio_host.files["state.json"])
        self.assertEqual(radio["radio"], "relayed")

        selected_host = self.run_crossing(
            {"kind": "select", "subject": "fog-capture"}, radio
        )
        selected = json.loads(selected_host.files["state.json"])
        self.assertEqual(selected["selected"], "fog-capture")
        self.assertEqual(selected["minutes"], radio["minutes"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CrossingFixtureTests)
    result = unittest.TextTestRunner().run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{passed}/{result.testsRun} passing")
    raise SystemExit(0 if result.wasSuccessful() else 1)
