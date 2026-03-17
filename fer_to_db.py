import csv
import requests
import sqlite3
import time
import unicodedata
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DB_PATH = "db\\erdos.db"
FIRSTNAMES_CSV = "db\\firstnames.csv"

BASE_ISVU = "https://www.isvu.hr"
BASE_FER = "https://www.fer.unizg.hr/"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# ------------------------
# Normalization
# ------------------------

def normalize(text: str) -> str:
    text = text.lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    text = text.replace("-", " ")
    return " ".join(text.split())

def slugify_name(full_name):
    parts = normalize(full_name).split()

    if len(parts) == 2:
        return f"{parts[0]}.{parts[1]}", None
    else:
        return f"{'_'.join(parts[:-1])}.{parts[-1]}", f"{parts[0]}.{'_'.join(parts[1:])}"

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
# DB
# ------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS person (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        title TEXT,
        gender TEXT,
        department TEXT,
        role TEXT,
        fer_profile_url TEXT,
        UNIQUE(full_name)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL UNIQUE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS authorship (
        person_id INTEGER NOT NULL,
        paper_id INTEGER NOT NULL,
        PRIMARY KEY (person_id, paper_id),
        FOREIGN KEY (person_id) REFERENCES person(id),
        FOREIGN KEY (paper_id) REFERENCES paper(id)
    );
    """)

    conn.commit()
    return conn

def insert_person(cur, data):
    cur.execute("""
        INSERT OR IGNORE INTO person
        (full_name, title, gender, department, role, fer_profile_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, data)

# ------------------------
# Name parsing (ROBUST)
# ------------------------

def parse_name_and_title(raw_name):

    raw_name = raw_name.strip()

    if "," in raw_name:
        before_comma, after_comma = raw_name.split(",", 1)
        full_name = before_comma.strip()
        extra_title = after_comma.strip()
    else:
        full_name = raw_name
        extra_title = ""

    parts = full_name.split()

    title_parts = []
    name_parts = []

    for p in parts:
        if p[0].isupper():
            name_parts.append(p)
        else:
            title_parts.append(p)

    title = " ".join(title_parts)

    if extra_title:
        if title:
            title = title + ", " + extra_title
        else:
            title = extra_title

    clean_name = " ".join(name_parts)

    return clean_name, title

# ------------------------
# FER PROFILE PARSER
# ------------------------

def parse_fer_profile(html):

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n")

    for line in text.split("\n"):
        line = line.strip()

        if "Zavod za" in line:
            idx = line.find("Zavod za")
            return line[idx:].strip()

    return None

# ------------------------
# FER PEOPLE
# ------------------------

def parse_fer_people(conn, gender_db):

    url = f"{BASE_ISVU}/visokaucilista/hr/podaci/36/nastavnici"
    soup = BeautifulSoup(requests.get(url).text, "html.parser")

    table = soup.find("table")
    rows = table.find_all("tr")[1:]

    cur = conn.cursor()

    for row in rows:

        tds = row.find_all("td")
        if not tds:
            continue

        raw_name = tds[0].get_text(strip=True)
        role = tds[2].get_text(strip=True)

        full_name, title = parse_name_and_title(raw_name)

        if not full_name:
            continue

        first_name = full_name.split()[0]
        gender = find_gender(first_name, gender_db)

        slug1, slug2 = slugify_name(full_name)

        potential_slugs = []

        # Prvo “normalni” slugovi
        for s in [slug1, slug2]:
            if s:
                potential_slugs.append(s)
                potential_slugs.append(s.replace("_", "-"))

        # Ukloni duplikate
        potential_slugs = list(dict.fromkeys(potential_slugs))

        department = None
        profile_url_final = None

        print(f"Processing: {full_name}")

        # Funkcija koja provjeri listu slugova s opcionalnim prefixom
        def try_slugs(slugs, prefix=""):
            for slug in slugs:
                profile_url = urljoin(BASE_FER, f"{prefix}{slug}")
                try:
                    r = requests.get(profile_url, timeout=10)
                    if r.status_code == 200:
                        return profile_url, parse_fer_profile(r.text)
                except Exception as e:
                    print(f" Error connecting to {profile_url}: {e}")
            return None, None

        # Prvo pokušaj bez /en/
        profile_url_final, department = try_slugs(potential_slugs)

        # Ako ništa nije pronađeno, probaj sa /en/
        if not profile_url_final:
            profile_url_final, department = try_slugs(potential_slugs, prefix="en/")

        if not department:
            print("No department found for:", full_name)

        insert_person(cur, (
            full_name,
            title,
            gender,
            department,
            role,
            profile_url_final
        ))

        conn.commit()
        time.sleep(1.5)

# function for fixing unknown genders in database

def fix_unknown_genders(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT id, full_name FROM person
        WHERE gender = 'unknown'
    """)

    rows = cur.fetchall()

    print("\n--- Manual gender input ---")
    print("Enter M / F (or press Enter to skip)\n")

    for person_id, full_name in rows:
        while True:
            user_input = input(f"{full_name} (M/F/skip): ").strip().upper()

            if user_input == "":
                break
            elif user_input in ("M", "F"):
                cur.execute("""
                    UPDATE person
                    SET gender = ?
                    WHERE id = ?
                """, (user_input, person_id))
                conn.commit()
                break
            else:
                print("Invalid input. Use M, F or Enter to skip.")

# ------------------------
# MAIN
# ------------------------

def main():

    gender_db = load_name_database(FIRSTNAMES_CSV)

    conn = init_db()

    parse_fer_people(conn, gender_db)
    print("Finished FER people import")

    fix_unknown_genders(conn)

    conn.close()

    print("Program end")

if __name__ == "__main__":
    main()