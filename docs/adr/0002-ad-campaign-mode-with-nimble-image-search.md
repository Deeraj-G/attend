# ADR 0002: Ad Campaign Mode Using Nimble Image Search

- **Status:** Proposed
- **Date:** 2026-09-25
- **Deciders:** Deeraj Gurram and the hackathon team
- **Builds on:** [ADR 0001](0001-interview-prep-agent-architecture.md)

---

## Context

Nimble can search the web for images as well as text. That opens a second use for the same on-device agent: the user **speaks a product or campaign brief**, and the agent researches the audience and the visual landscape, then drafts an ad campaign.

The agent loop from ADR 0001 is not specific to interviews. It runs recall → plan → research ⇄ observe → build → review with the user → persist. Only the prompts, the search types and the final artifact change.

Constraints specific to this mode:

| Constraint | Implication |
|---|---|
| LFM2.5-2.6B is text-only | It cannot judge an image by looking at it. We rank images using their metadata (title, alt text, source page, dimensions) unless we add a vision model. |
| Images found on the web are not licensed for reuse | Found images serve as **references and a moodboard only**, never as final ad creative. |
| The stack has no image generator | The output is copy, a creative brief and a moodboard. Final visuals are a stretch goal or a handoff. |
| The demo lasts 3 minutes | Showing both modes in full is too much. See Decision 5. |

## Decision

1. **Generalize the orchestrator into "session modes".** Each mode is a config: `{planner_prompt, search_plan_schema, coverage_rubric, builder, reviewer, persist_schema}`. The state machine, context packing, budgets and trace are shared with no changes.
2. **Add an `ad_campaign` mode** with two kinds of research:
   - **Nimble web search** on Reddit, reviews and forums to find audience pain points, the words customers use and competitor claims.
   - **Nimble image search** to collect visual references, competitor ads and brand-adjacent aesthetics.
3. **Rank images from metadata by default.** An optional vision model (for example LFM2-VL, *not yet verified*) can re-rank the top candidates and tag them with style, color and subject.
4. **Store campaigns in RawTree** so we can see which angles, styles and audiences the user approves or rejects. Each future campaign then starts from those preferences.
5. **Demo plan:** interview prep stays the primary demo. Ad campaign is a stretch goal, shown for about 20 seconds as "same agent, different mode". This keeps the demo focused while showing that the architecture is general.

---

## Diagrams

### One agent core, two modes

```mermaid
flowchart TB
    Voice["Voice / text input<br/>LFM2.5-Audio-1.5B"] --> Router{Session mode}

    Router -->|interview_prep| IP["Mode config: interview<br/>persona · subreddit queries · rubric"]
    Router -->|ad_campaign| AC["Mode config: ad campaign<br/>brief parser · web + image queries · creative rubric"]

    subgraph Core["Shared agent core (ADR 0001)"]
        SM["State machine<br/>RECALL → PLAN → RESEARCH ⇄ OBSERVE → BUILD → REVIEW → PERSIST"]
        CTX["Context builder ≤4k"]
        TR["Trace + budgets"]
    end

    IP --> Core
    AC --> Core
    Core --> NW["Nimble web search"]
    Core --> NI["Nimble image search"]
    Core --> RAG[("Local RAG<br/>text + image metadata")]
    Core --> RT[("RawTree")]

    NI -.->|ad_campaign only| Core
```

### Ad campaign session sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant A as LFM2.5-Audio
    participant O as Orchestrator
    participant T as RawTree
    participant L as LFM2.5-2.6B
    participant N as Nimble
    participant R as Local RAG

    U->>A: speaks the brief ("eco water bottle for hikers, playful tone")
    A-->>O: transcript
    O->>L: parse brief into product, audience, tone, channels [≤4k]
    L-->>O: structured brief
    O->>T: /brand_prefs, /similar_campaigns
    T-->>O: approved angles and styles, rejected ones

    O->>L: plan research (web queries + image queries)
    L-->>O: search plan

    loop Research (max 3 iterations)
        par Audience research
            O->>N: web search (reddit, reviews, forums)
            N-->>O: posts and pages
        and Visual research
            O->>N: image search (references, competitor ads)
            N-->>O: image URLs + metadata
        end
        O->>R: index text chunks + image metadata
        O->>L: grade coverage (pain points, angles, visual styles)
        alt gaps and budget left
            O->>L: rewrite queries
        end
    end

    O->>L: draft 3 campaign angles, each with headlines, body copy, CTA and moodboard picks
    L-->>O: campaign drafts
    O->>A: read the options aloud
    A-->>U: speech
    U->>A: "More like option 2, less corporate"
    A-->>O: feedback transcript
    O->>L: revise option 2
    O->>T: insert campaign JSON (brief, angles, picks, approvals)
    O-->>U: campaign board (copy + moodboard + sources)
