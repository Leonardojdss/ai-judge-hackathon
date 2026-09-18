from conftest import FakeRepository
from src.workflow_agentic.context import build_context
from src.utils.errors import AssessmentError
import pytest


def test_selection_searches_content_and_follows_imports(settings):
    files = {"src/main.py": "from helpers import validate\nvalidate()\n",
             "helpers.py": "def validate():\n    timeout = 4\n    return timeout\n",
             "src/z.py": "x = 1\n", ".env": "API_KEY=never-read", "key.pem": "PRIVATE KEY",
             "node_modules/app.js": "x", "image.png": "binary"}
    provider = FakeRepository(files)
    state = build_context(provider, provider.get_file_tree(), {}, settings)
    assert provider.reads[:2] == ["src/main.py", "helpers.py"]
    assert state["content_hits"]["helpers.py"] == [1, 2, 3]
    assert set(state["repository_files"]) == {"src/main.py", "helpers.py", "src/z.py"}
    assert len(state["coverage"]["omitted"]) == 4


def test_file_count_size_and_total_budgets(settings):
    settings.MAX_FILES = 1
    settings.MAX_FILE_BYTES = 20
    provider = FakeRepository({"src/main.py": "print(1)", "big.py": "x" * 21, "small.py": "print(2)"})
    state = build_context(provider, provider.get_file_tree(), {}, settings)
    assert provider.reads == ["src/main.py"]
    assert len(state["coverage"]["omitted"]) == 2


def test_missing_readme_and_progressive_line_hits(settings):
    provider = FakeRepository({"main.py": "x = 0\n" * 100 + "retry = 3\n"})
    state = build_context(provider, provider.get_file_tree(), {}, settings)
    assert state["content_hits"]["main.py"] == [101]
    assert state["repository_files"]["main.py"].splitlines()[100] == "retry = 3"


@pytest.mark.parametrize("code,status", [("REPOSITORY_AUTH", 403), ("REPOSITORY_UNAVAILABLE", 502)])
def test_total_read_failure_keeps_external_error(settings, code, status):
    class Unreadable(FakeRepository):
        def read_file(self, path):
            raise AssessmentError(code, "Falha externa.", status)
    provider = Unreadable({"main.py": "print(42)"})
    with pytest.raises(AssessmentError) as caught:
        build_context(provider, provider.get_file_tree(), {}, settings)
    assert caught.value.http_status == status
