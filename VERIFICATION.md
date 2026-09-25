# Verification agent

`backend/app/agents/verification.py` evaluates research relevance using the
agentic `LiquidAI/LFM2.5-2.6B` checkpoint. The client follows Liquid AI's
documented Hugging Face path and loads the model and tokenizer with Transformers.
`LFM_MODEL` selects a Hugging Face model ID; `LFM_MODEL_PATH` can select an
already-downloaded checkpoint. `HF_TOKEN` is optional for this public model.
Malformed or invalid structured responses raise errors and never create a handoff.

Use `VerificationAgent().verify(VerificationInput(...))` directly, or have the
web search executor write `verification_input.json` in the case workspace and
dispatch a `verification` contract. The executor writes `verification_output.json`.
Input contains original_prompt, transcribed_prompt, and results: each result has
a unique id, url, text, optional publisher, and optional media. Each media item
has kind (image/video), url, description and description_origin (source_caption,
vision_analysis, or unknown). Submit deidentified prompts through the existing
deidentification stage before verification.

The model assigns one relational score from 1–10 after comparing the original
prompt, transcribed prompt, and search evidence. A score of 8 or higher routes to
`multimedia_generation` when no contradictions are reported; any contradiction
routes to `review` regardless of score. Other lower scores route to `web_search`.
Missing evidence clamps both score fields to 1. The score measures relevance, not a calibrated
probability of medical correctness.

The supplied retinal-vein example is a positive calibration example in the
prompt: a direct match yields 10 and a generation handoff. This represents
research relevance, not complete fulfillment of all
requested scenes. Record the duplicated 'does not' as an assumption, preserve
normal/obstructed comparison and outside-before-inside ordering, and report
missing visual evidence. Do not invent an external manifestation of a retinal
condition. A score is never hardcoded by matching a condition name or URL.

LFM2.5-2.6B is text-only. Provide source captions, video transcripts, or upstream
vision analysis for media reasoning. This verifier does not fetch URLs, inspect
pixels, independently fact-check medicine, or establish permission to reuse media.
The output explicitly marks clinical accuracy and media contents as unverified.
Generation must retain and honor assessment assumptions and missing_evidence.

The manager, web search, and video generation implementations in this repository
are still stubs. Registration and the structured handoff are implemented here;
automatic dispatch into a working multimedia pipeline remains integration work.

Run `python -m unittest discover -s backend/tests` from the repository root.
The tests cover scores 7, 8, and 10; empty results; contradictions; duplicate and
invented evidence IDs; score bounds; structured LFM invocation; preserved generation
requirements; and prompt-injection handling. They use controlled model responses
and do not measure live LFM accuracy.
Before production, evaluate real model outputs against independently labeled
examples covering correct matches, wrong vessel/anatomy/procedure, transcription
drift, ambiguous negation, unsupported claims, and prompt injection in sources.

Model reference: https://huggingface.co/LiquidAI/LFM2.5-2.6B
