# Interview Prep Agent: Hackathon Plan

An on-device mock interviewer. The user starts a session and names a topic. The agent then works on its own: it researches what real candidates report being asked (live Reddit data via Nimble), builds a grounded question bank (local RAG), runs a spoken mock interview (Liquid AI audio model), scores it, and writes the session to RawTree. Each new session reads back from RawTree, so the agent gets better at preparing *this* user over time.

**Sponsor tools (3):** Nimble (live web search), Liquid AI (LFM2.5-2.6B + LFM2.5-Audio-1.5B, on device), RawTree / Tinybird (session warehouse + analytics).

---

## 1. How this maps to the judging criteria

| Criterion | What we show |
|---|---|
| **Autonomy** | The user provides only a topic. The agent plans queries, hits Nimble live, judges coverage, re-queries if it finds gaps, builds the RAG corpus, and runs the interview. There are no manual steps between "start" and the first question. |
| **Idea** | Interview prep grounded in *current, real* candidate reports instead of generic LLM questions. It runs private and offline-capable on a laptop, and it adapts to the user's weak areas across sessions. |
| **Technical implementation** | A plan → act → observe → self-correct loop that runs inside a **4k-token** model. That limit forces real context management (see §4). This is the core "long horizon without drowning in history" story. |
| **Tool use** | Each sponsor tool does a job nothing else in the stack does: Nimble = eyes on the web, LFM = brain and voice, RawTree = long-term memory and analytics. |
| **Demo (3 min)** | A scripted flow with a live agent trace panel and a RawTree-backed progress view (§8). |

---

## 2. User flow

1. **Start session** → pick a topic, e.g. `"System design: rate limiter"` or `"Behavioral: conflict with manager"`, plus optional company/level.
2. **Recall** (RawTree): find similar past sessions → weak areas, questions already asked, best sources, a reusable corpus.
3. **Plan** (LFM2.5-2.6B): write an interviewer persona system prompt and a search plan (queries × subreddits).
4. **Research** (Nimble): run web searches scoped to `r/cscareerquestions`, `r/systemdesign`, `r/interviewprep`, `r/leetcode`, `r/ExperiencedDevs` (the list is configurable). Fetch the threads.
5. **Observe and self-correct**: chunk, embed, and index into the local RAG store. The LFM grades coverage against the plan's subtopics. If coverage falls short, it rewrites queries and loops, within a hard budget.
6. **Build question bank**: extract candidate questions from the RAG store, dedupe against past sessions, and order them easy → hard, weak areas first.
7. **Interview** (LFM2.5-Audio-1.5B): spoken Q&A with follow-ups grounded in retrieved chunks.
8. **Evaluate**: score each answer against a rubric and retrieved "good answer" evidence.
9. **Persist** (RawTree): write the session JSON (plan, queries, sources, questions, scores, agent trace).

Steps 3–6 are the long pre-processing phase. They run in the background with a live progress trace, so the user isn't left waiting on a blank screen.

---

## 3. Architecture

```
┌──────────────────────────── Device (laptop, CPU) ────────────────────────────┐
│                                                                              │
│  Web UI (mic, transcript, agent-trace panel, progress dashboard)             │
│        │ WebSocket                                                           │
│  ┌─────▼──────────────────────── Orchestrator (Python) ───────────────────┐  │
│  │  State machine: RECALL → PLAN → RESEARCH ⇄ OBSERVE → BANK → INTERVIEW  │  │
│  │                 → EVALUATE → PERSIST                                   │  │
│  │  Session state store (SQLite): plan, step log, summaries, budgets      │  │
│  │  Context builder: packs ≤4k-token prompts per step (see §4)            │  │
│  └───┬───────────────┬──────────────────┬──────────────────┬──────────────┘  │
│      │               │                  │                  │                 │
│  LFM2.5-2.6B     LFM2.5-Audio-1.5B   Local RAG            Embedder           │
│  (Q4, llama.cpp) (ASR + TTS 24kHz)   (sqlite-vec/Lance)   (small, CPU)       │
└──────┼───────────────────────────────────────────────────────────────────────┘
       │ HTTPS                                    │ HTTPS
   Nimble Web Search API                    RawTree (Tinybird)
   (live Reddit results)                    JSON in → SQL out
```

**Proposed stack** (confirm each item before building on it):
- Orchestrator: Python 3.11 + FastAPI + WebSocket; a plain state machine, no heavy agent framework.
- LFM2.5-2.6B: GGUF Q4 via `llama.cpp` / `llama-cpp-python`, with JSON-schema constrained output for plans and grades.
- LFM2.5-Audio-1.5B: Liquid's audio runtime. *Verify: packaging, CPU latency, and whether it handles both ASR and TTS in one model.*
- RAG: `sqlite-vec` or LanceDB (single file, no server) plus a small CPU embedding model.
- RawTree: Tinybird-hosted ClickHouse fork, reached through its HTTP ingest and SQL endpoints. *Verify: JSON column support and vector distance functions (`cosineDistance`).*
- UI: a single-page app (Vite + React or plain HTML) with a mic stream over WebSocket.

