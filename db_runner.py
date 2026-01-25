import sqlite3

DB_PATH = "db/erdos.db"

def print_people_by_faculty(faculty_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, full_name, title, gender, role
        FROM person
        WHERE faculty = ?
        ORDER BY full_name
    """, (faculty_name,))

    rows = cur.fetchall()

    print(f"\nFakultet: {faculty_name}")
    print(f"Broj osoba: {len(rows)}\n")

    for r in rows:
        print(
            f"ID={r[0]:<4} | "
            f"{r[1]} | "
            f"title={r[2]} | "
            f"gender={r[3]} | "
            f"role={r[4]}"
        )

    conn.close()


if __name__ == "__main__":
    print_people_by_faculty("Tehničko veleučilište u Zagrebu")
