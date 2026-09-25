"""Verifier output -> /multimedia request (the 422 Juan hit posting verifier output directly)."""

from fastapi.testclient import TestClient

from backend.app.agents.verification import Assessment, SearchResult, VerificationInput, finalize
from backend.app.main import app

client = TestClient(app)


def verifier_output(score: int = 9, contradictions=()):
    data = VerificationInput(
        original_prompt="Show normal vs blocked retinal veins, outside to inside.",
        transcribed_prompt="retinal vein occlusion",
        results=[
            SearchResult(id="s0", url="https://nei.nih.gov/rvo", text="Veins get blocked.", publisher="NEI"),
            SearchResult(id="s1", url="https://example.com/x", text="Unrelated.", publisher="Blog"),
        ],
    )
    a = Assessment(
        relational_score=score, evidence_ids=["s0"], rationale="Matches.", assumptions=[],
        generation_requirements=["outside before inside"], missing_evidence=[], contradictions=list(contradictions),
        source_quality="supported",
    )
    return finalize(data, a).model_dump(mode="json")


def test_verifier_output_previews_with_only_cited_evidence():
    res = client.post("/multimedia/from-verification/preview", json={"verification_output": verifier_output()})
    assert res.status_code == 200
    prompt = res.json()["payload"]["prompt"]
    assert "Veins get blocked." in prompt and "Unrelated." not in prompt
    assert "outside before inside" in prompt


def test_non_generation_route_is_rejected():
    res = client.post("/multimedia/from-verification/preview", json={"verification_output": verifier_output(score=5)})
    assert res.status_code == 409