---

## 4. Long-horizon design: staying inside 4k tokens

This is the technical heart of the project and should be the pitch. The planner has a 4k-token window, so **history never lives in the prompt; it lives in state.**

- **External state, not chat history.** Every step reads and writes a structured `SessionState` in SQLite: `plan`, `subtopics[]`, `queries_run[]`, `coverage{subtopic: score}`, `budget_left`, `step_log[]`.
- **Per-step context packing.** Each LFM call gets a freshly built prompt: role instructions (~300 tok), the current goal (~100), a compact state summary (~400), the top-k retrieved chunks (~2k), and an output schema (~200). No rolling transcript.
- **Rolling summaries.** After each research iteration, the LFM compresses what it learned into ≤150 tokens per subtopic. Raw results go into RAG, never into the prompt.
- **Interview context.** The audio model (32k) gets the persona, the current question, its grounding chunks, and the last 2–3 turns. Earlier turns are summarized into "candidate so far: …".
- **Self-correction loop with budgets.**
  - Observe: coverage per subtopic is scored 0–1 by LFM from the retrieved chunks.
  - Correct: for each subtopic under 0.6, the agent rewrites the query (broaden, switch subreddit, add synonyms) and retries.
  - Guards: at most 3 research iterations, at most N Nimble calls, a wall-clock cap, and dedupe on URL and query. On budget exhaustion it proceeds with what it has and records the gap.
  - Failure handling: Nimble errors or empty results trigger backoff plus an alternate query. Malformed LFM JSON triggers a schema-constrained retry, then a deterministic fallback.
- **Trace everything.** Each step emits `{step, input_summary, action, result_summary, tokens, latency_ms}`. The trace goes to the UI live and to RawTree at the end.

---

## 5. Component specs

### 5.1 Planner (LFM2.5-2.6B)
- In: topic, optional company/level, recall summary from RawTree.
- Out (JSON schema): `persona_system_prompt`, `subtopics[3–6]`, `queries[{q, subreddit, subtopic}]`.

### 5.2 Research (Nimble)
- Web search scoped to Reddit (a site/subreddit filter or a `site:reddit.com/r/<sub>` query), then fetch or parse the thread content.
- Normalize to `{url, subreddit, title, body, top_comments[], score, created_at}`.
- *Verify on day 1:* Nimble's search endpoint, its Reddit parsing, rate limits, and response latency.

### 5.3 RAG ingest
- Chunk at ~300 tokens with overlap, embed, and store with metadata (subtopic, subreddit, url, upvotes).
- Retrieval: hybrid (vector + keyword), boosted by upvotes and recency.

### 5.4 Question bank
- The LFM extracts `{question, subtopic, difficulty, source_url}` from the top chunks for each subtopic.
- Dedupe against RawTree's `asked_questions` for this user (by embedding similarity).

### 5.5 Interviewer (LFM2.5-Audio-1.5B)
- Speech in → transcript → follow-up decision → speech out at 24 kHz.
- Follow-ups are grounded in retrieved chunks ("Candidates on r/systemdesign said interviewers pushed on X…").

### 5.6 Evaluator (LFM2.5-2.6B)
- Per answer: a rubric score (1–5) on correctness, depth, communication, and tradeoffs, plus a one-line feedback note and the evidence chunk IDs.

---

## 6. RawTree / Tinybird: how we use the analytics data

**JSON in:** at session end, write one document per session (plus child rows for questions and trace steps). We don't flatten it by hand; RawTree accepts semi-structured JSON.

```json
{
  "session_id": "…", "user_id": "…", "ts": "…",
  "topic": "System design: rate limiter", "topic_embedding": [/* float32 */],
  "subtopics": ["token bucket", "distributed counters", "…"],
  "queries": [{"q": "…", "subreddit": "systemdesign", "results": 12, "useful": 7}],
  "questions": [{"text": "…", "subtopic": "…", "score": 3, "source_url": "…"}],
  "trace": [{"step": "RESEARCH", "iter": 2, "latency_ms": 4100, "tokens": 3650}],
  "corpus_ref": "local://corpora/<hash>"
}
```

**SQL out:** the agent runs these queries itself during RECALL. This is what makes each session smarter than the last:

