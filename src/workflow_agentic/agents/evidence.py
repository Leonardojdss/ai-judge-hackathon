import io
import json
import re
import tokenize
from pathlib import PurePosixPath

from src.adapters.schemas.repository_assessment import AssessmentResult
from src.utils.errors import AssessmentError
from src.workflow_agentic.tools.repository_tools import priority


SENSITIVE_ASSIGNMENT = re.compile(r"(?i)[\w-]*(api[_-]?key|secret|password|passwd|private[_-]?key|access[_-]?token|auth[_-]?token|credential)[\w-]*\s*[\"']?\s*[:=]\s*[\"'][^\"']+[\"']")
TOKEN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|https?://[^\s/:]+:[^\s/@]+@)")


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


def prepare_context(state: dict, prompt: str, settings) -> tuple[str, dict, dict]:
    # UTF-8 bytes are a deliberately conservative token upper bound for code.
    # Include the output schema and message framing in the input budget.
    overhead = len(prompt.encode()) + len(json.dumps(AssessmentResult.model_json_schema()).encode()) + 512
    remaining = settings.INPUT_TOKEN_BUDGET - overhead
    if remaining < 128:
        raise AssessmentError("CONTEXT_BUDGET", "Orçamento de contexto insuficiente.", 422)
    tree = [entry["path"] for entry in state["repository_tree"]]
    header = json.dumps({"repository": state["repository_metadata"], "tree": tree[:100]}, ensure_ascii=False)
    if len(header.encode()) > remaining // 4:
        header = json.dumps({"repository": state["repository_metadata"], "tree_omitted": True})
    remaining -= len(header.encode())
    chunks = [header]
    presented = {}
    omitted = []
    files = state["repository_files"]
    # Content matches affect prompt selection, including mechanisms in central files.
    paths = sorted(files, key=lambda p: (not bool(state.get("content_hits", {}).get(p)), priority(p)))
    for path in paths:
        lines = safe_lines(files[path])
        matches = state.get("content_hits", {}).get(path, [])
        wanted = set(range(1, min(len(files[path].splitlines()), 60) + 1))
        for match in matches[:12]:
            wanted.update(range(max(1, match - 5), match + 11))
        label = json.dumps({"file": path}, ensure_ascii=False)
        allowance = min(remaining, 3500)
        used = len(label.encode()) + 2
        selected = {}
        block = [label]
        for number in sorted(wanted):
            if number not in lines:
                continue
            formatted = f"{number}: {lines[number]}"
            cost = len(formatted.encode()) + 1
            if used + cost > allowance:
                continue
            block.append(formatted)
            selected[number] = lines[number]
            used += cost
        if selected:
            presented[path] = selected
            remaining -= used
            chunks.append("\n".join(block))
        else:
            omitted.append(path)
    if not presented:
        raise AssessmentError("EMPTY_CONTEXT", "Nenhum trecho seguro cabe no contexto.", 422)
    coverage = {"presented": {p: sorted(lines) for p, lines in presented.items()},
                "partially_presented_files": [p for p, lines in presented.items() if len(lines) < len(files[p].splitlines())],
                "omitted_from_prompt": omitted, "token_estimate_upper_bound": settings.INPUT_TOKEN_BUDGET - remaining,
                "token_count_method": "utf8_bytes_upper_bound", "input_budget": settings.INPUT_TOKEN_BUDGET}
    return "\n\n".join(chunks), presented, coverage


def code_lines(path: str, content: str) -> set[int]:
    """Filter documentation, comment-only lines and Python docstrings."""
    if PurePosixPath(path).suffix.lower() in {".md", ".rst", ".txt"}:
        return set()
    if PurePosixPath(path).name.lower().startswith("readme"):
        return set()
    if path.endswith(".py"):
        try:
            tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            return {t.start[0] for t in tokens if t.type not in {
                tokenize.STRING, tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
                    and t.string.strip()}
        except (tokenize.TokenError, IndentationError):
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


def validate_evidence(result: AssessmentResult, criterion: str, presented: dict, files: dict):
    if result.criterion != criterion:
        raise ValueError("Unexpected criterion")
    all_evidence = list(result.evidence)
    for mechanism in result.mechanisms:
        all_evidence.extend(mechanism.evidence)
    if criterion == "engineering_mechanisms" and result.score > 0 and not any(m.implemented for m in result.mechanisms):
        raise ValueError("Engineering score requires implemented mechanisms")
    for evidence in all_evidence:
        lines = evidence.snippet.splitlines()
        if not lines or evidence.file not in presented:
            raise ValueError("Evidence file was not presented")
        for offset, text in enumerate(lines):
            if presented[evidence.file].get(evidence.line + offset) != text:
                raise ValueError("Evidence does not match presented lines")
        positions = set(range(evidence.line, evidence.line + len(lines)))
        if not positions & code_lines(evidence.file, files[evidence.file]):
            raise ValueError("Evidence contains only documentation or comments")
