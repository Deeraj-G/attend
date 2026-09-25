"""Research the procedure via Nimble text/image/video search. Media results are prompt references only."""

import json

import httpx

from backend.app.clients.nimble import NimbleClient, PHIBlockedError, SearchKind
from backend.app.config import settings
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract, ExecutorName, ExecutorOutput
from backend.app.state.workspace import Workspace

# Authoritative patient-education sources (ADR 0003). Text search is restricted to these.
TRUSTED_DOMAINS = [
    "medlineplus.gov",
    "nih.gov",
    "cdc.gov",
    "nhs.uk",
    "mayoclinic.org",
    "clevelandclinic.org",
    "hopkinsmedicine.org",
    "healthdirect.gov.au",
    "familydoctor.org",
    "asge.org",
    "gastro.org",
    "heart.org",
    "cancer.org",
]

MEDIA_NOTE = "Prompt-writing references only. Not licensed for reuse; never include in the output video."


def research_contract(contract_id: str = "c3", related_reports: list[str] | None = None) -> Contract:
    """The c3 contract, until the Manager emits it itself. Pass audit report ids to re-search their gaps."""
    return Contract(
        id=contract_id,
        executor=ExecutorName.WEB_SEARCH,
        goal="Research the procedure for a patient-education video: text sources plus image and video references.",
        acceptance_criteria=[
            f"{Workspace.SOURCES} and {Workspace.MEDIA_REFS} exist",
            "data.phi_blocked == 0 (no query was blocked for PHI)",
            "data.trusted_sources >= 3",
            "data.images >= 1 and data.videos >= 1",
        ],
        boundaries=[
            f"read only {Workspace.BRIEF} and the related reports; never the transcript",
            f"at most {settings.nimble_max_calls_per_run} Nimble calls",
            "media results are prompt references only",
            f"write only {Workspace.SOURCES}, {Workspace.MEDIA_REFS}, {Workspace.PROVENANCE}",
        ],
        related_reports=related_reports or [],
    )


class WebSearchAgent:
    name = "web_search"

    def __init__(self, client: NimbleClient | None = None) -> None:
        self.client = client or NimbleClient()

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        brief_path = workspace.path(Workspace.BRIEF)
        if not brief_path.exists():
            return ExecutorOutput(contract_id=contract.id, summary=f"missing input: {Workspace.BRIEF}")
        procedure = (json.loads(brief_path.read_text()).get("procedure") or "").strip()
        if not procedure:
            return ExecutorOutput(contract_id=contract.id, summary=f"missing input: procedure in {Workspace.BRIEF}")

        gaps = _gaps_from_reports(workspace, contract.related_reports)
        plan = _plan_searches(procedure, gaps)[: settings.nimble_max_calls_per_run]

        sources = _load(workspace, Workspace.SOURCES, {"procedure": procedure, "sources": [], "searches": []})
        media = _load(workspace, Workspace.MEDIA_REFS, {"note": MEDIA_NOTE, "images": [], "videos": []})
        seen = {s["url"] for s in sources["sources"]} | {m["url"] for m in media["images"] + media["videos"]}
        buckets = {"text": sources["sources"], "image": media["images"], "video": media["videos"]}

        run_logs = []
        for kind, query in plan:
            log = {"kind": kind, "query": query, "results": 0, "error": None}
            try:
                results = await self.client.search(
                    query, kind, include_domains=TRUSTED_DOMAINS if kind == "text" else None
                )
            except PHIBlockedError:
                log["error"] = "phi_blocked"
                results = []
            except (httpx.HTTPError, RuntimeError) as e:
                log["error"] = type(e).__name__
                results = []

            for r in results:
                if r["url"] in seen:
                    continue
                seen.add(r["url"])
                log["results"] += 1
                buckets[kind].append({**r, "query": query, "trusted": _is_trusted(r["domain"])})
            sources["searches"].append(log)
            run_logs.append(log)

        for name, content in ((Workspace.SOURCES, sources), (Workspace.MEDIA_REFS, media)):
            workspace.path(name).write_text(json.dumps(content, indent=2))
            workspace.record_provenance(name, self.name)

        # Counts only, for the Auditor. Queries and results stay in the artifacts.
        data = {
            "calls_planned": len(plan),
            "calls_sent": sum(1 for l in run_logs if l["error"] != "phi_blocked"),
            "phi_blocked": sum(1 for l in run_logs if l["error"] == "phi_blocked"),
            "failed_calls": sum(1 for l in run_logs if l["error"] not in (None, "phi_blocked")),
            "gaps_searched": len(gaps),
            "new_results": sum(l["results"] for l in run_logs),
            "sources": len(sources["sources"]),
            "trusted_sources": sum(1 for s in sources["sources"] if s["trusted"]),
            "images": len(media["images"]),
            "videos": len(media["videos"]),
        }
        flags = [f"{data[k]} {k.replace('_', ' ')}" for k in ("phi_blocked", "failed_calls") if data[k]]
        return ExecutorOutput(
            contract_id=contract.id,
            artifacts=[Workspace.SOURCES, Workspace.MEDIA_REFS],
            summary=f"{data['calls_sent']}/{data['calls_planned']} Nimble calls: {data['sources']} sources "
            f"({data['trusted_sources']} trusted), {data['images']} images, {data['videos']} videos"
            + (f" ({', '.join(flags)})" if flags else ""),
            data=data,
        )


def _plan_searches(procedure: str, gaps: list[str]) -> list[tuple[SearchKind, str]]:
    if gaps:
        # Re-search: spend the budget on the Auditor's gaps, keep existing media refs.
        return [("text", f"{procedure} {gap}") for gap in gaps]
    return [
        ("text", f"{procedure} what to expect preparation recovery"),
        ("image", f"{procedure} patient education illustration"),
        ("video", f"{procedure} what to expect patient education"),
    ]


def _gaps_from_reports(workspace: Workspace, report_ids: list[str]) -> list[str]:
    if not report_ids:
        return []
    wanted = set(report_ids)
    gaps: list[str] = []
    for report in ReportLog(workspace.dir).read_all():
        if report.id in wanted:
            gaps.extend(g for g in report.state_update.gaps if g not in gaps)
    return gaps


def _is_trusted(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS)


def _load(workspace: Workspace, name: str, default: dict) -> dict:
    path = workspace.path(name)
    return json.loads(path.read_text()) if path.exists() else default
