from conftest import FakeRepository
from src.workflow_agentic.context import build_context
from src.utils.errors import AssessmentError
import pytest


def test_selection_searches_content_and_follows_imports():
    files = {"src/main.py": "from helpers import validate\nvalidate()\n",
             "helpers.py": "def validate():\n    timeout = 4\n    return timeout\n",
             "src/z.py": "x = 1\n", ".env": "API_KEY=never-read", "key.pem": "PRIVATE KEY",
             "node_modules/app.js": "x", "image.png": "binary"}
    provider = FakeRepository(files)
    state = build_context(provider, provider.get_file_tree(), {})
    assert provider.reads[:2] == ["src/main.py", "helpers.py"]
    assert state["content_hits"]["helpers.py"] == [1, 2, 3]
    assert set(state["repository_files"]) == {"src/main.py", "helpers.py", "src/z.py"}
    assert len(state["coverage"]["omitted"]) == 4


def test_all_eligible_files_are_read_without_size_or_count_limits():
    provider = FakeRepository({"src/main.py": "print(1)", "big.py": "x" * 21, "small.py": "print(2)"})
    state = build_context(provider, provider.get_file_tree(), {})
    assert provider.reads == ["src/main.py", "big.py", "small.py"]
    assert set(state["repository_files"]) == {"src/main.py", "big.py", "small.py"}
    assert state["coverage"]["omitted"] == []


def test_missing_readme_and_progressive_line_hits():
    provider = FakeRepository({"main.py": "x = 0\n" * 100 + "retry = 3\n"})
    state = build_context(provider, provider.get_file_tree(), {})
    assert state["content_hits"]["main.py"] == [101]
    assert state["repository_files"]["main.py"].splitlines()[100] == "retry = 3"


def test_data_and_evaluation_artifacts_are_read_as_text_without_execution():
    from src.workflow_agentic.agents.evidence import prepare_context

    files = {
        "data/samples.csv": "question,answer\nExample,Expected\n",
        "data/samples.tsv": "question\tanswer\nExample\tExpected\n",
        "evaluation/results.jsonl": '{"accuracy": 0.8}\n',
        "evaluation/cases.ndjson": '{"scenario": "failure"}\n',
        "evaluation/report.ipynb": '{"cells": [{"cell_type": "code", "source": ["raise RuntimeError()"]}]}',
        "data/image.png": "binary",
        ".env": "API_KEY=never-read",
    }
    provider = FakeRepository(files)
    state = build_context(provider, provider.get_file_tree(), {})
    expected = set(files) - {"data/image.png", ".env"}
    assert set(provider.reads) == expected
    assert state["repository_files"]["evaluation/report.ipynb"] == files["evaluation/report.ipynb"]
    _, presented, _ = prepare_context({**state, "repository_metadata": {}})
    assert set(presented) == expected


@pytest.mark.parametrize("code,status", [("REPOSITORY_AUTH", 403), ("REPOSITORY_UNAVAILABLE", 502)])
def test_total_read_failure_keeps_external_error(code, status):
    class Unreadable(FakeRepository):
        def read_file(self, path):
            raise AssessmentError(code, "Falha externa.", status)
    provider = Unreadable({"main.py": "print(42)"})
    with pytest.raises(AssessmentError) as caught:
        build_context(provider, provider.get_file_tree(), {})
    assert caught.value.http_status == status
