import sqlite3
import requests
import time
import random
import unicodedata
import json
import os

DB_PATH = "db\\erdos.db"
CACHE_FILE = "dblp_cache.json"


# ------------------ utils ------------------

def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.replace("-", " ")
    nfkd = unicodedata.normalize("NFKD", name)

    cleaned = "".join(
        c for c in nfkd if not unicodedata.combining(c)
    ).lower().strip()

    return " ".join(cleaned.split())


def name_matches(a: str, b: str) -> bool:
    """
    Pametniji matching:
    - ignorira redoslijed
    - ignorira crtice
    """

    a_parts = set(normalize_name(a).split())
    b_parts = set(normalize_name(b).split())

    # mora imati barem 2 zajednička dijela (ime + prezime)
    return len(a_parts & b_parts) >= 2


# ------------------ CACHE ------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


# ------------------ DBLP API ------------------

def dblp_api_search(name, cache,
                    max_hits=1000,
                    initial_delay=2,
                    max_delay=64,
                    max_retries=10):

    if name in cache:
        return cache[name]

    url = "https://dblp.org/search/publ/api"
    params = {
        "q": name,
        "format": "json",
        "h": max_hits
    }

    delay = initial_delay
    retries = 0

    while True:
        try:
            time.sleep(delay + random.uniform(0.0, 0.5))

            r = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Academic research (Erdos graph)"},
                timeout=30
            )

            if r.status_code == 200:
                data = r.json()
                cache[name] = data
                return data

            if r.status_code == 429:
                retries += 1
                if retries > max_retries:
                    raise RuntimeError(f"Too many retries for '{name}'")

                print(f"[429] {name}, retry in {delay}s")
                delay = min(delay * 2, max_delay)
                continue

            r.raise_for_status()

        except requests.RequestException as e:
            retries += 1
            if retries > max_retries:
                raise RuntimeError(f"Fail for '{name}': {e}")

            print(f"[ERROR] {e}, retry in {delay}s")
            delay = min(delay * 2, max_delay)


# ------------------ PARSE ------------------

def parse_publications(data):
    hits = data.get("result", {}).get("hits", {}).get("hit", [])
    publications = []

    for hit in hits:
        info = hit.get("info", {})
        title = info.get("title")

        if not title:
            continue

        authors_raw = info.get("authors", {}).get("author", [])

        if isinstance(authors_raw, dict):
            authors = [authors_raw.get("text")]
        else:
            authors = [a.get("text") for a in authors_raw if "text" in a]

        authors = [a for a in authors if a]

        if authors:
            publications.append({
                "title": title.strip(),
                "authors": authors
            })

    return publications


# ------------------ DB helpers ------------------

def load_people(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM person")

    id_by_norm = {}
    name_by_id = {}

    for pid, name in cur.fetchall():
        norm = normalize_name(name)
        id_by_norm[norm] = pid
        name_by_id[pid] = name

    return id_by_norm, name_by_id


def find_person_id_fuzzy(name, id_by_norm):
    """
    Pokušaj pronaći osobu fuzzy matchom
    """
    for norm_name, pid in id_by_norm.items():
        if name_matches(name, norm_name):
            return pid
    return None


def get_or_create_paper(cur, title):
    cur.execute("SELECT id FROM paper WHERE title = ?", (title,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute("INSERT INTO paper (title) VALUES (?)", (title,))
    return cur.lastrowid


def authorship_exists(cur, person_id, paper_id):
    cur.execute(
        "SELECT 1 FROM authorship WHERE person_id = ? AND paper_id = ?",
        (person_id, paper_id)
    )
    return cur.fetchone() is not None


# ------------------ main logic ------------------

def populate_from_dblp():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cache = load_cache()

    id_by_norm, name_by_id = load_people(conn)

    print(f"[INFO] Loaded {len(id_by_norm)} people")

    for root_id, root_name in name_by_id.items():
        print(f"\n[DBLP] {root_name}")

        try:
            data = dblp_api_search(root_name, cache)
        except Exception as e:
            print(f"  ! API error: {e}")
            continue

        publications = parse_publications(data)

        for pub in publications:
            title = pub["title"]
            authors = pub["authors"]

            author_ids = []

            for a in authors:
                norm = normalize_name(a)

                if norm in id_by_norm:
                    author_ids.append(id_by_norm[norm])
                else:
                    pid = find_person_id_fuzzy(a, id_by_norm)
                    if pid:
                        author_ids.append(pid)

            if root_id not in author_ids:
                continue

            if len(author_ids) < 1:
                continue

            paper_id = get_or_create_paper(cur, title)

            for pid in author_ids:
                if not authorship_exists(cur, pid, paper_id):
                    cur.execute(
                        "INSERT INTO authorship (person_id, paper_id) VALUES (?, ?)",
                        (pid, paper_id)
                    )

        conn.commit()

    save_cache(cache)

    conn.close()
    print("\n[DONE] DBLP import finished.")


# ------------------ entry ------------------

if __name__ == "__main__":
    populate_from_dblp()