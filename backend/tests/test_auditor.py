"""Minimal AuditAgent: provenance, per-subtask checks, and the verifier as the research audit."""

import json

import pytest

from backend.app.agents.verification import Assessment, VerificationOutput
from backend.app.harness.auditor import AuditAgent
from backend.app.harness.contracts import build_contract
from backend.app.state.schemas import ExecutorOutput
from backend.app.state.workspace import Workspace


class FakeVerifier:
    def __init__(self, decision: str, contradictions=(), missing=()):
        self.decision, self.contradictions, self.missing = decision, list(contradictions), list(missing)

    def verify(self, data):
        a = Assessment(
            relational_score=9, evidence_ids=["s0"], rationale="", assumptions=[], generation_requirements=[],
            missing_evidence=self.missing, contradictions=self.contradictions, source_quality="supported",
        )
        return VerificationOutput(relational_score=9, decision=self.decision, assessment=a)


@pytest.fixture
def ws(tmp_path):
    w = Workspace("abc", root=tmp_path)
    w.path(Workspace.BRIEF).write_text(json.dumps({"procedure": "colonoscopy", "steps": ["prep"]}))
    w.path(Workspace.SOURCES).write_text(json.dumps({"sources": [
        {"url": "https://nih.gov/x", "title": "Colonoscopy", "snippet": "what to expect", "domain": "nih.gov"}
    ]}))
    w.record_provenance(Workspace.SOURCES, "web_search")
    return w


def research(ws, verifier):
    c = build_contract("research", attempt=1, round_no=3, related_reports=[])
    out = ExecutorOutput(contract_id=c.id, artifacts=[Workspace.SOURCES], data={"trusted_sources": 1})
    return AuditAgent(verifier).audit(c, out, ws)


def test_verifier_generate_route_completes(ws):
    r = research(ws, FakeVerifier("multimedia_generation"))
    assert (r.subtask, r.status, r.integrity) == ("research", "complete", "clean")


def test_verifier_web_search_route_is_incomplete_with_missing_evidence_as_gaps(ws):
    r = research(ws, FakeVerifier("web_search", missing=["recovery timeline"]))
    assert r.status == "incomplete" and r.state_update.gaps == ["recovery timeline"]


def test_verifier_review_route_blocks_with_question(ws):
    r = research(ws, FakeVerifier("review", contradictions=["same-day vs overnight"]))
    assert r.status == "blocked" and r.state_update.data["question"] == "same-day vs overnight"


def test_verifier_failure_falls_back_to_counts(ws):
    class Broken:
        def verify(self, data):
            raise RuntimeError("model down")

    r = research(ws, Broken())
    assert r.status == "incomplete" and r.state_update.data["verifier"] == "unavailable"


def test_artifact_written_by_another_executor_is_suspect(ws):
    ws.record_provenance(Workspace.SOURCES, "deidentify")
    r = research(ws, FakeVerifier("multimedia_generation"))
    assert r.integrity == "suspect"


def test_video_not_ready_is_incomplete(ws):
    ws.path("video.json").write_text("{}")
    ws.record_provenance("video.json", "video_generation")
    c = build_contract("video", attempt=1, round_no=4, related_reports=[])
    out = ExecutorOutput(contract_id=c.id, artifacts=["video.json"], data={"status": "Error", "ready": 0})
    r = AuditAgent(FakeVerifier("multimedia_generation")).audit(c, out, ws)
    assert r.status == "incomplete" and r.state_update.gaps == ["BFL status Error"]


def test_research_report_keeps_verifier_evidence_and_requirements(ws):
    v = FakeVerifier("multimedia_generation")
    r = research(ws, v)
    assert r.state_update.data["evidence_urls"] == ["https://nih.gov/x"]
    assert "generation_requirements" in r.state_update.data


def test_video_request_uses_cited_sources_and_requirements():
    from backend.app.agents.video_generation import build_request

    c = build_contract("video", attempt=1, round_no=4, related_reports=[])
    sources = {"sources": [
        {"url": "https://a.gov", "title": "Cited", "snippet": "yes", "trusted": True},
        {"url": "https://b.gov", "title": "Uncited", "snippet": "no", "trusted": True},
    ]}
    verdict = {"evidence_urls": ["https://a.gov"], "generation_requirements": ["outside before inside"]}
    req = build_request(c, {"procedure": "colonoscopy", "steps": []}, sources, {}, verdict)
    assert "Cited" in req.verification.context and "Uncited" not in req.verification.context
    assert req.verification.description == {"generation_requirements": ["outside before inside"]}

    fallback = build_request(c, {"procedure": "colonoscopy", "steps": []}, sources, {}, {})
    assert "Uncited" in fallback.verification.context
