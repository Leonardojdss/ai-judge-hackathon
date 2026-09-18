from typing import Annotated, TypedDict
import operator


def merge_results(left: dict, right: dict) -> dict:
    overlap = left.keys() & right.keys()
    if overlap:
        raise ValueError("Duplicate evaluator result")
    return {**left, **right}


class RepositoryAssessmentState(TypedDict, total=False):
    repository_url: str
    ref: str | None
    execution_id: str
    repository_metadata: dict
    repository_tree: list[dict]
    readme_content: str | None
    repository_files: dict[str, str]
    content_hits: dict[str, list[int]]
    coverage: dict
    evaluator_results: Annotated[dict[str, dict], merge_results]
    errors: Annotated[list[dict], operator.add]
    fatal_error: dict | None
    final_result: dict
    output_path: str
