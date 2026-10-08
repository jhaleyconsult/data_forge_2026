"""Integration tests for the configured one-week SimPy pilot."""

import unittest
from pathlib import Path

import pandas as pd

from src.sim import _patient_priority, run_pilot_simulation


class PilotSimulationTests(unittest.TestCase):
    def test_queue_priority_uses_configured_category_order(self) -> None:
        config = {
            "patient_queue_priority": {
                "emergency_categories": ["non_elective_via_ed"],
                "elective_categories": ["elective"],
                "order": ["emergency", "elective", "other"],
            }
        }

        self.assertEqual(
            _patient_priority("non_elective_via_ed", config),
            (0, "emergency"),
        )
        self.assertEqual(_patient_priority("elective", config), (1, "elective"))
        self.assertEqual(_patient_priority("newborn", config), (2, "other"))

    def test_pilot_is_reproducible_and_obeys_room_state_sequence(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        first = run_pilot_simulation(project_root)
        second = run_pilot_simulation(project_root)

        pd.testing.assert_frame_equal(first.event_log, second.event_log)
        pd.testing.assert_frame_equal(first.cleaner_activity, second.cleaner_activity)
        self.assertEqual(first.metrics, second.metrics)
        self.assertEqual(first.metrics["initial_rooms"], 10)
        self.assertEqual(first.metrics["initial_occupied_rooms"], 7)
        self.assertGreater(first.metrics["scaled_arrivals"], 1)
        self.assertEqual(first.metrics["simulation_horizon_hours"], 168)
        self.assertEqual(
            first.event_log["event_datetime"].min().date(),
            pd.Timestamp("2017-01-02").date(),
        )
        self.assertLess(
            first.event_log["event_datetime"].max(),
            pd.Timestamp("2017-01-09"),
        )
        self.assertEqual(
            first.cleaner_activity["start_datetime"].dt.date.nunique(),
            7,
        )
        self.assertGreater(first.metrics["ghost_room_minutes"], 0)
        self.assertGreater(first.metrics["idle_bed_hours"], 0)
        self.assertGreaterEqual(
            first.metrics["idle_bed_hours"] * 60,
            first.metrics["ghost_room_minutes"],
        )

        valid_transitions = {
            ("", "available"),
            ("", "occupied"),
            ("", "needs_cleaning"),
            ("occupied", "discharge_pending"),
            ("discharge_pending", "needs_cleaning"),
            ("needs_cleaning", "cleaning"),
            ("cleaning", "available"),
            ("available", "occupied"),
        }
        observed = set(
            zip(first.event_log["from_state"], first.event_log["to_state"])
        )
        self.assertTrue(observed <= valid_transitions)


if __name__ == "__main__":
    unittest.main()
