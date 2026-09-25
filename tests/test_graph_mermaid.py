from langchain_core.runnables.graph import Graph

from src.utils.graph_mermaid import generate_graph_png


def test_graph_png_is_generated_from_the_real_graph(tmp_path, monkeypatch):
    image = b"\x89PNG\r\n\x1a\nrendered"
    options = {}

    def render(self, **kwargs):
        options.update(kwargs)
        return image

    monkeypatch.setattr(Graph, "draw_mermaid_png", render)
    destination = tmp_path / "assessment.png"

    result = generate_graph_png(destination)

    assert result == destination
    assert destination.read_bytes() == image
    assert options == {"max_retries": 5, "retry_delay": 2.0}
