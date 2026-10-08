"""Single-process JSON persistence for the local API demonstration."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from src.events import BedStatus

VALID_STATUSES = {
    "available",
    "occupied",
    "discharge_pending",
    "needs_cleaning",
    "cleaning",
}
DEFAULT_STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "api_state.json"


class FileStateStore:
    """Read and atomically update patient statuses in a local JSON file."""

    def __init__(self, path: Path = DEFAULT_STATE_FILE) -> None:
        self.path = path
        self._lock = Lock()

    def get_status(self, patient_id: str) -> BedStatus | None:
        """Return a patient's current status, if one is recorded."""
        with self._lock:
            return self._read().get(patient_id)

    def set_status(self, patient_id: str, status: BedStatus) -> None:
        """Persist a patient's status with an atomic file replacement."""
        with self._lock:
            statuses = self._read()
            statuses[patient_id] = status
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_name(f"{self.path.name}.tmp")
            temporary_path.write_text(
                json.dumps(statuses, indent=2) + "\n", encoding="utf-8"
            )
            temporary_path.replace(self.path)

    def _read(self) -> dict[str, BedStatus]:
        if not self.path.exists():
            return {}
        try:
            statuses = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not read API state file {self.path}") from error
        if not isinstance(statuses, dict) or any(
            not isinstance(patient_id, str)
            or not isinstance(status, str)
            or status not in VALID_STATUSES
            for patient_id, status in statuses.items()
        ):
            raise RuntimeError(f"API state file {self.path} has an invalid format")
        return statuses


state_store = FileStateStore()