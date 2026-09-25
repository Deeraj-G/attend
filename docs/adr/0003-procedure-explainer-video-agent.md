# ADR 0003: Procedure Explainer Video Agent on a Manage-Execute-Audit Harness

- **Status:** Proposed
- **Date:** 2026-09-25
- **Deciders:** Deeraj Gurram and the hackathon team
- **Relation to earlier ADRs:** This is a different use case from [0001](0001-interview-prep-agent-architecture.md) and [0002](0002-ad-campaign-mode-with-nimble-image-search.md). It reuses their core ideas: on-device LFM models, external state instead of chat history, and budgeted self-correction. It replaces their state machine with a **Manage-Execute-Audit** harness.

---

## Context

Patients are often nervous before a procedure, and a verbal explanation from a doctor is hard to picture. We want a doctor to **describe a procedure out loud** and have the agent produce a **short, calm, patient-friendly explainer video**. The doctor reviews and approves the video before any patient sees it.

The pipeline the team proposed:

| Step | Agent | Tool |
|---|---|---|
| 0 | Recorder | OSS audio capture (Python `sounddevice` + `soundfile`, or browser `MediaRecorder`) |
| 1 | TranscriptionAgent | Liquid AI **LFM2.5-Audio-1.5B** (speech-to-text) |
| 2 | ManagerAgent (long-running) | Liquid AI **LFM2.5-2.6B** (Q4, CPU, 4k context) |
| 3 | WebSearchAgent | **Nimble**: text, image and video search |
| 4 | AuditAgent | Independent review; discards irrelevant sources and triggers a re-search |
| 5 | VideoGenerationAgent | **Black Forest Labs**; the doctor can request edits |

This is a long-horizon task. It runs through many searches, audits, scene generations and edit rounds. The 4k-token manager would drown if it carried the full trajectory. The LongHorizon-Harness pattern (Manage → Execute → Audit, with an append-only external state memory of audit reports) solves this directly, and it is what the hackathon asks for.

### Constraints specific to healthcare

| Constraint | Implication |
|---|---|
| The recording may contain **PHI** (patient name, DOB, MRN, history) | Transcription runs on device. Only a **de-identified procedure description** may leave the device for Nimble or BFL. Any PHI in an outbound request or a returned source is an audit **violation**: the Auditor discards the offending item and the case continues (see [ADR 0004](0004-manager-agent-rule-based-scheduler.md)). |
| The video is patient education, **not medical advice** | The doctor's description is the source of truth. Web sources may only *enrich* it, never *contradict* it. Conflicts go back to the doctor. |
| Generated video can show wrong anatomy or be distressing | The style is calm, illustrative and non-graphic. **The doctor must approve before release** (a hard gate). |
| Source quality matters | Prefer authoritative sources (MedlinePlus, NHS, Mayo Clinic, specialty societies, hospital patient-education pages). Discard forums and marketing pages. |
| Web images and videos are not licensed for reuse | Nimble media results are **references for prompt writing only**. They never go into the output. |

## Decision

1. **Adopt the Manage-Execute-Audit harness.**
   - The **Manager** (LFM2.5-2.6B) is a state machine. It sees only the task and the audit reports V₁…Vᵢ, never the raw environment. Each round it emits one **subtask contract** cᵢ = {goal, acceptance criteria, boundaries, related report refs}. It can also take the **ask** route to the doctor.
   - The **Executors** (Transcription, WebSearch, VideoGeneration) run each contract in a **fresh, budgeted context**. They see the environment and the related reports only, and their trajectories are discarded.
   - The **Auditor** runs read-only in a clean context. It inspects the workspace and returns report Vᵢ with `status ∈ {complete, incomplete, blocked}`, `integrity ∈ {clean, suspect, violation}`, and `state_update = {facts, evidence, gaps}`.
   - **External State Memory:** reports are appended to `reports.jsonl`. They are the *only* thing the Manager reads, so memory grows by one report per round rather than with the trajectory.
   - **Terminate** when every subtask has status `complete`, integrity is `clean`, and the doctor has approved.
2. **Environment = a per-case workspace folder** (`cases/<case_id>/`): audio, transcript, de-identified brief, sources, storyboard, scene clips, final video. The Auditor checks artifact provenance (which executor wrote each file) and flags unexpected mutations or deletions.
3. **Decompose the video into scenes** (about 4–6, for example *before you arrive → check-in and prep → anesthesia → the procedure, shown non-graphically → recovery → going home*). Each scene is its own subtask contract. Edits regenerate a single scene, not the whole video.
4. **Build narration on device.** LFM2.5-2.6B writes a script at a 6th–8th grade reading level, and LFM2.5-Audio-1.5B voices it. The final video is BFL scene clips plus narration, stitched with `ffmpeg`.
5. **Put a PHI boundary at the device edge.** A de-identification step (rules for names, dates and IDs, followed by an LFM pass) produces the only text that may leave. The Auditor re-checks every outbound payload.
6. **Use the ask route (human in the loop) for:** conflicts between the doctor's description and the sources, `blocked` subtasks, and the **final approval gate**. Edit requests come back in by voice and are transcribed on device.
7. **Sponsor tools:** Liquid AI (two models), Nimble, Black Forest Labs. That makes 3. An optional 4th is **RawTree/Tinybird**, used as a queryable mirror of the report log and for analytics across cases (reuse audited sources and storyboards for the same procedure type).

---

## Diagrams

### Harness overview

```mermaid
flowchart LR
    Doctor([Doctor])
    Task["Long-horizon task T<br/>explainer video for a procedure"]

    subgraph Memory["External State Memory (append-only)"]
        V["V1 → V2 → … → Vn<br/>reports.jsonl"]
    end

    subgraph Manage["MANAGE · LFM2.5-2.6B"]
        M1["State read<br/>reads reports only"]
        M2["Dependency judgment<br/>next subtask"]
        M3["Contract ci<br/>goal · acceptance · boundaries · refs"]
    end

    subgraph Execute["EXECUTE · fresh context + budget"]
        E1["TranscriptionAgent<br/>LFM2.5-Audio STT"]
        E2["WebSearchAgent<br/>Nimble text / image / video"]
        E3["ScriptAgent<br/>LFM2.5-2.6B + Audio TTS"]
        E4["VideoGenerationAgent<br/>Black Forest Labs"]
    end

    subgraph Audit["AUDIT · read-only, clean context"]
        A1["Inspect workspace<br/>provenance · mutation · PHI"]
        A2["Report Vi<br/>status · integrity · facts / gaps"]
    end

    Env[("Environment e<br/>cases/case_id/")]

    Task --> Manage
    V -->|re-read each round| M1
    M1 --> M2 --> M3
    M3 -->|"① contract ci"| Execute
    Execute -->|acts read/write| Env
    Execute -->|"② output oi"| Audit
    Env -->|read-only| Audit
    A1 --> A2
    A2 -->|"③ append Vi"| V
    M2 <-->|ask route| Doctor
    Manage -. no access .-x Env
```

### Subtask plan (one contract per node)

```mermaid
flowchart TD
    S0["c0 · Record<br/>doctor audio → case workspace"] --> S1["c1 · Transcribe<br/>LFM2.5-Audio STT"]
    S1 --> S2["c2 · De-identify + brief<br/>procedure, steps, patient concerns"]
    S2 --> S3["c3 · Research<br/>Nimble text + image + video"]
    S3 --> S4["c4 · Source audit<br/>keep authoritative, drop the rest"]
    S4 -->|gaps| S3
    S4 --> S5["c5 · Storyboard<br/>4–6 scenes, calm, non-graphic"]
    S5 --> S6["c6 · Narration script + TTS<br/>6th–8th grade reading level"]
    S5 --> S7["c7..ck · Generate scene clips<br/>Black Forest Labs, one per scene"]
    S6 --> S8["Assemble<br/>ffmpeg: clips + narration + captions"]
    S7 --> S8
    S8 --> S9{"Doctor review<br/>ask route"}
    S9 -->|"edit: 'scene 3 too clinical'"| S7
    S9 -->|"edit: script wording"| S6
    S9 -->|approve| Done([Release to patient])
```

### End-to-end sequence

