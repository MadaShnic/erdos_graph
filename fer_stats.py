import sqlite3
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_STATS = os.path.join(BASE_DIR, "db", "statistics.db")


def fetch_author_stats(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM author_stats")

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    return [dict(zip(columns, row)) for row in rows]


def median(values):
    values = sorted(values)
    n = len(values)

    if n == 0:
        return 0

    mid = n // 2

    if n % 2 == 0:
        return (values[mid - 1] + values[mid]) / 2
    else:
        return values[mid]


def compute_statistics(data):
    n = len(data)

    degrees = []
    clusterings = []
    papers = []
    centralities = []

    internal = 0
    external = 0
    balanced = 0

    for author in data:
        degree = author.get("degree")
        clustering = author.get("clustering")
        num_papers = author.get("total_papers")
        centrality = author.get("centrality")  # ili kako god se zove kod tebe
        collab = author.get("person_collab_type")

        if degree is not None:
            degrees.append(degree)

        if clustering is not None:
            clusterings.append(clustering)

        if num_papers is not None:
            papers.append(num_papers)

        if centrality is not None:
            centralities.append(centrality)

        if collab == "internal":
            internal += 1
        elif collab == "external":
            external += 1
        elif collab == "balanced":
            balanced += 1

    stats = {
        "n": n,

        "avg_degree": sum(degrees) / len(degrees) if degrees else 0,
        "median_degree": median(degrees),

        "avg_clustering": sum(clusterings) / len(clusterings) if clusterings else 0,
        "median_clustering": median(clusterings),

        "total_papers": sum(papers),
        "avg_papers": sum(papers) / len(papers) if papers else 0,
        "median_papers": median(papers),

        "avg_centrality": sum(centralities) / len(centralities) if centralities else 0,
        "median_centrality": median(centralities),

        "internal": internal,
        "external": external,
        "balanced": balanced,
    }

    return stats


def print_statistics(stats):
    n = stats["n"]

    internal_pct = (stats["internal"] / n * 100) if n else 0
    external_pct = (stats["external"] / n * 100) if n else 0
    balanced_pct = (stats["balanced"] / n * 100) if n else 0

    print("=== FER GLOBALNA STATISTIKA ===\n")

    print(f"Broj autora: {n}\n")

    print("— MREŽNE METRIKE —")
    print(f"Prosječni degree: {stats['avg_degree']:.4f}")
    print(f"Medijan degree: {stats['median_degree']:.4f}")
    print(f"Prosječni clustering: {stats['avg_clustering']:.4f}")
    print(f"Medijan clustering: {stats['median_clustering']:.4f}")
    print(f"Prosječni centrality: {stats['avg_centrality']:.4f}")
    print(f"Medijan centrality: {stats['median_centrality']:.4f}\n")

    print("— RADOVI —")
    print(f"Ukupno radova: {stats['total_papers']}")
    print(f"Prosjek radova po autoru: {stats['avg_papers']:.4f}")
    print(f"Medijan radova po autoru: {stats['median_papers']:.4f}\n")

    print("— SURADNJA —")
    print(f"internal: {stats['internal']} ({internal_pct:.2f}%)")
    print(f"external: {stats['external']} ({external_pct:.2f}%)")
    print(f"balanced: {stats['balanced']} ({balanced_pct:.2f}%)")


def main():
    conn = sqlite3.connect(DB_STATS)

    try:
        data = fetch_author_stats(conn)
        stats = compute_statistics(data)
        print_statistics(stats)
    finally:
        conn.close()


if __name__ == "__main__":
    main()