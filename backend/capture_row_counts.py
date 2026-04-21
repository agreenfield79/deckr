"""Capture pre-refactor SQLite row counts. Run once before any Phase 3B changes."""
import sqlite3
import json

con = sqlite3.connect("data/deckr.db")
tables = [
    r[0]
    for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
]
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
con.close()

output_path = "data/pre-refactor-row-counts.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(counts, f, indent=2)

print(f"Saved to {output_path}")
for table, count in counts.items():
    print(f"  {table:<40} {count}")
