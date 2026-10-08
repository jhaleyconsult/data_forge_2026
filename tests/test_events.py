"""Tests for API-independent bed state transitions."""

import unittest

from src.events import (
    Patient,
    Room,
    check_in,
    check_out,
    current_care,
    finish_cleaning,
    start_cleaning,
)


class BedEventTests(unittest.TestCase):
    def test_room_moves_through_the_required_state_sequence(self) -> None:
        room = Room("ROOM-01", "available")
        patient = Patient("patient-1", "elective", "elective", 120.0)
        event_log = []

        check_in(room, patient, 0.0, event_log)
        current_care(room, 120.0, event_log)
        checked_out_patient = check_out(room, 120.0, event_log)
        start_cleaning(room, 150.0, event_log)
        finish_cleaning(room, 195.0, event_log)

        self.assertIs(checked_out_patient, patient)
        self.assertEqual(
            [entry["to_state"] for entry in event_log],
            [
                "occupied",
                "discharge_pending",
                "needs_cleaning",
                "cleaning",
                "available",
            ],
        )
        self.assertEqual(
            [entry["patient_id"] for entry in event_log],
            ["patient-1"] * 5,
        )
        self.assertEqual(room.state, "available")
        self.assertIsNone(room.patient)

    def test_invalid_transition_fails_explicitly(self) -> None:
        room = Room("ROOM-01", "available")

        with self.assertRaisesRegex(ValueError, "does not need cleaning"):
            start_cleaning(room, 0.0, [])


if __name__ == "__main__":
    unittest.main()
