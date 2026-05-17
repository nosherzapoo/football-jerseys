"""One-time seeder: creates tables and loads kits from the CSV.

Usage:
    DATABASE_URL='postgresql://...' python seed.py

Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING for the kit list.
The schema bits use IF NOT EXISTS too.
"""
import csv
import os
import sys
from pathlib import Path

# Allow running this file directly: make the `api` package importable.
sys.path.insert(0, str(Path(__file__).parent))

from api import db  # noqa: E402

CSV_PATH = Path(__file__).parent / "world_cup_2026_kits.csv"


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        sys.exit("Set DATABASE_URL first, e.g. via `export` or a .env loader.")

    c = db.conn()
    db.init_schema(c)
    print("Schema ready.")

    with open(CSV_PATH, newline="", encoding="utf-8") as f, c.cursor() as cur:
        n = 0
        for row in csv.DictReader(f):
            cur.execute(
                "INSERT INTO jerseys (country, kit_type, image_path) "
                "VALUES (%s, %s, %s) ON CONFLICT (country, kit_type) DO NOTHING",
                (
                    row["country_name"].strip(),
                    row["kit_type"].strip().lower(),
                    row["better_image_path"].strip(),
                ),
            )
            n += cur.rowcount
        c.commit()
        print(f"Inserted {n} new kits.")

        cur.execute("SELECT COUNT(*) FROM jerseys")
        print(f"Total kits in DB: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
