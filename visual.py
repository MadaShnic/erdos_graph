from dash import Dash, dcc, html, Input, Output
import networkx as nx
import plotly.graph_objects as go

def run_dash_app(graph, levels, root_author):
    app = Dash(__name__)

    # NetworkX graf
    G = nx.Graph()
    for a, coauthors in graph.items():
        for c in coauthors:
            G.add_edge(a, c)

    pos = nx.spring_layout(G, k=1.2, iterations=100, seed=42)

    app.layout = html.Div([
        html.H2(f"Erdős Coauthor Graph – {root_author}"),
        dcc.Graph(
            id="graph",
            figure=make_figure(G, pos, levels, root_author),
            clear_on_unhover=True,
            style={"height": "90vh"}  # 90% visine prozora
        )
    ])

    @app.callback(
        Output("graph", "figure"),
        Input("graph", "hoverData")
    )
    def highlight_subgraph(hoverData):
        if hoverData is None:
            return make_figure(G, pos, levels, root_author)
        
        point_data = hoverData["points"][0]
        # provjera postoji li customdata
        if "customdata" not in point_data:
            return make_figure(G, pos, levels, root_author)
        
        if point_data["curveNumber"] != 1:  # 1 je indeks node_trace u fig.data
            return make_figure(G, pos, levels, root_author)

        node = point_data["customdata"]
        neighbors = set(G.neighbors(node)) | {node}
        return make_figure(
            G, pos, levels, root_author,
            highlight_nodes=neighbors
        )

    app.run(debug=True)


def make_figure(G, pos, levels, root_author, highlight_nodes=None):
    edge_x = []
    edge_y = []
    edge_opacity = []

    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

        if highlight_nodes:
            if u in highlight_nodes and v in highlight_nodes:
                edge_opacity.append(1.0)
            else:
                edge_opacity.append(0.05)
        else:
            edge_opacity.append(0.5)

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        opacity=1.0
    )

    node_x = []
    node_y = []
    node_color = []
    node_opacity = []
    hover_text = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        level = levels.get(node, "?")
        hover_text.append(
            f"<b>{node}</b><br>"
            f"Erdős level: {level}<br>"
            f"Degree: {G.degree[node]}"
        )

        if node == root_author:
            node_color.append("red")
        elif level == 1:
            node_color.append("skyblue")
        else:
            node_color.append("lightgreen")

        if highlight_nodes:
            node_opacity.append(1.0 if node in highlight_nodes else 0.1)
        else:
            node_opacity.append(1.0)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=list(G.nodes()),
        customdata=list(G.nodes()),  # 👈 BITNO
        textposition="top center",
        hoverinfo="text",
        hovertext=hover_text,
        marker=dict(
            size=20,
            color=node_color,
            opacity=node_opacity,
            line=dict(width=2)
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        hovermode="closest",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig
