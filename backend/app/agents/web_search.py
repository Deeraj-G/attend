"""Research the procedure via Nimble text/image/video search. Media results are prompt references only."""

import json

import httpx

from backend.app.clients.nimble import NimbleClient, PHIBlockedError, SearchKind
from backend.app.config import settings
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract, ExecutorOutput
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

SOURCES_FILE = "sources.json"
MEDIA_FILE = "media_refs.json"
MEDIA_NOTE = "Prompt-writing references only. Not licensed for reuse; never include in the output video."


class WebSearchAgent:
    name = "web_search"

    def __init__(self, client: NimbleClient | None = None) -> None:
        self.client = client or NimbleClient()

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        brief_path = workspace.path("brief.json")
        if not brief_path.exists():
            return ExecutorOutput(contract_id=contract.id, summary="brief.json missing; nothing to research")
        procedure = (json.loads(brief_path.read_text()).get("procedure") or "").strip()
        if not procedure:
            return ExecutorOutput(contract_id=contract.id, summary="brief.json has no procedure")

        gaps = _gaps_from_reports(workspace, contract.related_reports)
        plan = _plan_searches(procedure, gaps)[: settings.nimble_max_calls_per_run]

        sources = _load(workspace, SOURCES_FILE, {"procedure": procedure, "sources": [], "searches": []})
        media = _load(workspace, MEDIA_FILE, {"note": MEDIA_NOTE, "images": [], "videos": []})
        seen = {s["url"] for s in sources["sources"]} | {
            m["url"] for m in media["images"] + media["videos"]
        }

        for kind, query in plan:
            log = {"kind": kind, "query": query, "results": 0, "error": None}
            try:
                results = await self.client.search(
                    query, kind, include_domains=TRUSTED_DOMAINS if kind == "text" else None
                )
            except PHIBlockedError as e:
                log["error"] = f"phi_blocked: {e}"
                results = []
            except (httpx.HTTPError, RuntimeError) as e:
                log["error"] = f"{type(e).__name__}: {e}"
                results = []

            for r in results:
                if r["url"] in seen:
                    continue
                seen.add(r["url"])
                log["results"] += 1
                r["query"] = query
                r["trusted"] = _is_trusted(r["domain"])
                target = {"text": sources["sources"], "image": media["images"], "video": media["videos"]}
                target[kind].append(r)
            sources["searches"].append(log)

        written = []
        for name, data in ((SOURCES_FILE, sources), (MEDIA_FILE, media)):
            workspace.path(name).write_text(json.dumps(data, indent=2))
            workspace.record_provenance(name, self.name)
            written.append(name)

        run_logs = sources["searches"][-len(plan):] if plan else []
        errors = [f"{l['kind']}: {l['error']}" for l in run_logs if l["error"]]
        sent = sum(1 for l in run_logs if not (l["error"] or "").startswith("phi_blocked"))
        summary = (
            f"{sent}/{len(plan)} Nimble calls sent; totals: {len(sources['sources'])} sources, "
            f"{len(media['images'])} images, {len(media['videos'])} videos"
        )
        if errors:
            summary += "; errors: " + "; ".join(errors)
        return ExecutorOutput(contract_id=contract.id, artifacts=written, summary=summary)


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
