import sqlite3
import requests
import time
import random
import unicodedata

DB_PATH = "db\\erdos.db"


# ------------------ utils ------------------

def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace("-", " ")
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

def dblp_api_search(
    name: str,
    max_hits=1000,
    initial_delay=2,
    max_delay=64,
    max_retries=10
):
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
            # mali jitter da ne pucaš točno u istim intervalima
            time.sleep(delay + random.uniform(0.0, 0.5))

            r = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Academic research (Erdos graph)"},
                timeout=30
            )

            # ---------------- SUCCESS ----------------
            if r.status_code == 200:
                return r.json()

            # ---------------- RATE LIMIT ----------------
            if r.status_code == 429:
                retries += 1
                if retries > max_retries:
                    raise RuntimeError(
                        f"Too many retries (429) for '{name}'"
                    )

                print(
                    f"  [429] Rate limited for '{name}', "
                    f"retry in {delay}s (attempt {retries})"
                )

                delay = min(delay * 2, max_delay)
                continue

            # ---------------- OTHER ERRORS ----------------
            r.raise_for_status()

        except requests.RequestException as e:
            retries += 1
            if retries > max_retries:
                raise RuntimeError(
                    f"Request failed too many times for '{name}': {e}"
                )

            print(
                f"  [ERROR] {e}, retry in {delay}s "
                f"(attempt {retries})"
            )
            delay = min(delay * 2, max_delay)

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
    """
    Returns:
    - id_by_norm_name : dict normalized_name -> person_id
    - name_by_id     : dict person_id -> full_name
    """
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM person")

    id_by_norm = {}
    name_by_id = {}

    for pid, name in cur.fetchall():
        norm = normalize_name(name)
        id_by_norm[norm] = pid
        name_by_id[pid] = name

    return id_by_norm, name_by_id


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

    id_by_norm, name_by_id = load_people(conn)

    print(f"[INFO] Loaded {len(id_by_norm)} people from database")

    for root_id, root_name in name_by_id.items():
        print(f"\n[DBLP] Processing: {root_name}")

        try:
            data = dblp_api_search(root_name)
        except Exception as e:
            print(f"  ! API error: {e}")
            continue

        publications = parse_publications(data)

        for pub in publications:
            title = pub["title"]
            authors = pub["authors"]

            # keep only authors that exist in OUR database
            author_ids = []
            for a in authors:
                norm = normalize_name(a)
                if norm in id_by_norm:
                    author_ids.append(id_by_norm[norm])

            # skip papers where root author is not actually included
            if root_id not in author_ids:
                continue

            # skip solo papers with external authors only
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

    conn.close()
    print("\n[DONE] DBLP import finished.")


# ------------------ entry ------------------

if __name__ == "__main__":
    populate_from_dblp()
