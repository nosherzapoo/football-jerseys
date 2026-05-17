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
        inserted = 0
        updated_alt = 0
        for row in csv.DictReader(f):
            country = row["country_name"].strip()
            kit_type = row["kit_type"].strip().lower()
            primary = row["better_image_path"].strip()
            left = row["left_half_image_path"].strip()
            right = row["right_half_image_path"].strip()
            # The "alt" half is whichever isn't already the primary. If the row
            # uses a single image for all three slots (e.g. when only the full
            # photo is usable), leave image_alt NULL so voting doesn't rotate
            # to a duplicate.
            if left == right:
                alt = None
            else:
                alt = right if primary == left else left

            cur.execute(
                "INSERT INTO jerseys (country, kit_type, image_path, image_alt) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (country, kit_type) DO NOTHING",
                (country, kit_type, primary, alt),
            )
            inserted += cur.rowcount

            # Backfill image_alt for rows that pre-date the column.
            cur.execute(
                "UPDATE jerseys SET image_alt = %s "
                "WHERE country = %s AND kit_type = %s AND image_alt IS NULL",
                (alt, country, kit_type),
            )
            updated_alt += cur.rowcount
        c.commit()
        print(f"Inserted {inserted} new kits.")
        print(f"Backfilled image_alt for {updated_alt} existing rows.")

        cur.execute("SELECT COUNT(*) FROM jerseys")
        print(f"Total kits in DB: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
