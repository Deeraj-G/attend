"""AuditAgent. Read-only, clean context. Checks provenance, PHI and acceptance; writes report V_i.

Minimal rule-based version so the loop runs end to end; research is judged by the verifier
(ADR 0004 Option A: the verifier is the source audit, not its own subtask).
"""

import json

from backend.app.agents.transcription import WORDS_PER_SPEECH_SECOND
from backend.app.agents.verification import SearchResult, VerificationAgent, VerificationInput
from backend.app.state.schemas import Contract, ExecutorOutput, Report, StateUpdate
from backend.app.state.workspace import Workspace


class AuditAgent:
    def __init__(self, verifier: VerificationAgent | None = None) -> None:
        self._verifier = verifier

    @property
    def verifier(self) -> VerificationAgent:
        if self._verifier is None:
            self._verifier = VerificationAgent()
        return self._verifier

    def audit(self, contract: Contract, output: ExecutorOutput, workspace: Workspace) -> Report:
        def report(status: str, integrity: str = "clean", gaps: list[str] | None = None, **data) -> Report:
            return Report(
                id=f"v-{contract.id}",
                contract_id=contract.id,
                subtask=contract.subtask,
                status=status,
                integrity=integrity,
                state_update=StateUpdate(facts=[output.summary], gaps=gaps or [], data=data),
            )

        if not output.artifacts:
            return report("incomplete", gaps=[output.summary or "executor produced no artifacts"])

        provenance = workspace.provenance()
        for path in output.artifacts:
            entry = provenance.get(path)
            if not workspace.path(path).exists() or entry is None or entry.written_by != contract.executor:
                return report("incomplete", "suspect", gaps=[f"provenance mismatch for {path}"])

        d = output.data
        match contract.subtask:
            case "transcribe":
                lo, hi = WORDS_PER_SPEECH_SECOND
                gaps = [f"{k} = {d.get(k)}" for k in ("empty_segments", "truncated_segments") if d.get(k)]
                if not lo <= d.get("words_per_speech_second", 0) <= hi:
                    gaps.append(f"words_per_speech_second = {d.get('words_per_speech_second')}")
                return report("incomplete" if gaps else "complete", gaps=gaps, duration_s=d.get("duration_s"))
            case "deidentify":
                if d.get("phi_remaining"):
                    return report("incomplete", "violation", ["identifiers left in brief"], discarded=["brief.json"])
                return report("complete")
            case "research":
                return self._audit_research(workspace, d, report)
            case "video":
                if d.get("phi_blocked"):
                    return report("incomplete", "violation", ["prompt contained PHI"], discarded=["video prompt"])
                if d.get("ready"):
                    return report("complete")
                return report("incomplete", gaps=[f"BFL status {d.get('status')}"])
        return report("complete")

    def _audit_research(self, workspace: Workspace, d: dict, report) -> Report:
        brief = json.loads(workspace.path(Workspace.BRIEF).read_text())
        sources = json.loads(workspace.path(Workspace.SOURCES).read_text())["sources"]
        results = [
            SearchResult(id=f"s{i}", url=s["url"], text=f"{s['title']}. {s['snippet']}"[:2000], publisher=s["domain"])
            for i, s in enumerate(sources[:20])
        ]
        request = f"Patient-education video about {brief['procedure']}. Steps: {'; '.join(brief.get('steps', []))}"
        try:
            verdict = self.verifier.verify(
                VerificationInput(original_prompt=request, transcribed_prompt=brief["procedure"], results=results)
            )
        except Exception:
            # Verifier unavailable: fall back to the executor's own counts.
            if d.get("trusted_sources", 0) >= 3:
                return report("complete", verifier="unavailable")
            return report("incomplete", gaps=["fewer than 3 trusted sources"], verifier="unavailable")

        a = verdict.assessment
        data = {"relational_score": verdict.relational_score, "route": verdict.decision}
        if verdict.decision == "review":
            return report("blocked", gaps=a.contradictions, question="; ".join(a.contradictions), **data)
        if verdict.decision == "web_search":
            return report("incomplete", gaps=a.missing_evidence or ["sources do not match the procedure"], **data)
        return report("complete", **data)
