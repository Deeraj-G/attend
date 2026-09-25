# ADR 0001: Architecture for the On-Device Interview Prep Agent

- **Status:** Proposed
- **Date:** 2026-09-25
- **Deciders:** Deeraj Gurram and the hackathon team
- **Context:** Long Horizon Agents Hackathon. The agent must plan, act, observe, and self-correct across a full cycle without drowning in its own history, and it must use 3+ sponsor tools.
- **Related:** [PLAN.md](../../PLAN.md)

---

## Context

We are building a mock interviewer that runs on a laptop CPU. The user starts a session and names a topic. The agent does the rest on its own:

1. It researches what real candidates report being asked, using live Reddit data.
2. It builds a grounded question bank.
3. It runs a spoken interview, scores it, and remembers the results for the next session.

Constraints that shape the design:

| Constraint | Source |
|---|---|
| Planner model has a **4k-token** input context (LFM2.5-2.6B, 4-bit, CPU, a few GB of RAM) | Liquid AI model limits |
| Audio model has a 32k context and 24 kHz output (LFM2.5-Audio-1.5B) | Liquid AI model limits |
| Web research is the slowest phase of the session | Nimble search plus thread fetch latency |
| Must show autonomy on live web data with no manual steps | Judging: Autonomy |
| Must use ≥3 sponsor tools meaningfully | Judging: Tool Use |
| Demo must fit in 3 minutes | Judging: Presentation |

## Decision

1. **Orchestration:** a Python orchestrator driven by an explicit **state machine**, not a free-form chat agent loop.
2. **Memory model:** **state, not history.** Every step reads and writes a structured `SessionState` in SQLite. Each LFM prompt is freshly packed to ≤4k tokens. Raw web content lives only in the local RAG store.
3. **Sponsor tool roles:**
   - **Nimble**: live web search scoped to interview subreddits.
   - **Liquid AI**: LFM2.5-2.6B handles planning, grading, and evaluation. LFM2.5-Audio-1.5B runs the voice interview.
   - **RawTree (Tinybird)**: long-term cross-session memory and analytics, with JSON in and SQL out exposed as Tinybird pipe endpoints.
4. **Self-correction:** a coverage-graded research loop with hard budgets (iterations, API calls, wall clock).
5. **Local RAG:** `sqlite-vec` or LanceDB plus a small CPU embedder. It is file-based and needs no server.

---

## Diagrams

### System context

```mermaid
flowchart LR
    User([Candidate])

    subgraph Device["Laptop (CPU only)"]
        UI["Web UI<br/>mic · transcript · agent trace · progress"]
        Orch["Orchestrator<br/>state machine + context builder"]
        State[("SessionState<br/>SQLite")]
        RAG[("Local RAG<br/>sqlite-vec / LanceDB")]
        Emb["Embedder<br/>small CPU model"]
        LFM["LFM2.5-2.6B<br/>Q4 · llama.cpp · 4k ctx"]
        Audio["LFM2.5-Audio-1.5B<br/>32k ctx · 24 kHz out"]
    end

    Nimble["Nimble<br/>Web Search API"]
    RawTree[("RawTree / Tinybird<br/>ClickHouse fork")]

    User <--> UI
    UI <-->|WebSocket| Orch
    Orch <--> State
    Orch --> LFM
    Orch <--> Audio
    Orch --> Emb --> RAG
    Orch <--> RAG
    Orch -->|search queries| Nimble
    Nimble -->|Reddit threads| Orch
    Orch -->|"JSON in"| RawTree
    RawTree -->|"SQL out (pipes)"| Orch
```

### Session state machine

```mermaid
stateDiagram-v2
    [*] --> RECALL: start session + topic
    RECALL --> PLAN: past sessions, weak areas, cache hit?
    RECALL --> BANK: fresh corpus cache hit
    PLAN --> RESEARCH
    RESEARCH --> OBSERVE
    OBSERVE --> RESEARCH: coverage < 0.6 and budget left
    OBSERVE --> BANK: coverage ok or budget exhausted
    BANK --> INTERVIEW
    INTERVIEW --> INTERVIEW: next question / follow-up
    INTERVIEW --> EVALUATE: questions done or user ends
    EVALUATE --> PERSIST
    PERSIST --> [*]
```

### End-to-end session sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant O as Orchestrator
    participant T as RawTree
    participant L as LFM2.5-2.6B
    participant N as Nimble
    participant R as Local RAG
    participant A as LFM2.5-Audio

    U->>O: start(topic)
    O->>T: /recall, /weak_areas, /asked_questions
    T-->>O: similar sessions, weak subtopics, dedupe list

    O->>L: plan(topic, recall summary) [≤4k]
    L-->>O: persona prompt, subtopics, queries

    loop Research (max 3 iterations)
        O->>N: search(query, subreddit)
        N-->>O: threads
        O->>R: chunk + embed + index
        O->>L: grade coverage per subtopic [≤4k]
        L-->>O: coverage scores
        alt coverage low and budget left
            O->>L: rewrite queries for gaps
            L-->>O: new queries
        end
    end

    O->>R: retrieve top chunks per subtopic
    O->>L: extract questions [≤4k]
    L-->>O: question bank (deduped vs RawTree)

    loop Each question
        O->>A: ask(question, persona, grounding)
        A-->>U: speech (24 kHz)
        U->>A: spoken answer
        A-->>O: transcript
        O->>L: score answer vs rubric + evidence
        L-->>O: score, feedback
    end

    O->>T: insert session JSON (questions, scores, trace)
    O-->>U: summary + progress chart
