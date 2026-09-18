from langgraph.graph import END, START, StateGraph

from src.workflow_agentic.nodes.node import (evaluator_node, json_output_node, observed,
                                             repository_context_builder_node, repository_loader_node,
                                             synthesis_node)
from src.workflow_agentic.registry import EVALUATORS
from src.workflow_agentic.state import RepositoryAssessmentState


def build_repository_assessment_graph(provider, agents, store, settings, telemetry=None, evaluators=EVALUATORS):
    if not evaluators or any(not e.criterion.strip() for e in evaluators) or len({e.criterion for e in evaluators}) != len(evaluators):
        raise ValueError("Evaluator identifiers must be nonempty and unique")
    builder = StateGraph(RepositoryAssessmentState)
    nodes = {"repository_loader": repository_loader_node(provider),
             "context_builder": repository_context_builder_node(provider, settings),
             "synthesis": synthesis_node(evaluators, settings),
             "json_output": json_output_node(store)}
    for evaluator in evaluators:
        if evaluator.criterion in nodes:
            raise ValueError("Evaluator identifier is reserved")
        nodes[evaluator.criterion] = evaluator_node(evaluator, agents)
    for name, operation in nodes.items():
        builder.add_node(name, observed(name, operation, settings, telemetry))
    builder.add_edge(START, "repository_loader")
    builder.add_conditional_edges("repository_loader", lambda s: "synthesis" if s.get("fatal_error") else "context_builder",
                                  ["synthesis", "context_builder"])
    evaluator_names = [e.criterion for e in evaluators]
    builder.add_conditional_edges("context_builder", lambda s: "synthesis" if s.get("fatal_error") else evaluator_names,
                                  ["synthesis", *evaluator_names])
    builder.add_edge(evaluator_names, "synthesis")
    builder.add_edge("synthesis", "json_output")
    builder.add_edge("json_output", END)
    return builder


def get_compiled_graph(provider, agents, store, settings, telemetry=None, checkpointer=None, evaluators=EVALUATORS):
    return build_repository_assessment_graph(provider, agents, store, settings, telemetry, evaluators).compile(checkpointer=checkpointer)
