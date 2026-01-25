import csv
import requests
import sqlite3
import time
import unicodedata
from bs4 import BeautifulSoup

DB_PATH = "db\\erdos.db"
STEM_CSV = "db\\stem_unis.csv"
FIRSTNAMES_CSV = "db\\firstnames.csv"
BASE_URL = "https://www.isvu.hr"

# ------------------------
# Normalization (HR-safe)
# ------------------------

def normalize(text: str) -> str:
    text = text.lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())

# ------------------------
# Gender DB
# ------------------------

def load_name_database(path):
    temp = {}

    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if not row:
                continue

            name = row[0].strip().lower()
            gender = row[1].strip().upper() if len(row) > 1 else ""

            temp.setdefault(name, set())
            if gender:
                temp[name].add(gender)

    db = {}
    for name, genders in temp.items():
        if "M" in genders:
            db[name] = "M"
        elif "F" in genders:
            db[name] = "F"
        else:
            db[name] = "unknown"

    return db


def find_gender(first_name, db):
    return db.get(first_name.lower(), "unknown")

# ------------------------
# Load STEM universities
# ------------------------

def load_stem_unis(path):
    stem = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stem.add(normalize(row["name"]))
    return stem

# ------------------------
# DB
# ------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # PERSON
    cur.execute("""
    CREATE TABLE IF NOT EXISTS person (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        title TEXT,
        gender TEXT,
        faculty TEXT NOT NULL,
        faculty_id INTEGER,
        role TEXT,
        isvu_person_id TEXT,
        UNIQUE(full_name, faculty)
    );
    """)

    # PAPER
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        UNIQUE(title)
    );
    """)

    # AUTHORSHIP (many-to-many)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS authorship (
        person_id INTEGER NOT NULL,
        paper_id INTEGER NOT NULL,
        FOREIGN KEY(person_id) REFERENCES person(id),
        FOREIGN KEY(paper_id) REFERENCES paper(id),
        UNIQUE(person_id, paper_id)
    );
    """)

    conn.commit()
    return conn


def insert_person(cur, data):
    cur.execute("""
        INSERT OR IGNORE INTO person
        (full_name, title, gender, faculty, faculty_id, role, isvu_person_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, data)


def get_person_id(cur, full_name, faculty):
    cur.execute("""
        SELECT id FROM person WHERE full_name=? AND faculty=?
    """, (full_name, faculty))
    row = cur.fetchone()
    return row[0] if row else None


def insert_paper(cur, title):
    cur.execute("""
        INSERT OR IGNORE INTO paper (title)
        VALUES (?)
    """, (title,))
    cur.execute("""
        SELECT id FROM paper WHERE title=?
    """, (title,))
    return cur.fetchone()[0]


def insert_authorship(cur, person_id, paper_id):
    cur.execute("""
        INSERT OR IGNORE INTO authorship (person_id, paper_id)
        VALUES (?, ?)
    """, (person_id, paper_id))

# ------------------------
# ISVU scraping
# ------------------------

def get_isvu_faculties():
    url = f"{BASE_URL}/visokaucilista/hr/pretrazivanje"
    soup = BeautifulSoup(requests.get(url).text, "html.parser")

    faculties = []
    for a in soup.select("a[href*='/podaci/']"):
        name = a.get_text(strip=True)
        fid = a["href"].split("/")[-1]
        faculties.append((fid, name))

    return faculties


def split_title_name(raw):
    """
    Title = sve do prve rijeci s velikim pocetnim slovom
    """
    parts = raw.replace("-", " ").split()
    title_parts = []
    name_parts = []

    for p in parts:
        if p[0].isupper():
            name_parts.append(p)
        else:
            title_parts.append(p)

    return " ".join(title_parts), " ".join(name_parts)


def parse_faculty_people(conn, fid, faculty_name, gender_db):
    url = f"{BASE_URL}/visokaucilista/hr/podaci/{fid}/nastavnici"
    soup = BeautifulSoup(requests.get(url).text, "html.parser")

    table = soup.find("table")
    if not table:
        return

    rows = table.find_all("tr")[1:]
    cur = conn.cursor()

    for row in rows:
        tds = row.find_all("td")
        if not tds:
            continue

        isvu_person_id = tds[0].get("data-oznakanastavnik")
        raw_name = tds[0].get_text(strip=True)
        role = tds[2].get_text(strip=True)

        title, full_name = split_title_name(raw_name)
        first_name = full_name.split()[0]
        gender = find_gender(first_name, gender_db)

        insert_person(cur, (
            full_name,
            title,
            gender,
            faculty_name,
            fid,
            role,
            isvu_person_id
        ))

    conn.commit()

# ------------------------
# MAIN
# ------------------------

def main():
    stem_unis = load_stem_unis(STEM_CSV)
    gender_db = load_name_database(FIRSTNAMES_CSV)
    conn = init_db()

    isvu_faculties = get_isvu_faculties()
    print(f"ISVU faculties found: {len(isvu_faculties)}")

    for fid, name in isvu_faculties:
        if normalize(name) in stem_unis:
            print(f"[STEM] {name}")
            parse_faculty_people(conn, fid, name, gender_db)
            time.sleep(1)

    conn.close()
    print("Finished.")

if __name__ == "__main__":
    main()
