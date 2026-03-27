"""
playground/api/server.py — FastAPI backend for the Agent Hypervisor interactive playground.

Single endpoint: POST /evaluate
Accepts a raw input, channel, tool, and args.
Returns the full pipeline trace: sanitized event, proposal, reason chain, verdict.

Run with:
    uvicorn playground.api.server:app --reload --port 8000
or:
    python playground/api/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from boundary.semantic_event import SemanticEventFactory, TrustLevel
from boundary.intent_proposal import IntentProposalBuilder
from policy.engine import PolicyEngine, Verdict

COMPILED_DIR = REPO_ROOT / "manifests" / "examples" / "compiled"
PLAYGROUND_DIR = Path(__file__).parent.parent

MANIFESTS = {
    "email-safe-assistant": COMPILED_DIR / "email-safe-assistant",
    "mcp-gateway-demo": COMPILED_DIR / "mcp-gateway-demo",
    "browser-agent-demo": COMPILED_DIR / "browser-agent-demo",
}

# Pre-load engines
_engines: dict[str, PolicyEngine] = {}

def get_engine(manifest: str) -> PolicyEngine:
    if manifest not in _engines:
        _engines[manifest] = PolicyEngine.from_compiled_dir(MANIFESTS[manifest])
    return _engines[manifest]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    input: str
    channel: str = "email"         # user | email | web | file | mcp | agent
    tool: str = "send_email"
    args: dict[str, Any] = {}
    manifest: str = "email-safe-assistant"


class ProvenanceInfo(BaseModel):
    event_id: str
    source_channel: str
    timestamp: str
    injections_stripped: list[str]


class SemanticEventInfo(BaseModel):
    source: str
    trust_level: str
    taint: bool
    sanitized_payload: str
    payload_type: str
    provenance: ProvenanceInfo


class ProposalInfo(BaseModel):
    proposal_id: str
    tool: str
    args: dict[str, Any]
    trust_level: str
    taint: bool
    source_event_id: str


class ReasonStepInfo(BaseModel):
    check: str
    result: str       # pass | fail | escalate
    detail: str


class EvaluateResponse(BaseModel):
    # Input
    raw_input: str
    channel: str
    manifest: str

    # Pipeline stages
    event: SemanticEventInfo
    proposal: ProposalInfo
    reason_chain: list[ReasonStepInfo]

    # Output
    verdict: str                   # allow | deny | require_approval | simulate
    verdict_label: str             # human-readable
    denial_point: str | None       # which check caused denial, if any
    taint_at_denial: bool

    # Baseline comparison
    baseline_outcome: str          # always "executed" — no policy


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_event(factory: SemanticEventFactory, channel: str, raw: str):
    if channel == "user":
        return factory.from_user(raw)
    elif channel == "email":
        return factory.from_email(raw)
    elif channel == "web":
        return factory.from_web(raw)
    elif channel == "file":
        return factory.from_file(raw)
    elif channel == "mcp":
        return factory.from_mcp(raw, tool_name="unknown")
    elif channel == "agent":
        return factory.from_agent(raw, agent_id="unknown")
    return factory.from_user(raw)


VERDICT_LABELS = {
    Verdict.ALLOW: "Allowed",
    Verdict.DENY: "Denied",
    Verdict.REQUIRE_APPROVAL: "Requires approval",
    Verdict.SIMULATE: "Simulation only",
}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Agent Hypervisor Playground", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    manifest = req.manifest if req.manifest in MANIFESTS else "email-safe-assistant"
    factory = SemanticEventFactory(session_id="playground")
    engine = get_engine(manifest)

    event = make_event(factory, req.channel, req.input)
    proposal = IntentProposalBuilder(event).build(req.tool, req.args)
    decision = engine.evaluate(proposal)

    # Find denial point
    denial_point = None
    for step in decision.reason_chain:
        if step.result in ("fail", "escalate"):
            denial_point = step.check
            break

    return EvaluateResponse(
        raw_input=req.input,
        channel=req.channel,
        manifest=manifest,
        event=SemanticEventInfo(
            source=event.source,
            trust_level=event.trust_level,
            taint=event.taint,
            sanitized_payload=event.sanitized_payload,
            payload_type=event.payload_type,
            provenance=ProvenanceInfo(
                event_id=event.provenance.event_id,
                source_channel=event.provenance.source_channel,
                timestamp=event.provenance.timestamp,
                injections_stripped=list(event.provenance.injections_stripped),
            ),
        ),
        proposal=ProposalInfo(
            proposal_id=proposal.proposal_id,
            tool=proposal.tool,
            args=dict(proposal.args),
            trust_level=proposal.trust_level,
            taint=proposal.taint,
            source_event_id=proposal.source_event_id,
        ),
        reason_chain=[
            ReasonStepInfo(check=s.check, result=s.result, detail=s.detail)
            for s in decision.reason_chain
        ],
        verdict=decision.verdict,
        verdict_label=VERDICT_LABELS.get(decision.verdict, decision.verdict),
        denial_point=denial_point,
        taint_at_denial=proposal.taint,
        baseline_outcome="executed",
    )


@app.get("/manifests")
def list_manifests() -> dict:
    return {"manifests": list(MANIFESTS.keys())}


@app.get("/tools/{manifest}")
def list_tools(manifest: str) -> dict:
    if manifest not in MANIFESTS:
        return {"tools": []}
    engine = get_engine(manifest)
    return {"tools": list(engine._actions.keys())}


# Serve the playground frontend
app.mount("/static", StaticFiles(directory=str(PLAYGROUND_DIR / "static")), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(str(PLAYGROUND_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("playground.api.server:app", host="0.0.0.0", port=8000, reload=True)
