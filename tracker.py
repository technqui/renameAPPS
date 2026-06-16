import json
import os
from datetime import datetime

TRACKER_FILE = "processed_contacts.json"


class ContactTracker:
    def __init__(self, tracker_file: str = TRACKER_FILE):
        self.tracker_file = tracker_file
        self._data: dict = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.tracker_file):
            try:
                with open(self.tracker_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        with open(self.tracker_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def is_processed(self, original_name: str) -> bool:
        return original_name in self._data

    def mark_processed(self, original_name: str, new_name: str, seq_num: int) -> None:
        self._data[original_name] = {
            "new_name": new_name,
            "seq_num": seq_num,
            "timestamp": datetime.now().isoformat(),
        }
        self._save()

    def clear(self) -> None:
        self._data = {}
        self._save()
