import ast
import io
import json
import re
import tokenize
from pathlib import PurePosixPath

from src.adapters.schemas.repository_assessment import AssessmentResult
from src.utils.errors import AssessmentError
from src.utils.rubric import CRITERIA_BY_ID
from src.workflow_agentic.guardrails.prompt_injection import (
    GUARDRAIL_VERSION, filter_content, model_repository_metadata, unsafe_path,
)
from src.workflow_agentic.tools.repository_tools import priority


SENSITIVE_ASSIGNMENT = re.compile(r"(?i)[\w-]*(api[_-]?key|secret|password|passwd|private[_-]?key|access[_-]?token|auth[_-]?token|credential)[\w-]*\s*[\"']?\s*[:=]\s*[\"'][^\"']+[\"']")
TOKEN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|https?://[^\s/:]+:[^\s/@]+@)")
DOCUMENTATION_SUFFIXES = {".md", ".rst", ".txt"}
RUNTIME_CONFIGURATION_SUFFIXES = DOCUMENTATION_SUFFIXES


class EvidenceValidationError(ValueError):
    """Evidence rejection with a safe reason suitable for logs and API metadata."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def safe_lines(content: str) -> dict[int, str]:
    result = {}
    in_key = False
    for number, line in enumerate(content.splitlines(), 1):
        if "-----BEGIN" in line and "PRIVATE KEY" in line:
            in_key = True
        if not in_key and not TOKEN.search(line) and not SENSITIVE_ASSIGNMENT.search(line):
            result[number] = line
        if "-----END" in line and "PRIVATE KEY" in line:
            in_key = False
    return result


def prepare_context(state: dict) -> tuple[str, dict, dict]:
    files = state["repository_files"]
    chunks = []
    presented = {}
    omitted = []
    blocked_lines = {}
    blocked_paths = []
    reasons = set()
    paths = sorted(files, key=lambda p: (not bool(state.get("content_hits", {}).get(p)), priority(p)))
    for path in paths:
        if unsafe_path(path):
            blocked_paths.append(path)
            omitted.append(path)
            reasons.add("unsafe_file_path")
            continue
        filtered = filter_content(files[path])
        if filtered.blocked:
            blocked_lines[path] = sorted(filtered.blocked)
            reasons.update(reason for codes in filtered.blocked.values() for reason in codes)
        lines = {number: text for number, text in safe_lines(files[path]).items() if number in filtered.lines}
        if any(text.strip() for text in lines.values()):
            presented[path] = lines
            chunks.append({"file": path, "lines": [{"line": n, "text": text} for n, text in lines.items()]})
        else:
            omitted.append(path)
    guardrail = {"version": GUARDRAIL_VERSION, "blocked_lines": blocked_lines,
                 "blocked_paths": blocked_paths, "reasons": sorted(reasons),
                 "removed_lines": sum(len(lines) for lines in blocked_lines.values()),
                 "removed_files": len(set(blocked_paths) | {p for p in blocked_lines if p not in presented})}
    coverage = {"presented": {p: sorted(lines) for p, lines in presented.items()},
                "files_presented": len(presented),
                "lines_presented": sum(len(lines) for lines in presented.values()),
                "omitted_from_prompt": omitted, "guardrail": guardrail}
    if not presented:
        error = (AssessmentError("PROMPT_INJECTION_BLOCKED", "O guardrail não encontrou conteúdo seguro suficiente para avaliar.", 422)
                 if reasons else AssessmentError("EMPTY_CONTEXT", "Nenhum trecho seguro disponível no contexto.", 422))
        error.coverage = coverage
        raise error
    context = {"type": "untrusted_repository_data",
               "repository": model_repository_metadata(state.get("repository_metadata", {})),
               "coverage_reduced_by_guardrail": bool(reasons), "files": chunks}
    return json.dumps(context, ensure_ascii=True), presented, coverage


def code_lines(path: str, content: str) -> set[int]:
    """Filter documentation, comment-only lines and Python docstrings."""
    if PurePosixPath(path).suffix.lower() in DOCUMENTATION_SUFFIXES:
        return set()
    if PurePosixPath(path).name.lower().startswith("readme"):
        return set()
    if path.endswith(".py"):
        try:
            tree = ast.parse(content)
            # A multiline prompt assigned to a variable is runtime configuration;
            # a standalone string/docstring is documentation.
            documentation = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    documentation.update(range(node.lineno, node.end_lineno + 1))
            tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            return {line for t in tokens if t.type not in {
                tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
                    and t.string.strip() for line in range(t.start[0], t.end[0] + 1)
                    if line not in documentation}
        except (tokenize.TokenError, SyntaxError):
            return set()
    result = set()
    in_block = False
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if in_block:
            if "*/" in stripped or "-->" in stripped:
                in_block = False
            continue
        if stripped.startswith(("/*", "<!--")):
            in_block = not ("*/" in stripped or "-->" in stripped)
            continue
        if stripped and not stripped.startswith(("#", "//", "--", "*", ";")):
            result.add(i)
    return result


def _normalized_line(line: str) -> str:
    return line.strip()


def _matching_ranges(evidence, presented: dict[int, str]) -> list[tuple[int, list[str]]]:
    requested = evidence.snippet.splitlines()
    if not requested:
        return []
    matches = []
    for start in sorted(presented):
        canonical = [presented.get(start + offset) for offset in range(len(requested))]
        if any(line is None for line in canonical):
            continue
        if all(_normalized_line(actual) == _normalized_line(expected)
               for actual, expected in zip(canonical, requested)):
            matches.append((start, canonical))
    return matches


def _canonicalize_evidence(evidence, presented: dict[str, dict[int, str]]):
    if evidence.file not in presented:
        raise EvidenceValidationError("evidence_file_not_presented")
    matches = _matching_ranges(evidence, presented[evidence.file])
    if not matches:
        raise EvidenceValidationError("evidence_snippet_not_found")

    claimed = next((match for match in matches if match[0] == evidence.line), None)
    if claimed is not None:
        selected = claimed
    elif len(matches) == 1:
        selected = matches[0]
    else:
        raise EvidenceValidationError("evidence_snippet_ambiguous")

    evidence.line = selected[0]
    evidence.snippet = "\n".join(selected[1])


def _is_runtime_configuration(path: str, files: dict[str, str], presented: dict) -> bool:
    """Accept text prompts only when executable code loads the exact repository path."""
    if PurePosixPath(path).suffix.lower() not in RUNTIME_CONFIGURATION_SUFFIXES:
        return False
    for source_path, content in files.items():
        if source_path == path:
            continue
        if not source_path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Static read operations only. A mention in print(), a comment, or
            # an unused path string does not establish a configuration load.
            argument = None
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                argument = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "file"), None)
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), ast.Constant("r"))
                if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str) or any(c in mode.value for c in "wax+"):
                    continue
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "read_text":
                receiver = node.func.value
                if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "Path" and receiver.args:
                    argument = receiver.args[0]
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                continue
            if str(PurePosixPath(argument.value)) != path:
                continue
            if all(line in presented.get(source_path, {}) for line in range(node.lineno, node.end_lineno + 1)):
                return True
    return False


def validate_evidence(result: AssessmentResult, criterion: str, presented: dict, files: dict):
    if result.criterion != criterion:
        raise EvidenceValidationError("criterion_mismatch")
    rubric = {question.id: question for question in CRITERIA_BY_ID[criterion].questions}
    for answer in result.questions:
        implementation = False
        for evidence in answer.evidence:
            _canonicalize_evidence(evidence, presented)
            if not evidence.snippet.strip():
                raise EvidenceValidationError("evidence_snippet_empty")
            lines = evidence.snippet.splitlines()
            positions = set(range(evidence.line, evidence.line + len(lines)))
            implementation |= bool(positions & code_lines(evidence.file, files[evidence.file])) or _is_runtime_configuration(evidence.file, files, presented)
        if answer.score > 0 and not rubric[answer.question_id].allow_documentation and not implementation:
            raise EvidenceValidationError("evidence_not_executable_or_integrated_configuration")
