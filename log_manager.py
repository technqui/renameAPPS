import csv
import os
from datetime import datetime
from typing import List, Dict

COLUMNS = ["No", "Original Name", "New Name", "Status", "Timestamp", "Notes"]


class LogManager:
    def __init__(self, log_file: str = "zalo_rename_log.csv"):
        self.log_file = log_file
        self.records: List[Dict] = []
        self._counter = 0
        self._load_history()

    def _load_history(self) -> None:
        """Read records from an existing CSV so history survives app restarts."""
        if not os.path.exists(self.log_file):
            return
        try:
            with open(self.log_file, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    record = {col: row.get(col, "") for col in COLUMNS}
                    self.records.append(record)
                    try:
                        no = int(row.get("No", 0))
                        if no > self._counter:
                            self._counter = no
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    def set_log_file(self, path: str) -> None:
        self.log_file = path

    def add_record(
        self,
        original_name: str,
        new_name: str,
        status: str,
        notes: str = "",
    ) -> Dict:
        self._counter += 1
        record = {
            "No": self._counter,
            "Original Name": original_name,
            "New Name": new_name,
            "Status": status,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Notes": notes,
        }
        self.records.append(record)
        self._save()
        return record

    def _save(self) -> None:
        with open(self.log_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(self.records)

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(self.records)

    def export_excel(self, path: str) -> None:
        import pandas as pd
        pd.DataFrame(self.records, columns=COLUMNS).to_excel(path, index=False)

    def get_records(self) -> List[Dict]:
        return list(self.records)

    def clear(self) -> None:
        self.records = []
        self._counter = 0
