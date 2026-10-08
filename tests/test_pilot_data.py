"""Tests for reproducible pilot population generation."""

import unittest

import pandas as pd

from src.pilot_data import generate_pilot_inputs


class PilotDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.daily_record = pd.Series({
            "date": "2017-01-02",
            "total_staffed_beds": 5,
            "total_occupied_beds": 3,
            "occupied_beds_non_elective_via_ed": 2,
            "occupied_beds_intensive": 1,
            "avg_los_non_elective_via_ed_days": 4.0,
        })
        self.appointments = pd.DataFrame([
            {
                "appointment_id": "patient-1",
                "source_key": "1",
                "date": "2017-01-02",
                "category": "non_elective_via_ed",
                "check_in_time": "08:00:00",
            },
            {
                "appointment_id": "patient-2",
                "source_key": "2",
                "date": "2017-01-02",
                "category": "non_elective_via_ed",
                "check_in_time": "09:00:00",
            },
        ])
        self.pilot_config = {
            "date": "2017-01-02",
            "modeled_room_count": 5,
            "simulation_horizon_hours": 24,
            "arrival_sampling_probability": 1.0,
            "arrival_sort_keys": ["date", "check_in_time", "appointment_id"],
            "length_of_stay_starts_at_admission": True,
            "patient_length_of_stay": {
                "distribution": "lognormal",
                "coefficient_of_variation": 0.5,
                "minimum_days": 0.1,
            },
        }
        self.room_need_config = {
            "probability_unoccupied_room_needs_cleaning": 1.0,
        }
        self.seeds = {
            "room_occupancy": 1,
            "initial_patient_categories": 2,
            "initial_patient_remaining_los": 3,
            "arrival_sampling": 4,
            "arrival_patient_los": 5,
            "initial_room_dirty_state": 6,
        }

    def generate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return generate_pilot_inputs(
            self.appointments,
            self.daily_record,
            self.pilot_config,
            self.room_need_config,
            self.seeds,
            overall_los_mean=5.9,
        )

    def test_room_and_arrival_inputs_are_reproducible(self) -> None:
        rooms_first, arrivals_first = self.generate()
        rooms_second, arrivals_second = self.generate()

        pd.testing.assert_frame_equal(rooms_first, rooms_second)
        pd.testing.assert_frame_equal(arrivals_first, arrivals_second)

        self.assertEqual(rooms_first["occupied"].sum(), 3)
        self.assertEqual(len(arrivals_first), 2)
        unoccupied = rooms_first.loc[~rooms_first["occupied"]]
        self.assertEqual(set(unoccupied["room_state"]), {"needs_cleaning"})
        self.assertTrue(unoccupied["dirty_state"].all())

    def test_initial_remaining_stay_is_consistent_with_total_stay(self) -> None:
        rooms, _ = self.generate()
        occupied = rooms.loc[rooms["occupied"]]

        self.assertTrue(
            (
                occupied["total_los_days"]
                == occupied["elapsed_los_days"] + occupied["remaining_los_days"]
            ).all()
        )
        self.assertTrue((occupied["remaining_los_days"] > 0).all())

    def test_missing_arrival_los_mean_fails_explicitly(self) -> None:
        appointments = self.appointments.copy()
        appointments.loc[0, "category"] = "missing_category"

        with self.assertRaisesRegex(ValueError, "no observed LOS mean"):
            generate_pilot_inputs(
                appointments,
                self.daily_record,
                self.pilot_config,
                self.room_need_config,
                self.seeds,
                overall_los_mean=5.9,
            )

    def test_multi_date_arrivals_use_minutes_from_pilot_start(self) -> None:
        appointments = self.appointments.copy()
        appointments.loc[1, "date"] = "2017-01-03"
        next_day = self.daily_record.copy()
        next_day["date"] = "2017-01-03"
        next_day["avg_los_non_elective_via_ed_days"] = 6.0
        daily_records = pd.DataFrame([
            self.daily_record,
            next_day,
        ])
        pilot_config = {
            **self.pilot_config,
            "simulation_horizon_hours": 48,
        }

        _, arrivals = generate_pilot_inputs(
            appointments,
            daily_records,
            pilot_config,
            self.room_need_config,
            self.seeds,
            overall_los_mean=5.9,
        )

        self.assertEqual(arrivals["date"].tolist(), ["2017-01-02", "2017-01-03"])
        self.assertEqual(arrivals["arrival_time_minutes"].tolist(), [480.0, 1980.0])


if __name__ == "__main__":
    unittest.main()
