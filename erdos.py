import requests
from bs4 import BeautifulSoup
import csv
import unicodedata
from collections import deque, defaultdict
import networkx as nx
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.io as pio


def normalize_name(name: str) -> str:
    """
    Uklanja dijakritike, mijenja '-' u razmak i spušta u lowercase.
    Nakić -> nakic
    Mario-Osvin Pavcevic -> mario osvin pavcevic
    """
    name = name.replace("-", " ")

    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

def load_researcher_names(csv_filename="researchers.csv"):
    names = set()
    with open(csv_filename, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            names.add(normalize_name(row["name"]))
    return names

def print_publications_with_known_coauthors(publications, researcher_names, root_author):
    root_norm = normalize_name(root_author)

    for pub in publications:
        matched_authors = []

        for author in pub["authors"]:
            norm_author = normalize_name(author)

            # preskoči root autora
            if norm_author == root_norm:
                continue

            if norm_author in researcher_names:
                matched_authors.append(author)

        # ispiši karticu samo ako postoji barem jedan poznati koautor
        if matched_authors:
            print("Title:", pub["title"])
            print("Authors:", ", ".join(pub["authors"]))
            print("Matched researchers:", ", ".join(matched_authors))
            print("Link:", pub["link"])
            print("-" * 50)


def dblp_html_search(name: str):
    # DBLP HTML search URL
    url = "https://dblp.org/search?q=" + requests.utils.quote(name)
    resp = requests.get(url)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")

    # div koji sadrži sve publikacije
    publs_div = soup.find("div", id="completesearch-publs")
    if not publs_div:
        print("Nema 'completesearch-publs' — autor možda ne postoji ili nema radove.")
        return None

    return publs_div

def parse_publications(publs_div):
    # dohvaća sve <li> elemente koji predstavljaju radove
    items = publs_div.find_all("li", class_="entry")
    
    publications = []
    for item in items:
        # naslov
        title_tag = item.find("span", class_="title")
        title = title_tag.get_text(strip=True) if title_tag else "(no title)"

        # link (prvi href unutar <li>)
        link_tag = item.find("a", href=True)
        link = link_tag["href"] if link_tag else None

        # autori
        authors = [a.get_text(strip=True) 
                   for a in item.select("span[itemprop='author']")]

        publications.append({
            "title": title,
            "authors": authors,
            "link": link
        })
    
    return publications


def build_erdos_graph(root_author, researcher_names, MAX_DEPTH):
    visited = set()
    erdos_level = dict()

    queue = deque()
    queue.append((root_author, 0))

    root_norm = normalize_name(root_author)
    visited.add(root_norm)
    erdos_level[root_author] = 0

    while queue:
        current_author, depth = queue.popleft()

        if depth >= MAX_DEPTH:
            continue

        publs_div = dblp_html_search(current_author)
        if not publs_div:
            continue

        publications = parse_publications(publs_div)

        for pub in publications:
            for author in pub["authors"]:
                norm_author = normalize_name(author)

                # preskoči samog sebe i već obrađene
                if norm_author == normalize_name(current_author):
                    continue
                if norm_author in visited:
                    continue
                if norm_author not in researcher_names:
                    continue

                visited.add(norm_author)
                erdos_level[author] = depth + 1
                queue.append((author, depth + 1))

    return erdos_level

def print_erdos_graph(erdos_level):
    levels = defaultdict(list)

    for author, level in erdos_level.items():
        levels[level].append(author)

    for level in sorted(levels.keys()):
        print(f"\nErdos distance {level}:")
        for author in sorted(levels[level]):
            print(f"  {author}")
# vizualno

def build_coauthor_graph(root_author, max_depth, researcher_names):
    """
    BFS pretraga koautora do dubine max_depth.
    Vraća:
        - graf kao dict: ključ=autor, vrijednost=set koautora
        - levels dict: ključ=autor, vrijednost=stupanj (0=root, 1=direktni koautori, ...)
    """
    graph = {}  # adjacency list
    levels = {root_author: 0}
    visited = set([normalize_name(root_author)])
    
    queue = deque([(root_author, 0)])

    while queue:
        author, depth = queue.popleft()
        if depth >= max_depth:
            continue

        publs_div = dblp_html_search(author)
        if not publs_div:
            continue

        publications = parse_publications(publs_div)

        coauthors_set = set()
        for pub in publications:
            for a in pub["authors"]:
                norm_a = normalize_name(a)
                # preskoči root i filtriraj po researchers.csv
                if norm_a == normalize_name(root_author) or norm_a not in researcher_names:
                    continue
                coauthors_set.add(a)
        
        graph[author] = coauthors_set

        # dodaj nove coautore u queue
        for coauthor in coauthors_set:
            norm_coauthor = normalize_name(coauthor)
            if norm_coauthor not in visited:
                visited.add(norm_coauthor)
                levels[coauthor] = depth + 1
                queue.append((coauthor, depth + 1))

    return graph, levels

def build_graph(root_author, publications, researcher_names):
    """
    Kreira NetworkX graf:
    - čvorovi: autori
    - bridovi: suradnja
    - zadržava samo autori iz researcher_names
    """
    G = nx.Graph()
    root_norm = normalize_name(root_author)

    # Dodaj root autora
    G.add_node(root_author, level=0)

    for pub in publications:
        # filtriraj koautore koji su u researchers.csv i nisu root
        coauthors = [
            a for a in pub["authors"]
            if normalize_name(a) in researcher_names and normalize_name(a) != root_norm
        ]

        # dodaj čvorove i bridove
        for coauthor in coauthors:
            G.add_node(coauthor)  # NetworkX automatski ignorira duplikate
            G.add_edge(root_author, coauthor)

    return G

def draw_graph_from_dict(graph, levels, root_author):
    G = nx.Graph()
    
    # dodaj čvorove i bridove
    for author, coauthors in graph.items():
        G.add_node(author, level=levels.get(author, 1))
        for coauthor in coauthors:
            G.add_node(coauthor, level=levels.get(coauthor, 1))
            G.add_edge(author, coauthor)
    
    # spring layout s većim k za udaljenije čvorove
    pos = nx.spring_layout(G, k=1.2, iterations=100, seed=42)

    # boje po stupnju
    colors = []
    for node in G.nodes():
        if node == root_author:
            colors.append("red")
        else:
            level = levels.get(node, 1)
            if level == 1:
                colors.append("skyblue")
            else:
                colors.append("lightgreen")

    plt.figure(figsize=(20, 16))  # povećana figura
    nx.draw(
        G, pos,
        with_labels=True,
        node_color=colors,
        node_size=2500,  # veći čvorovi
        font_size=12,    # veći font
        font_weight="bold",
        edge_color="gray",
        linewidths=1,
        alpha=0.9
    )
    plt.title(f"Coauthor graph for {root_author}", fontsize=18)
    plt.tight_layout()
    plt.savefig("coauthor_graph_large.png", dpi=300)
    plt.close()

def plot_interactive_graph(graph, levels, root_author):
    G = nx.Graph()
    for author, coauthors in graph.items():
        for coauthor in coauthors:
            G.add_edge(author, coauthor)
    
    pos = nx.spring_layout(G, k=1.2, iterations=100, seed=42)
    
    # priprema podataka za Plotly
    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines'
    )

    node_x = []
    node_y = []
    hover_text = []
    node_color = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        hover_text.append(f"{node}<br>Level: {levels.get(node, 1)}<br>Degree: {G.degree[node]}")
        if node == root_author:
            node_color.append('red')
        elif levels.get(node,1) == 1:
            node_color.append('skyblue')
        else:
            node_color.append('lightgreen')

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[node for node in G.nodes()],
        textposition='top center',
        hoverinfo='text',
        hovertext=hover_text,
        marker=dict(
            color=node_color,
            size=20,
            line_width=2
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title=f"Interactive Coauthor Graph for {root_author}",
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20,l=5,r=5,t=40)
                    ))
    pio.renderers.default = "browser"
    fig.show()

def main():
    root_author = "Anamari Nakić"
    max_depth = 3

    # load researcher names from CSV
    researcher_names = load_researcher_names("./db/researchers.csv")

    # build coauthor graph
    graph, levels = build_coauthor_graph(root_author, max_depth, researcher_names)

    # draw graph
    # draw_graph_from_dict(graph, levels, root_author)
    plot_interactive_graph(graph, levels, root_author)


if __name__ == "__main__":
    main()
