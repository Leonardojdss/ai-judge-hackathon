import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config.settings import Settings
from src.utils.errors import AssessmentError


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, ASSESSMENT_OUTPUT_DIR=tmp_path / "results",
                    RETRY_DELAY=0, OPENAI_API_KEY="test-only", LLM_MODEL="test-model")


class FakeRepository:
    def __init__(self, files=None, failure=None):
        self.files = files or {"src/main.py": "def main():\n    return 42\n", "README.md": "# Example\n"}
        self.failure = failure
        self.tree_truncated = False
        self.reads = []
        self.closed = False
        self.tools = {"read_file": SimpleNamespace(invoke=lambda args: self.read_file(args["formatted_filepath"]))}

    def get_repository_metadata(self):
        if self.failure:
            raise self.failure
        return {"name": "owner/repo", "url": "https://github.com/owner/repo", "commit": "a" * 40}

    def get_file_tree(self):
        return [{"path": p, "size": len(t.encode()), "mode": "100644"} for p, t in self.files.items()]

    def get_readme(self):
        return ("README.md", self.files["README.md"]) if "README.md" in self.files else (None, None)

    def read_file(self, path):
        self.reads.append(path)
        return self.files[path]

    def close(self):
        self.closed = True


def assessment_result(criterion, score=0, file="src/main.py", snippet="def main():", line=1):
    evidence = [{"file": file, "description": "Implementação concreta observada.", "line": line, "snippet": snippet}] if score else []
    return {"criterion": criterion, "score": score,
            "status": ["does_not_meet", "partially_meets", "meets"][score],
            "summary": "Resultado limitado aos arquivos analisados.", "evidence": evidence,
            "recommendations": ["Ampliar testes."],
            "mechanisms": [{"mechanism": "validation", "implemented": True, "evidence": evidence}] if criterion == "engineering_mechanisms" and score else []}


class FakeAgents:
    def __init__(self, fail=(), barrier=False):
        self.fail = fail
        self.calls = []
        self.barrier = barrier
        self.ready = asyncio.Event()
        self.finished = []

    async def evaluate(self, criterion, prompt, state):
        self.calls.append(criterion)
        if len(self.calls) == 3:
            self.ready.set()
        if self.barrier:
            await asyncio.wait_for(self.ready.wait(), timeout=2)
        self.finished.append(criterion)
        if criterion in self.fail:
            raise AssessmentError("MODEL_ERROR", "Falha controlada.")
        return {"result": assessment_result(criterion), "coverage": {"presented": {"src/main.py": [1, 2]}}}


def fixture_files(maturity):
    root = Path(__file__).parent / "fixtures" / maturity
    return {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*") if p.is_file()}