```mermaid
sequenceDiagram
    autonumber
    actor D as Doctor
    participant M as Manager (LFM2.5-2.6B)
    participant X as Executors
    participant N as Nimble
    participant B as Black Forest Labs
    participant A as Auditor
    participant S as reports.jsonl

    D->>X: record description (on device)
    M->>X: c1 transcribe
    X-->>A: transcript.txt
    A->>S: V1 complete · clean

    M->>S: read V1
    M->>X: c2 de-identify + brief
    X-->>A: brief.json
    A->>S: V2 complete · clean (no PHI found)

    loop Research until audited coverage is ok (budget ≤ 3)
        M->>S: read reports
        M->>X: c3 research(brief, gaps)
        X->>N: text / image / video search (de-identified)
        N-->>X: results
        X-->>A: sources.json
        A->>S: Vi incomplete · gaps (e.g. "recovery timeline missing")
    end

    alt source conflicts with doctor's description
        M->>D: ask: "Source says 2–4 h recovery, you said same-day. Which?"
        D-->>M: answer (injected into state)
    end

    M->>X: c5 storyboard, c6 script + TTS
    X-->>A: storyboard.json, narration.wav
    A->>S: complete · clean

    loop per scene
        M->>X: c7 generate scene k
        X->>B: prompt(scene k, style: calm illustrative)
        B-->>X: clip k
        X-->>A: scene_k.mp4
        A->>S: Vk complete / incomplete (regenerate)
    end

    M->>X: assemble video
    M->>D: ask: review video
    D-->>M: "scene 3 is too clinical"
    M->>X: regenerate scene 3 only
    M->>D: ask: review again
    D-->>M: approve
    A->>S: final: complete · clean · approved
```

### Audit decision

```mermaid
flowchart TD
    In([Executor output oi]) --> P{"PHI in any<br/>outbound payload?"}
    P -- yes --> Vio["Discard offending items<br/>integrity = violation<br/>list refs in data.discarded"]
    Vio --> Prov
    P -- no --> Prov{"Provenance ok?<br/>only allowed files changed"}
    Prov -- no --> Sus["integrity = suspect<br/>manager re-issues contract"]
    Prov -- yes --> Acc{"Acceptance criteria met?"}
    Acc -- no --> Inc["status = incomplete<br/>gaps listed"]
    Acc -- yes --> Con{"Consistent with doctor's<br/>description?"}
    Con -- no --> Blk["status = blocked<br/>ask route: conflict"]
    Con -- yes --> Ok["status = complete<br/>integrity = clean"]
    Sus --> R[(Append Vi)]
    Inc --> R
    Blk --> R
    Ok --> R
```

### Privacy boundary

```mermaid
flowchart LR
    subgraph Device["On device (never leaves)"]
        Audio["Doctor audio"] --> STT["LFM2.5-Audio STT"] --> Tx["Raw transcript<br/>may contain PHI"]
        Tx --> DeID["De-identify<br/>rules + LFM pass"]
        DeID --> Brief["De-identified brief<br/>procedure + steps only"]
        Script["Narration script"] --> TTS["LFM2.5-Audio TTS"]
        Reports[("reports.jsonl")]
    end

    Brief -->|audited outbound| Nimble["Nimble search"]
    Brief -->|audited outbound| BFL["Black Forest Labs"]
    Nimble --> Refs["Sources + media refs<br/>prompt inspiration only"]
    Refs --> Script
    BFL --> Clips["Scene clips"]
```

### Report schema (Vᵢ)

```mermaid
classDiagram
    class Contract {
        string id
        string subtask
        string goal
        string[] acceptance
        string[] boundaries
        string[] related_reports
        Budget budget
    }
    class Budget {
        int max_turns
        int max_seconds
        int max_api_calls
    }
    class Report {
        string id
        string contract_id
        Status status
        Integrity integrity
        Fact[] facts
        string[] evidence_paths
        string[] gaps
        Artifact[] artifacts
    }
    class Status {
        <<enumeration>>
        complete
        incomplete
        blocked
    }
    class Integrity {
        <<enumeration>>
        clean
        suspect
        violation
    }
    class Artifact {
        string path
        string written_by
        string sha256
    }
    class Fact {
        string claim
        string source
    }
    Contract --> Budget
    Report --> Contract : audits
    Report --> Status
    Report --> Integrity
    Report --> Artifact
    Report --> Fact
```

---

## Context budget (Manager ≤ 4k tokens)

The Manager never reads transcripts, sources or clips. It reads only a digest of reports:

| Slot | ~Tokens |
|---|---|
| Role + harness rules | 400 |
| Task T + de-identified brief | 400 |
| Task state Sᵢ (subtasks with status) | 300 |
| Latest reports (full) plus older reports (one line each) | 1,800 |
| Pending doctor answers | 200 |
| Contract JSON schema | 300 |

