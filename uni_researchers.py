import requests
import csv
import time
from bs4 import BeautifulSoup
from collections import defaultdict

db = {}

def remove_title(name_with_titles):
    parts = name_with_titles.split()
    name = ""
    title = ""

    for part in parts:
        # first letter is upper (name/surname)
        if part[0].isupper():
            name += part + " "
        else:
            title += part + " "

    return name[:-1], title[:-1]


def find_gender(first_name, db):
    name = first_name.lower()
    return db.get(name, "unknown")

def load_name_database(db_path):
    temp = {}

    with open(db_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if not row:
                continue

            name = row[0].strip().lower()

            if len(row) > 1:
                g = row[1].strip().upper()
            else:
                g = ""

            # spremi u skup svih vrijednosti koje se jave
            if name not in temp:
                temp[name] = set()

            if g:
                temp[name].add(g)

    # Sad iz temp gradimo finalnu bazu
    db.clear()

    for name, genders in temp.items():
        if "M" in genders:
            db[name] = "M"
        elif "F" in genders:
            db[name] = "F"
        else:
            db[name] = "unknown"

def print_all(res_path):
    with open(res_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            print(
                f"ID: {r['id']}, "
                f"Name: {r['name']}, "
                f"Title: {r['title']}, "
                f"Gender: {r['gender']}, "
                f"Role: {r['role']}"
            )


def load_researchers(soup, csv_filename):
    # Find the table (there is only one big table on the page)
    table = soup.find("table")

    # Find all rows excluding header
    rows = table.find_all("tr")[1:]  # skip header row

    # Open CSV file for writing
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(["id", "name", "title", "gender", "role"])

        for row in rows:
            first_td = row.find("td")

            # Unique ID from HTML
            person_id = first_td.get("data-oznakanastavnik")

            # Extract all text columns
            cols = [td.get_text(strip=True) for td in row.find_all("td")]

            name, title = remove_title(cols[0])
            # Function for replacing all croatian symbols and dashes etc.
            name.replace("-", " ")
            
            first_name = name.split()[0]
            gender = find_gender(first_name, db)

            # Write row to CSV
            writer.writerow([
                person_id,
                name,
                title,
                gender,
                cols[2],  # role
            ])


def main():
    # to change uni, change ID number in URL, FER = 36
    URL = "https://www.isvu.hr/visokaucilista/hr/podaci/36/nastavnici/akademskagodina/2025"
    # first names data base to detect gender
    db_path = "./db/firstnames.csv"
    res_path = "./db/researchers.csv"
    resp = requests.get(URL)
    resp.raise_for_status()

    print("Status code:", resp.status_code)

    soup = BeautifulSoup(resp.text, "html.parser")

    load_name_database(db_path)
    load_researchers(soup, res_path)

    print_all(res_path)

if __name__ == "__main__":
    main()