```

### Image research and selection pipeline

```mermaid
flowchart LR
    Q["Image queries<br/>from planner"] --> NI["Nimble image search"]
    NI --> Meta["Normalize<br/>url · title · alt · source page · size"]
    Meta --> Filter{"Usable?<br/>size, dedupe, safe"}
    Filter -- no --> Drop([discard])
    Filter -- yes --> Embed["Embed metadata text"]
    Embed --> Rank["Rank vs brief + brand prefs<br/>(RawTree)"]
    Rank --> VL{"Vision model<br/>available?"}
    VL -- yes --> Tag["Re-rank + tag<br/>style · palette · subject"]
    VL -- no --> Board
    Tag --> Board["Moodboard<br/>references only, with source links"]
```

### RawTree additions for campaigns

```mermaid
erDiagram
    CAMPAIGNS ||--o{ CAMPAIGN_ANGLES : proposes
    CAMPAIGNS ||--o{ CAMPAIGN_IMAGES : references
    CAMPAIGNS ||--o{ TRACE_STEPS : logged

    CAMPAIGNS {
        string campaign_id PK
        string user_id
        datetime ts
        string mode
        json brief
        array_float32 brief_embedding
        string status
    }
    CAMPAIGN_ANGLES {
        string campaign_id FK
        string angle
        string headline
        string body
        string cta
        array_float32 angle_embedding
        bool approved
        string feedback
    }
    CAMPAIGN_IMAGES {
        string campaign_id FK
        string image_url
        string source_page
        string query
        json tags
        float rank_score
        bool picked
    }
    TRACE_STEPS {
        string campaign_id FK
        string step
        int iter
        int tokens
        int latency_ms
    }
```

### How campaign analytics feed back

| Pipe endpoint | SQL idea | How the agent uses it |
|---|---|---|
| `/brand_prefs` | approval rate by angle type and image tag, per user | Favors approved tones and styles and avoids rejected ones |
| `/similar_campaigns` | `cosineDistance(brief_embedding, {new})` | Reuses research and angles from similar past briefs |
| `/image_query_yield` | `picked / returned` by query pattern | Improves future image queries |
| `/angle_performance` | approval rate by angle and audience | Orders the options it proposes |

---

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Mode config on the shared core (chosen)** | Reuses all of ADR 0001, and a second mode shows the architecture is general | Mode configs need a stable interface early | ✅ |
| B. Pivot entirely to ad campaigns | Visual demo, and a clear commercial story | Throws away the interview design, and image selection is weak without a vision model | ❌ for now; revisit if the team prefers |
| C. A separate app for campaigns | Independent development | Duplicate orchestration, and two half-finished demos | ❌ |
| D. Use found images directly as ad creative | Looks finished | Copyright and licensing risk | ❌ |

## Consequences

**Positive**
- Nimble is used for two search types, which strengthens the Tool Use criterion.
- The "same agent, new mode" story supports the Idea and Technical Implementation criteria.
- RawTree preference learning carries over across modes.

**Negative / risks**
- Without a vision model, image ranking relies on metadata, which may be noisy. Mitigation: show source links, let the user pick, and log picks to RawTree.
- Scope creep. Mitigation: build this mode only after ADR 0001 milestones 1–3 work end to end.
- Licensing. Mitigation: the moodboard is labeled "references" and always links to sources.

## Follow-ups

- [ ] Verify Nimble's image search endpoint: parameters, metadata returned, rate limits.
- [ ] Decide whether to add a vision model (for example LFM2-VL). Check RAM headroom next to the other two models.
- [ ] Define the `ModeConfig` interface in the orchestrator before milestone 2.
- [ ] Team decision: keep ad campaign as a stretch mode, or pivot to it (Option B).
