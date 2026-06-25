import sqlite3

DB_PATH = "db\\erdos.db"

def fix_titles():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        UPDATE person
        SET title = TRIM(REPLACE(title, '-', ' '))
        WHERE title LIKE '%-%'
    """)

    cur.execute("""
        UPDATE person
        SET title = TRIM(REPLACE(title, '  ', ' '))
        WHERE title LIKE '%  %'
    """)

    conn.commit()
    conn.close()
    print("Titles cleaned successfully.")

if __name__ == "__main__":
    fix_titles()