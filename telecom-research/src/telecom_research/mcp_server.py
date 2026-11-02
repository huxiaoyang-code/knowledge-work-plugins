"""Optional official MCP SDK stdio transport; tools are discovered and checked per request."""
import argparse
import asyncio
import json
from pathlib import Path

from .store import Store, WorkflowError, canonical


def object_schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


DOCUMENTS = object_schema({key: {"type": "string", "minLength": 1} for key in ("manuscript", "evidence", "plan")}, ["manuscript", "evidence", "plan"])
REPORT = object_schema({
    "decision": {"type": "string", "enum": ["pass", "revise", "reject", "insufficient"]},
    "scores": object_schema({key: {"type": ["number", "null"], "minimum": 0, "maximum": 10,
        "description": "Null only when decision is insufficient"} for key in ("novelty", "theory", "experiments", "engineering", "evidence", "presentation")},
        ["novelty", "theory", "experiments", "engineering", "evidence", "presentation"]),
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "rationale": {"type": "string", "minLength": 1},
    "blockers": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "search_evidence": {"type": "array", "description": "Empty only for insufficient; record actual searches, never fabricate access",
        "items": object_schema({key: {"type": "string", "minLength": 1} for key in ("query", "source", "url", "accessed_at", "finding")},
                               ["query", "source", "url", "accessed_at", "finding"])}
}, ["decision", "scores", "confidence", "rationale", "blockers", "search_evidence"])
SPEC = object_schema({
    "kind": {"type": "string", "enum": ["simulation", "hardware"]},
    "name": {"type": "string", "minLength": 1},
    "code_revision": {"type": "string", "minLength": 1},
    "config": {"type": "object", "minProperties": 1, "description": "Simulation or algorithm parameters; never override hardware_config RF settings"},
    "device_id": {"type": "string"},
    "device_config_hash": {"type": "string", "description": "Required for hardware: manager-approved SHA-256"},
    "hardware_config": {"type": "object", "description": "Required for hardware: exact complete operator-approved device configuration"}
}, ["kind", "name", "code_revision", "config"])
SCHEMAS = {
    "project_status": object_schema(),
    "research_context": object_schema(),
    "submission_submit": DOCUMENTS,
    "review_context": object_schema(),
    "review_submit": object_schema({"report": REPORT}, ["report"]),
    "execution_context": object_schema(),
    "experiment_submit": object_schema({"spec": SPEC}, ["spec"]),
    "experiment_status": object_schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
    "paper_submit": DOCUMENTS,
}
DESCRIPTIONS = {
    "project_status": "Read the scoped project's current status. Reviewer reports remain independent.",
    "research_context": "Read the current draft and author-facing review feedback to resume a research or revision session.",
    "submission_submit": "Snapshot a draft manuscript, literature evidence and experiment plan for independent review.",
    "review_context": "Read your assigned immutable submission and linked experiment provenance, without author history or peer reviews.",
    "review_submit": "Submit one immutable independent review of the assigned version; decision, six scores, confidence, rationale, search_evidence and blockers required.",
    "execution_context": "Read this runtime's exact approved draft, experiment plan, evidence and linked experiment records; stale grants are rejected.",
    "experiment_submit": "Register a formal simulation or operator-approved hardware request; no executor is configured in this prototype.",
    "experiment_status": "Read a current-draft experiment's status and checked imported provenance.",
    "paper_submit": "Snapshot the complete paper after approved-draft experiments have imported provenance-checked results.",
}


async def serve(state, token_file):
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as exc:
        raise SystemExit("Install the optional transport with pip install -e '.[mcp]' first") from exc
    store = Store(state)
    token = Path(token_file).read_text(encoding="utf-8").strip()
    store.tools(token)  # Fail before accepting protocol traffic for invalid/manager credentials.
    server = Server("telecom-research")

    @server.list_tools()
    async def list_tools():
        return [types.Tool(name=name, description=DESCRIPTIONS[name], inputSchema=SCHEMAS[name]) for name in store.tools(token)]

    @server.call_tool()
    async def call_tool(name, arguments):
        try:
            result = store.call(token, name, arguments or {})
            return types.CallToolResult(content=[types.TextContent(type="text", text=canonical(result))])
        except (WorkflowError, TypeError, KeyError) as exc:
            return types.CallToolResult(content=[types.TextContent(type="text", text=canonical({"error": str(exc)}))], isError=True)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--token-file", required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.state, args.token_file))


if __name__ == "__main__":
    main()
