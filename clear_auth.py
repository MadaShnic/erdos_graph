import sqlite3
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "statistics.db")


def normalize_title(title: str) -> str:
    if not title:
        return title

    t = title.strip().lower()

    # 🔥 1. SVE mag.ing.* -> mag. ing.
    if "mag" in t:
        return "mag. ing."

    # 🧠 2. dr.sc. logika (bez razmaka, duljina = 6)
    t_no_space = re.sub(r"\s+", "", t)

    if t_no_space == "dr.sc.":
        return "dr. sc."
    

    # fallback
    return title.strip()


def clean_and_normalize_authors():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # BEFORE COUNT
    cur.execute("SELECT COUNT(*) FROM author_stats")
    before = cur.fetchone()[0]

    # 🧹 DELETE useless authors
    cur.execute("""
        DELETE FROM author_stats
        WHERE graph_nodes = 0
    """)
    conn.commit()

    # 🔧 NORMALIZE TITLES
    cur.execute("SELECT rowid, title FROM author_stats")
    rows = cur.fetchall()

    changes = {}

    for rowid, title in rows:
        new_title = normalize_title(title)

        if title != new_title:
            changes[title] = new_title

            cur.execute("""
                UPDATE author_stats
                SET title = ?
                WHERE rowid = ?
            """, (new_title, rowid))

    conn.commit()

    # AFTER COUNT
    cur.execute("SELECT COUNT(*) FROM author_stats")
    after = cur.fetchone()[0]

    print(f"Removed authors: {before - after}")
    print(f"Remaining authors: {after}")

    print("\n=== TITLE FIXES ===")
    for old, new in changes.items():
        print(f"{old}  --->  {new}")

    conn.close()


if __name__ == "__main__":
    clean_and_normalize_authors()