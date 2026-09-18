from src.config.settings import Settings
from src.utils.errors import AssessmentError
from src.workflow_agentic.tools.repository_tools import TERMS, exclusion_reason, imported_paths, priority, read_repository_file


def build_context(provider, tree: list[dict], initial: dict[str, str], settings: Settings) -> dict:
    files = dict(initial)
    omitted = []
    eligible = []
    total_bytes = sum(len(s.encode()) for s in files.values())
    for entry in tree:
        path = entry["path"]
        reason = exclusion_reason(path)
        if entry.get("mode") == "120000":
            reason = "symlink"
        if entry.get("size", 0) > settings.MAX_FILE_BYTES:
            reason = "file_size_limit"
        if reason:
            omitted.append({"file": path, "reason": reason})
        elif path not in files:
            eligible.append(path)
    available = set(eligible) | set(files)
    pending = sorted(eligible, key=priority)
    hits = {}
    read_count = len(files)
    errors = []
    last_external_error = None
    while pending:
        path = pending.pop(0)
        if read_count >= settings.MAX_FILES or total_bytes >= settings.MAX_TOTAL_BYTES:
            omitted.extend({"file": p, "reason": "read_budget"} for p in [path, *pending])
            break
        read_count += 1
        try:
            content = read_repository_file(provider, path)
            size = len(content.encode())
            if size > settings.MAX_FILE_BYTES or size + total_bytes > settings.MAX_TOTAL_BYTES:
                omitted.append({"file": path, "reason": "read_budget"})
                continue
        except AssessmentError as exc:
            omitted.append({"file": path, "reason": exc.code})
            if exc.code == "REPOSITORY_AUTH":
                raise
            if exc.http_status >= 500 or exc.code == "NOT_FOUND":
                errors.append(exc.record("context_builder"))
                last_external_error = exc
            continue
        files[path] = content
        total_bytes += size
        matches = [i for i, line in enumerate(content.splitlines(), 1) if TERMS.search(line)]
        if matches:
            hits[path] = matches
        imports = imported_paths(path, content, available)
        # Prioritize referenced modules while retaining a deterministic order.
        pending.sort(key=lambda p: (p not in imports, priority(p)))
    if not files:
        if last_external_error:
            raise last_external_error
        raise AssessmentError("EMPTY_CONTEXT", "Nenhum arquivo textual pôde ser analisado.", 422)
    return {"repository_files": files, "content_hits": hits, "errors": errors,
            "coverage": {"files_discovered": len(tree), "files_read": len(files),
                         "bytes_read": total_bytes, "omitted": omitted,
                         "tree_truncated": provider.tree_truncated,
                         "limitations": "A avaliação considera apenas os arquivos e trechos apresentados; ausência de evidência não comprova ausência no repositório."}}
