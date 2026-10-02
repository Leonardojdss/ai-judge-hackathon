import re
from pathlib import PurePosixPath


EXCLUDED_DIRS = {".git", "node_modules", "vendor", "venv", ".venv", "env", "dist", "build", "__pycache__", ".next", "coverage", ".terraform", ".ssh"}
TEST_DIRS = {"test", "tests", "__tests__", "e2e", "spec", "specs", "integration-tests", "unit-tests"}
TEST_CONFIG_FILES = {
    ".coveragerc", "jest.config.js", "jest.config.ts", "playwright.config.js",
    "playwright.config.ts", "pytest.ini", "tox.ini", "vitest.config.js",
    "vitest.config.ts",
}
TEST_FILE = re.compile(
    r"(?:^test_|^tests?\.|^conftest\.py$|_(?:tests?|spec)\.[^.]+$|\.(?:test|spec)\.[^.]+$)",
    re.I,
)
PASCAL_CASE_TEST_FILE = re.compile(r"(?:Test|Tests|Spec)\.(?:java|kt|cs|swift)$")
DATA_ARTIFACT_EXTENSIONS = {
    ".arrow", ".avro", ".csv", ".db", ".dmp", ".dump", ".duckdb",
    ".feather", ".jsonl", ".ndjson", ".ods", ".orc", ".parquet",
    ".sqlite", ".sqlite3", ".sql", ".tsv", ".xls", ".xlsb", ".xlsm",
    ".xlsx",
}
TEXT_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".xml", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".sh", ".tf", ".md", ".rst", ".txt", ".properties", ".swift", ".c", ".h", ".cpp", ".vue", ".svelte", ".gradle", ".ipynb"}
TERMS = re.compile(r"retry|timeout|guardrail|moderation|safety|sanitize|exception|middleware|logging|telemetry|trace|circuit.?breaker|fallback|rate.?limit|validate|idempot|pagination|batch|cache|queue|dataset|leakage|bias|benchmark|accuracy|precision|recall|evaluation|token|latency|cost|jailbreak", re.I)


def exclusion_reason(path: str) -> str | None:
    p = PurePosixPath(path)
    name = p.name.lower()
    if any(part.lower() in EXCLUDED_DIRS for part in p.parts):
        return "excluded_directory"
    if (any(part.lower() in TEST_DIRS for part in p.parts[:-1])
            or name in TEST_CONFIG_FILES or TEST_FILE.search(name)
            or PASCAL_CASE_TEST_FILE.search(p.name)):
        return "test_artifact"
    if name.startswith(".env") and not name.endswith((".example", ".sample", ".template")):
        return "credentials"
    if p.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".keystore"} or name in {"credentials", "credentials.json", "secrets.json", "secrets.yaml", ".netrc", ".npmrc", "id_rsa", "id_ed25519"}:
        return "credentials"
    if p.suffix.lower() in DATA_ARTIFACT_EXTENSIONS:
        return "data_artifact"
    if name.endswith((".lock", "-lock.json", ".min.js", ".map")):
        return "generated"
    if p.suffix.lower() not in TEXT_EXTENSIONS and name not in {"dockerfile", "makefile", "readme", ".gitignore", ".env.example", ".env.sample", ".env.template"}:
        return "unsupported_or_binary"
    return None


def priority(path: str) -> tuple[int, int, str]:
    p = PurePosixPath(path)
    name = p.name.lower()
    if name.startswith("readme") or name in {"pyproject.toml", "requirements.txt", "package.json", "dockerfile", "docker-compose.yml", "makefile", ".env.example"}:
        rank = 0
    elif p.stem.lower() in {"main", "app", "index", "server", "startup", "program", "graph"}:
        rank = 1
    elif TERMS.search(path):
        rank = 2
    elif any(part in {"src", "app", "agents", "nodes", "providers", "services", "config", "tests"} for part in p.parts):
        rank = 3
    else:
        rank = 4
    return rank, len(p.parts), path


def imported_paths(path: str, content: str, available: set[str]) -> set[str]:
    """Follow Python/JS imports without loading or executing repository code."""
    modules = re.findall(r"(?:from\s+|import\s+)[\"']?([.\w/-]+)", content)
    modules += re.findall(r"(?:require\(|from\s*)[\"']([^\"']+)", content)
    found = set()
    for module in modules:
        candidates = {module.replace(".", "/") if "/" not in module else module}
        if module.startswith("."):
            relative = module if "/" in module else module.lstrip(".").replace(".", "/")
            candidates.add(str(PurePosixPath(path).parent / relative))
        for stem in candidates:
            # Normalize relative JS imports without accessing the local filesystem.
            parts = []
            for part in PurePosixPath(stem).parts:
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            stem = "/".join(parts)
            for suffix in ("", ".py", "/__init__.py", ".ts", ".js", "/index.ts", "/index.js"):
                if stem + suffix in available:
                    found.add(stem + suffix)
    return found


def read_repository_file(provider, path: str) -> str:
    """Production uses the notebook toolkit, constrained by the provider."""
    return provider.tools["read_file"].invoke({"formatted_filepath": path})
