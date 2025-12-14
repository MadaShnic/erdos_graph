import requests
from bs4 import BeautifulSoup
import csv
import unicodedata
from collections import deque, defaultdict
import networkx as nx
import plotly.graph_objects as go
import plotly.io as pio
from plotly.graph_objs import FigureWidget
import visual

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
        authors = [a.get_text(strip=True) for a in item.select("span[itemprop='author']")]
        publications.append({
            "title": title,
            "authors": authors,
            "link": link
        })
    return publications

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

def plot_interactive_graph(graph, levels, root_author):
    G = nx.Graph()
    for author, coauthors in graph.items():
        for coauthor in coauthors:
            G.add_edge(author, coauthor)
    
    pos = nx.spring_layout(G, k=1.2, iterations=100, seed=42)

    # edges
    edge_x = []
    edge_y = []
    edge_pairs = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        edge_pairs.append(edge)

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="#888"),
        hoverinfo="none",
        mode="lines",
        opacity=0.5
    )

    # nodes
    node_x = []
    node_y = []
    hover_text = []
    node_color = []
    nodes = list(G.nodes())
    for node in nodes:
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        hover_text.append(
            f"{node}<br>Level: {levels.get(node, 1)}<br>Degree: {G.degree[node]}"
        )
        if node == root_author:
            node_color.append("red")
        elif levels.get(node, 1) == 1:
            node_color.append("skyblue")
        else:
            node_color.append("lightgreen")

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=nodes,
        textposition="top center",
        hoverinfo="text",
        hovertext=hover_text,
        marker=dict(
            color=node_color,
            size=20,
            line_width=2,
            opacity=1.0
        )
    )

    fig = FigureWidget(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=f"Interactive Coauthor Graph for {root_author}",
            showlegend=False,
            hovermode="closest"
        )
    )

    # adjacency
    adjacency = {n: set(G.neighbors(n)) for n in G.nodes()}

    def on_hover(trace, points, state):
        if not points.point_inds:
            return
        idx = points.point_inds[0]
        hovered = nodes[idx]
        neighbors = adjacency[hovered] | {hovered}
        fig.data[1].marker.opacity = [
            1.0 if n in neighbors else 0.1 for n in nodes
        ]
        edge_opacity = []
        for a, b in edge_pairs:
            if a in neighbors and b in neighbors:
                edge_opacity.append(1.0)
            else:
                edge_opacity.append(0.05)
        fig.data[0].line.opacity = edge_opacity

    def on_unhover(trace, points, state):
        fig.data[1].marker.opacity = 1.0
        fig.data[0].line.opacity = 0.5

    node_trace.on_hover(on_hover)
    node_trace.on_unhover(on_unhover)

    pio.renderers.default = "browser"
    fig.write_html("erdos_graph.html", auto_open=True)

def main():
    root_author = "Anamari Nakić"
    max_depth = 3
    # load researcher names from CSV
    researcher_names = load_researcher_names("./db/researchers.csv")
    # build coauthor graph
    graph, levels = build_coauthor_graph(root_author, max_depth, researcher_names)
    # draw graph
    visual.run_dash_app(graph, levels, root_author)

if __name__ == "__main__":
    main()
