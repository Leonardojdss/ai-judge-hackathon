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


def test_data_artifacts_are_excluded_before_reading():
    from src.workflow_agentic.agents.evidence import prepare_context

    files = {
        "data/samples.csv": "question,answer\nExample,Expected\n",
        "data/samples.tsv": "question\tanswer\nExample\tExpected\n",
        "data/workbook.xlsx": "not-read",
        "data/warehouse.parquet": "not-read",
        "database/schema.sql": "CREATE TABLE example (id INT);",
        "database/local.sqlite": "not-read",
        "evaluation/results.jsonl": '{"accuracy": 0.8}\n',
        "evaluation/cases.ndjson": '{"scenario": "failure"}\n',
        "evaluation/report.ipynb": '{"cells": [{"cell_type": "code", "source": ["raise RuntimeError()"]}]}',
        "data/image.png": "binary",
        ".env": "API_KEY=never-read",
    }
    provider = FakeRepository(files)
    state = build_context(provider, provider.get_file_tree(), {})
    expected = {"evaluation/report.ipynb"}
    assert set(provider.reads) == expected
    assert state["repository_files"]["evaluation/report.ipynb"] == files["evaluation/report.ipynb"]
    assert {item["reason"] for item in state["coverage"]["omitted"]} == {
        "credentials", "data_artifact", "unsupported_or_binary",
    }
    _, presented, _ = prepare_context({**state, "repository_metadata": {}})
    assert set(presented) == expected


def test_excluded_initial_data_artifact_does_not_enter_context():
    provider = FakeRepository({
        "dataset.csv": "large,data\n",
        "src/main.py": "print('ready')\n",
    })
    state = build_context(
        provider,
        provider.get_file_tree(),
        {"dataset.csv": provider.files["dataset.csv"]},
    )

    assert provider.reads == ["src/main.py"]
    assert state["repository_files"] == {"src/main.py": "print('ready')\n"}


@pytest.mark.parametrize("path", [
    "tests/test_service.py",
    "test/unit/service_test.go",
    "src/__tests__/service.test.ts",
    "e2e/login.spec.js",
    "src/test_repository.py",
    "src/repository_test.py",
    "lib/user_spec.rb",
    "src/repository.spec.ts",
    "src/ServiceTest.java",
    "spec/services/user_spec.rb",
    "conftest.py",
    "pytest.ini",
    "playwright.config.ts",
])
def test_test_artifacts_are_excluded_before_reading(path):
    provider = FakeRepository({path: "must not be read", "src/main.py": "print('ready')"})

    state = build_context(provider, provider.get_file_tree(), {})

    assert provider.reads == ["src/main.py"]
    assert state["repository_files"] == {"src/main.py": "print('ready')"}
    omitted = {item["file"]: item["reason"] for item in state["coverage"]["omitted"]}
    assert omitted[path] == "test_artifact"


@pytest.mark.parametrize("code,status", [("REPOSITORY_AUTH", 403), ("REPOSITORY_UNAVAILABLE", 502)])
def test_total_read_failure_keeps_external_error(code, status):
    class Unreadable(FakeRepository):
        def read_file(self, path):
            raise AssessmentError(code, "Falha externa.", status)
    provider = Unreadable({"main.py": "print(42)"})
    with pytest.raises(AssessmentError) as caught:
        build_context(provider, provider.get_file_tree(), {})
    assert caught.value.http_status == status
