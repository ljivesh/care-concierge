"""Wires the nodes into a LangGraph StateGraph.

Read the edges below to answer "can a tool be reached without the safety
node?": START has exactly one edge, to `safety`, and the only ways into
`tools` and `escalate` start from there.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import (
    Deps,
    after_respond,
    after_router,
    after_safety,
    after_tools,
    fixed_reply_node,
    make_escalate_node,
    make_respond_node,
    make_router_node,
    make_safety_node,
    make_tools_node,
    make_verify_node,
)
from app.graph.state import ConciergeState


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(ConciergeState)

    graph.add_node("safety", make_safety_node(deps))
    graph.add_node("router", make_router_node(deps))
    graph.add_node("respond", make_respond_node(deps))
    graph.add_node("tools", make_tools_node(deps))
    graph.add_node("verify", make_verify_node(deps))
    graph.add_node("escalate", make_escalate_node(deps))
    graph.add_node("fixed_reply", fixed_reply_node)

    # Every turn starts at the safety node. There is no other edge out of START.
    graph.add_edge(START, "safety")
    graph.add_conditional_edges("safety", after_safety, ["router", "escalate", "fixed_reply"])
    graph.add_conditional_edges("router", after_router, ["respond", "tools", "escalate", "fixed_reply"])
    # The loop: the model asks for a tool, the tool runs, the model sees the result.
    # ...and a finished clinic answer is checked against its passages before it is shown.
    graph.add_conditional_edges("respond", after_respond, ["tools", "verify", END])
    graph.add_edge("verify", END)
    graph.add_conditional_edges("tools", after_tools, ["respond", "fixed_reply"])
    graph.add_edge("escalate", END)
    graph.add_edge("fixed_reply", END)

    # The checkpointer saves the state to Postgres after every node, under the
    # thread_id given when the graph is run. That is what survives a restart.
    return graph.compile(checkpointer=checkpointer)
