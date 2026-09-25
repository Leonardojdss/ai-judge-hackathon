"""Generate a PNG image from the repository assessment LangGraph."""

from pathlib import Path

from src.workflow_agentic.graph import build_repository_assessment_graph


OUTPUT_PATH = Path("docs/repository-assessment-graph.png")


def generate_graph_png(output: Path = OUTPUT_PATH) -> Path:
    """Compile the production graph and save its Mermaid rendering as PNG."""
    graph = build_repository_assessment_graph(
        provider=None,
        agents=None,
        store=None,
        settings=None,
    ).compile()
    image = graph.get_graph().draw_mermaid_png(
        max_retries=5,
        retry_delay=2.0,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return output


if __name__ == "__main__":
    print(generate_graph_png())