Executors get contract cᵢ plus the related reports only. Their step history is thrown away once they return oᵢ, following "dozens of steps → 1 report".

---

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Manage-Execute-Audit harness (chosen)** | Bounded context, independent verification, a natural human gate, matches the hackathon theme and the published pattern | More moving parts than a linear pipeline | ✅ |
| B. Linear pipeline, steps 0 → 5 | Simplest to build | No self-correction and no audit trail; one bad source poisons the video | ❌ |
| C. Single agent with a growing transcript | Few components | Overflows 4k within a few rounds; the executor judges its own work | ❌ |
| D. Use Nimble-found images and videos directly in the output | Realistic visuals | Licensing risk, and some are graphic | ❌ references only |

## Consequences

**Positive**
- The raw transcript never leaves the device, and every outbound payload is audited for PHI.
- Every claim in the video traces back to a report, and every report traces back to evidence files. That gives the doctor an audit trail to review.
- Scene-level contracts make doctor edits cheap and targeted.

**Negative / risks**

| Risk | Mitigation |
|---|---|
| BFL's video capability or API access is unconfirmed | **Spike on day 1.** Fallback: BFL image generation (FLUX) for keyframes per scene, animated with `ffmpeg` (Ken Burns pans, crossfades) and narrated |
| The Auditor can't "see" clips (LFM2.5-2.6B is text-only) | Audit scene prompts and metadata. Optionally caption sampled frames with a vision model (for example LFM2-VL, *unverified*). The doctor gate is the final visual check. |
| De-identification misses something | Rules first, LFM second, Auditor third. The demo uses a synthetic, non-patient recording only. |
| Generated anatomy is inaccurate or distressing | Illustrative, non-graphic style constraints in every prompt, plus the doctor approval gate |
| STT errors on medical terms | Show the transcript to the doctor for a quick fix. Keep a medical-term glossary in the brief. |
| Nimble media search parameters or coverage are unknown | Spike on day 1. Text-only research is enough for scripting. |

## Build order

| # | Milestone | Done when |
|---|---|---|
| 0 | Spikes | Mic capture → LFM2.5-Audio STT. LFM2.5-2.6B emits a contract under a JSON schema. Nimble text and image search. BFL generates one clip or image. Record latency for each. |
| 1 | Harness skeleton | Manager / Executor / Auditor loop over `reports.jsonl`, with stub executors and termination logic |
| 2 | Text path | Record → transcript → de-identified brief → Nimble research with an audit-driven re-search → storyboard + script |
| 3 | Media path | BFL scene generation, TTS narration, `ffmpeg` assembly |
| 4 | Doctor loop | Review UI, voice edit → single-scene regeneration, approval gate |
| 5 | Demo hardening | Synthetic case, cached Nimble results, pre-generated fallback clips, trace panel |

**Cut line:** keep the audit loop and the doctor gate. They are the core of the Autonomy, Technical and safety story. If BFL video is unavailable or slow, drop to the keyframe fallback.

## Demo script (3 min)

1. **0:00–0:20** Problem: patients are anxious before procedures, and a verbal explanation is hard to picture.
2. **0:20–0:45** The doctor records about 20 seconds: "We'll do a colonoscopy under light sedation…"
3. **0:45–1:40** The trace panel streams the rounds: contract → Nimble research → an audit drops a forum source and flags a missing recovery timeline → re-search → storyboard. The Manager's context stays flat while the report log grows.
4. **1:40–2:30** The video plays. The doctor says "scene 3 is too clinical", only scene 3 regenerates, and the doctor approves.
5. **2:30–3:00** Architecture: Manage-Execute-Audit, the PHI boundary, and the sponsor tools.

## Follow-ups

- [ ] Confirm Black Forest Labs video generation access; otherwise commit to the keyframe fallback.
- [ ] Confirm Nimble image and video search parameters.
- [ ] Confirm LFM2.5-Audio-1.5B's STT input format (sample rate, max clip length) and TTS voices.
- [ ] Decide whether to add RawTree as a 4th sponsor tool (report mirror + a cross-case source cache).
- [ ] Mark ADR 0001 and 0002 as *Superseded* if the team commits to this use case.