```

### Self-correcting research loop

```mermaid
flowchart TD
    Start([Plan: subtopics + queries]) --> Search[Nimble search<br/>scoped to subreddit]
    Search --> Empty{Results?}
    Empty -- "no / error" --> Backoff[Backoff + alternate query] --> Budget
    Empty -- yes --> Ingest[Chunk · embed · index into RAG]
    Ingest --> Grade["LFM grades coverage<br/>per subtopic (0–1)"]
    Grade --> Check{All subtopics ≥ 0.6?}
    Check -- yes --> Done([Build question bank])
    Check -- no --> Budget{"Budget left?<br/>iters ≤ 3 · calls ≤ N · time cap"}
    Budget -- no --> Gap[Record gaps in trace] --> Done
    Budget -- yes --> Rewrite["LFM rewrites queries<br/>broaden · switch subreddit · synonyms"]
    Rewrite --> Search
```

### Per-step context packing (≤4k tokens)

```mermaid
flowchart LR
    subgraph Stores["Persistent (never in prompt wholesale)"]
        S[("SessionState")]
        R[("RAG chunks")]
        T[("RawTree history")]
    end

    subgraph Prompt["Packed prompt ≤ 4,000 tokens"]
        P1["Role instructions ~300"]
        P2["Current goal ~100"]
        P3["State summary ~400"]
        P4["Top-k chunks ~2,000"]
        P5["Output JSON schema ~200"]
    end

    S -->|summarize| P3
    R -->|retrieve + truncate first| P4
    T -->|recall digest| P3
    Prompt --> LFM["LFM2.5-2.6B"]
    LFM -->|"structured output<br/>+ ≤150-token rolling summary"| S
```

### RawTree data model

```mermaid
erDiagram
    SESSIONS ||--o{ SESSION_QUESTIONS : contains
    SESSIONS ||--o{ SESSION_QUERIES : ran
    SESSIONS ||--o{ TRACE_STEPS : logged

    SESSIONS {
        string session_id PK
        string user_id
        datetime ts
        string topic
        array_float32 topic_embedding
        json subtopics
        json coverage
        string corpus_ref
    }
    SESSION_QUESTIONS {
        string session_id FK
        string text
        array_float32 text_embedding
        string subtopic
        int difficulty
        int score
        string feedback
        string source_url
    }
    SESSION_QUERIES {
        string session_id FK
        string query
        string subreddit
        int results
        int useful
        int iteration
    }
    TRACE_STEPS {
        string session_id FK
        string step
        int iter
        int tokens
        int latency_ms
        string result_summary
    }
```

### How analytics feed back into the agent

```mermaid
flowchart LR
    subgraph Pipes["Tinybird pipe endpoints (SQL out)"]
        Q1["/recall<br/>cosineDistance on topic_embedding"]
        Q2["/weak_areas<br/>avg(score) by subtopic"]
        Q3["/asked_questions<br/>recent similar sessions"]
        Q4["/source_quality<br/>useful / results by subreddit"]
        Q5["/corpus_cache<br/>similar topic within 7 days"]
        Q6["/agent_health<br/>iters, retries, latency by step"]
    end

    Q1 --> Plan[Planner seed]
    Q2 --> Bank[Question ordering:<br/>weak areas first]
    Q3 --> Dedupe[Question dedupe]
    Q4 --> Queries[Subreddit / query choice]
    Q5 --> Skip[Skip or shorten research]
    Q6 --> Budgets[Tune loop budgets]
    Q2 --> Chart[User progress chart]
```

---

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. State machine + external state (chosen)** | Fits in 4k context, deterministic, easy to trace and demo, directly shows the "without drowning in history" requirement | More upfront schema design | ✅ |
| B. Free-form ReAct loop with chat history | Fast to prototype | Overflows 4k within a few steps, hard to debug, weak self-correction story | ❌ |
| C. Cloud LLM for planning, local only for audio | Bigger context, better reasoning | Breaks the on-device premise and the Liquid AI story, and adds latency and cost | ❌ |
| D. Store everything in RawTree, including the RAG corpus | One store | Network round trip per retrieval, and RawTree is analytics-oriented rather than a low-latency vector store | ❌ (RawTree keeps summaries and embeddings of sessions only) |

## Consequences

**Positive**
- The context budget is enforced by construction, so long sessions don't degrade.
- Every step is traced, which makes the agent's autonomy visible in the demo and queryable in RawTree.
- Cross-session memory makes each session better targeted, and a corpus-cache hit removes the slowest phase.

**Negative / risks**
- The small planner model may produce malformed JSON. Mitigation: schema-constrained decoding, a retry, then a deterministic fallback.
- Audio model latency on CPU is not yet known. Mitigation: warm-load the model and keep a text + system TTS fallback.
- RawTree's support for JSON types and `cosineDistance` needs to be verified. Fallback: `Array(Float32)` columns with similarity computed locally.
- Nimble's Reddit coverage and latency still need a day-1 spike. Mitigation: cache results for demo topics.

## Follow-ups

- [ ] Spike Nimble, LFM2.5-2.6B Q4, LFM2.5-Audio, and RawTree. Record latency for each.
- [ ] Freeze the `SessionState` and RawTree schemas.
- [ ] Write ADR 0002 on the RAG store choice (sqlite-vec vs LanceDB) after the spikes.
