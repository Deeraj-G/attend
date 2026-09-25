"""Run step 3 (Nimble research) on a case.

    python -m backend.scripts.research --case <id>                 # needs brief.json from step 2
    python -m backend.scripts.research --procedure "colonoscopy"   # new case with a stand-in brief
    python -m backend.scripts.research --case <id> --reports V4    # re-search the gaps in report V4
"""

import argparse
import asyncio
import json
import uuid

from backend.app.agents.web_search import WebSearchAgent, research_contract
from backend.app.state.schemas import Case
from backend.app.state.workspace import Workspace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="existing case id with a brief.json")
    source.add_argument("--procedure", help="create a case whose brief is just this procedure name (until step 2 lands)")
    parser.add_argument("--reports", nargs="*", default=[], help="audit report ids whose gaps to re-search")
    args = parser.parse_args()

    if args.case:
        workspace = Workspace(args.case)
        if not workspace.exists():
            parser.error(f"case {args.case} not found")
    else:
        case = Case(id=uuid.uuid4().hex[:12], procedure=args.procedure)
        workspace = Workspace(case.id)
        workspace.save_case(case)
        workspace.path(Workspace.BRIEF).write_text(json.dumps({"procedure": args.procedure}, indent=2))
        workspace.record_provenance(Workspace.BRIEF, "manual")
        print(f"case {workspace.case_id}: stand-in brief for {args.procedure!r}")

    output = asyncio.run(WebSearchAgent().run(research_contract(related_reports=args.reports), workspace))
    print(output.summary)
    print(output.data)
    if not output.artifacts:
        return

    sources = json.loads(workspace.path(Workspace.SOURCES).read_text())["sources"]
    media = json.loads(workspace.path(Workspace.MEDIA_REFS).read_text())
    for label, items in (("TEXT", sources), ("IMAGE", media["images"]), ("VIDEO", media["videos"])):
        for r in items:
            print(f"  {label:<5} {r['domain']:<28} {r['title'][:60]}")
    print(f"-> {workspace.path(Workspace.SOURCES)}, {workspace.path(Workspace.MEDIA_REFS)}")


if __name__ == "__main__":
    main()