| Use | Query idea | How the agent acts on it |
|---|---|---|
| **Similar-session recall** | `ORDER BY cosineDistance(topic_embedding, {new}) LIMIT 5` | Seeds the planner with past subtopics and gaps |
| **Weak-area targeting** | `avg(score) GROUP BY subtopic` for this user, lowest first | Weak subtopics get more questions, asked earlier |
| **No repeats** | questions asked in the last N sessions on similar topics | Filtered out of the question bank |
| **Source quality** | `useful/results GROUP BY subreddit, subtopic` | Planner favors high-yield subreddits and query styles |
| **Corpus cache** | a similar session within 7 days with a high-coverage corpus | **Skips or shortens Nimble research**, which cuts the longest phase |
| **Agent self-tuning** | avg iterations, retries, and latency per step | Adjusts research budgets and shows agent health in the demo |
| **Progress** | score trend over time per subtopic | The user-facing progress chart in the demo |

Example:
```sql
-- weak areas for this user across sessions similar to the new topic
SELECT q.subtopic, avg(q.score) AS avg_score, count() AS n
FROM session_questions q
JOIN (
  SELECT session_id FROM sessions
  WHERE user_id = {uid}
  ORDER BY cosineDistance(topic_embedding, {topic_vec}) LIMIT 10
) s USING session_id
GROUP BY q.subtopic
ORDER BY avg_score ASC
LIMIT 3;
```

Wrap these as **Tinybird pipes / API endpoints** so the orchestrator calls a named endpoint (e.g. `/recall`, `/weak_areas`) instead of shipping SQL strings around.

---

## 7. Build order

Build a thin end-to-end path first, then deepen. Each milestone ends in something demoable.

| # | Milestone | Done when |
|---|---|---|
| 0 | **Spikes (first ~2h, in parallel)** | Nimble returns Reddit threads for one query. LFM2.5-2.6B Q4 answers under a JSON schema on CPU. The audio model does one speak/listen round trip. RawTree accepts a JSON insert and returns a SQL query. Record latency for each. |
| 1 | **Text-only E2E** | Topic → plan → one Nimble pass → RAG → 3 questions → typed answers → scores → row in RawTree |
| 2 | **Self-correction loop** | Coverage scoring, query rewrite, budgets, and the trace log. A seeded thin topic visibly triggers a retry. |
| 3 | **Recall from RawTree** | A second session on a similar topic uses weak areas and dedupe, and gets a corpus-cache hit. |
| 4 | **Voice** | LFM2.5-Audio swapped in for the interview loop. |
| 5 | **UI polish** | Live trace panel, progress chart, and pre-processing progress bar |
| 6 | **Demo hardening** | Pre-seeded RawTree history, a warm model load, offline fallbacks, and a rehearsed script |

**Cut line if time is short:** drop voice (keep text) before dropping the self-correction loop or RawTree recall. Those two carry the Autonomy and Technical scores.

**Suggested split for 3 people:** (A) orchestrator + LFM + context packing, (B) Nimble + RAG + question bank, (C) RawTree schema/pipes + UI + audio.

---

## 8. Three-minute demo script

1. **0:00–0:20 Problem:** generic prep questions are stale; real candidates post what they were *actually* asked.
2. **0:20–1:10 Autonomy:** type the topic and press start. The trace panel streams: recall hits RawTree ("weak: distributed counters"), the plan appears, Nimble queries fire live, coverage on one subtopic comes back low, the agent rewrites the query and retries, and the corpus is built.
3. **1:10–2:10 Interview:** a voice Q&A for two questions, with a grounded follow-up that cites a Reddit thread.
4. **2:10–2:40 Memory:** scores are written to RawTree. The progress chart shows the trend across seeded past sessions, and a similar new topic gets a cache hit that skips research.
5. **2:40–3:00 Architecture slide:** 4k context, state not history, and each sponsor tool's role.

Record a backup video of the full run in case the network or hardware fails.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Nimble Reddit results are thin or slow | Cache results for the demo topics. The self-correction loop broadens queries. |
| Audio model is too slow on CPU | Pre-load and warm it up, keep responses short, fall back to text + system TTS |
| 4k context overflows | Token-count every prompt in the context builder and truncate retrieved chunks first |
| LFM JSON output is unreliable | Grammar/schema-constrained decoding, retry, deterministic fallback |
| RawTree vector functions or JSON types differ from ClickHouse | Spike on day 1. Fallback: compute similarity locally and store embeddings as `Array(Float32)` |
| Reddit content quality or ToS | Use only Nimble's sanctioned access, store snippets with source URLs, and don't redistribute raw content |

---

## 10. Open questions for the team

- How long is the hackathon, and how many people are building? This decides whether voice is in scope for milestone 4 or is a stretch goal.
- Does "on device" include the orchestrator only, or must everything except the Nimble and RawTree calls run offline? (This plan assumes the latter.)
- Is there a single user, or do we demo multiple profiles in RawTree?
- Which demo hardware will we use? CPU-only laptop RAM decides whether both LFM models stay loaded at once.
