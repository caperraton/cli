import csv
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List


def export_report(rows: List[Dict[str, Any]], out_dir: Path, stem: str, formats: List[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if "json" in formats:
        p = out_dir / f"{stem}.json"
        p.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"[export] Wrote {len(rows)} rows -> {p}")
    if "csv" in formats:
        p = out_dir / f"{stem}.csv"
        fieldnames = list(rows[0].keys()) if rows else []
        with p.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(rows)
        print(f"[export] Wrote {len(rows)} rows -> {p}")


class DBManager:
    """SQLite upsert manager (easily swappable to Postgres via psycopg/SQLAlchemy)."""

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS report_records (
                report_type TEXT NOT NULL,
                record_key TEXT NOT NULL,
                platform TEXT NOT NULL,
                org TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (report_type, record_key)
            )
        """)
        self.conn.commit()

    def upsert_rows(self, report_type: str, rows: List[Dict[str, Any]], key_fields: List[str]) -> int:
        cur = self.conn.cursor()
        count = 0
        for r in rows:
            key = "|".join(str(r.get(k, "")) for k in key_fields)
            cur.execute(
                """
                INSERT INTO report_records (report_type, record_key, platform, org, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(report_type, record_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (report_type, key, r.get("platform", ""), r.get("org", ""), json.dumps(r)),
            )
            count += 1
        self.conn.commit()
        return count

    def close(self) -> None:
        self.conn.close()