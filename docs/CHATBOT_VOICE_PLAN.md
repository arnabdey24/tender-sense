# Tender assistant: widget, live voice, and analysis workspace

Status: proposed for review. Planning only; no application implementation has started.
Date: 2026-09-10.

## Goal and agreed scope

Give a bidder a continuous conversation about a selected tender, using text,
English speech, Bangla speech, or a mixture. The assistant explains the existing
assessment, answers follow-up questions, and creates charts, calculations,
logical diagrams, and draft checklists in an expandable workspace.

The user confirmed English/Bangla/mixed speech and analysis plus draft creation
for the first version. Existing Bid/Hold/Skip decisions, company profiles, and
rules remain controlled through their existing application interfaces.

## Research findings

| Area | Existing implementation | Consequence for this feature |
| --- | --- | --- |
| Product | Shared tender pool, organization profiles, semantic matching, eligibility rules, decisions, notifications | Conversation needs both tender facts and the current organization's assessment. |
| Frontend | React 19, TypeScript, Vite, TanStack Router/Query, Zustand, shadcn Base UI | Add a feature module within the current app shell and use its design system. |
| Tender screen | `frontend/src/routes/_app/app/tenders/$tenderId.tsx` | Has overview, verdict, eligibility, decisions, and extracted requirements; natural entry point for “Discuss this tender.” |
| Match contract | `backend/app/modules/matching/schemas.py` | Already returns similarity, score breakdown, rule results, explanation, and several assessment versions. |
| Scoring | `backend/app/modules/matching/scoring.py` | Combines best capability similarity with the mean of the strongest capabilities; grades and recommendations are deterministic. |
| Rule evaluation | `backend/app/modules/rules/{engine,facts,service}.py` | Reuse money comparisons, missing-data behavior, source precedence, and recorded human overrides. |
| Existing explanation | `backend/app/ai/{explanation.py,prompts/explanation.py}` | Narrative phrases existing results; it does not independently decide the grade. Preserve this contract. |
| AI client | `backend/app/ai/base.py` | Supports embeddings and structured generation; lacks conversation streaming, tool orchestration, and live audio. |
| Evidence | `backend/app/ai/schemas.py`, tender document/extraction models | Quotes and extraction confidence exist; document text may be absent. Existing vector chunks serve matching, not a complete document retrieval system. |
| Authentication | `backend/app/core/deps.py`, frontend auth/client helpers | Organization comes from authenticated context; membership is checked on requests. HTTP dependencies need deliberate adaptation for long-lived sockets. |
| Deployment | `infra/caddy/Caddyfile`, `frontend/vite.config.ts` | Production currently sets `microphone=()`; development proxy lacks explicit WebSocket forwarding. |
| Tests | Scoring/rules/security backend suites; Vitest/MSW, axe, Playwright frontend | Extend these patterns; current browser smoke tests do not validate assistant or microphone flows. |

No competing chatbot implementation was found. The working tree was clean when
research began.

## Experience design

### Entry and context

- Show a bottom-right assistant launcher on authenticated organization workspace
  pages. On tender detail, also show “Discuss this tender.”
- Opening from a tender preselects it; opening elsewhere offers a tender picker
  using the existing tender search API.
- Keep a visible context strip: tender title/reference, organization, grade,
  eligibility, deadline, and when the assessment was produced.
- Bind each conversation to one tender and one organization. Visiting another
  page does not silently change the conversation's tender. “Discuss this tender”
  explicitly switches to that tender's thread, stopping any active voice session.
- Default history is private to the signed-in user within their organization.
  Reopening restores the last thread for that tender. Offer new conversation and
  delete conversation actions.
- Version changes produce an “Assessment updated” notice. Past answers retain
  their original evidence; subsequent turns use a newly recorded context snapshot.

### Three connected layouts

| Mode | Proposed desktop behavior | Contents |
| --- | --- | --- |
| Compact widget | Approximately 400 × 560 px, constrained to the viewport | Context strip, recent messages, suggestion prompts, text composer, live voice button |
| Expanded chat | Approximately 480–600 px wide, full available height | More readable thread, history access, richer inline previews |
| Analysis workspace | Broad overlay with adjustable split, initially about 40% conversation / 60% analysis | Chat remains visible beside charts, calculations, evidence, and drafts |

These sizes are starting points for the visual prototype. All modes share the
same session and mounted audio controller; resizing must not restart voice.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Tender assistant · Selected tender                 Minimize   Close │
├─────────────────────────┬───────────────────────────────────────────┤
│ Conversation            │ Capability fit                         ↗ │
│                         │                                           │
│ You: কেন Hold দেখাচ্ছে? │  [Chart] [Data] [Calculation] [Sources]   │
│                         │                                           │
│ Assistant: Your match   │  Network integration  ███████████         │
│ is strong, but one      │  Similar projects     ████████            │
│ requirement needs      │  Other capabilities   █████               │
│ verification. [Source]  │                                           │
│                         │  Assumptions / requirement comparisons    │
│ [Open eligibility map]  │  Previous versions · Copy · Download      │
├─────────────────────────┤                                           │
│ ◉ Listening…   Mute End │                                           │
│ Ask about this tender… │                                           │
└─────────────────────────┴───────────────────────────────────────────┘
```

The diagram is a layout illustration, not tender data. On phones, use a
full-screen surface with Conversation/Analysis tabs and persistent voice controls.
Respect safe areas and the software keyboard. Opening a generated preview expands
the workspace; an explicit request such as “show a graph” may open it directly.
Background completion should not steal focus from a user reading another item.

### Text conversation

- Starter prompts: “Explain this recommendation,” “Which requirements need
  checking?”, “Show our capability match,” and “Create a bid preparation checklist.”
- Stream answers with citations, tables, short explanations, and artifact previews.
  Display useful progress such as “Checking eligibility” or “Calculating the gap.”
- Support Stop, retry, copy, and follow-ups that refer to the active chart or draft.
- Keep partial answers visibly incomplete after an interruption or connection loss.
- Reply in the user's chosen language or follow their language in Auto mode.
  Preserve exact tender references, currency units, and source quotes. Label
  translations of evidence and provide the original text.

### Live voice and animation

- Voice starts through an explicit “Start live voice” action. Request microphone
  access then and show a brief explanation that audio is processed by the AI service.
- Use continuous conversational audio with speech detection, spoken answers, live
  captions, and interruption. The user can interrupt to correct a number or ask a
  follow-up; queued assistant audio stops promptly.
- Keep typing available. During live mode, typed turns go through the active live
  session, avoiding two assistants responding to the same turn.
- Use a small animated orb or waveform: input amplitude while listening, output
  amplitude while speaking, a distinct processing animation, and a static muted
  state. Animate with browser audio measurements and lightweight SVG/CSS/canvas.
- Explicit states: idle, requesting permission, connecting, listening, processing,
  speaking, muted, reconnecting, and error. Every state has a readable label.
- Controls: microphone mute, speaker mute, captions, and End voice. Speaker mute
  preserves captions. End voice releases media tracks and stops playback.
- Minimize during voice leaves a visible active-call strip with End. Close ends
  voice. Logout, organization changes, and session expiry also stop audio and
  clear private state. Do not automatically restart recording after an error.
- Honor reduced motion; do not use color or animation as the only state signal.
  Provide keyboard controls and clear permission-denied/no-device fallbacks.
- Validate Bangladeshi accents, mixed sentences, procurement abbreviations, lakh/
  crore, English/Bangla numerals, and spoken dates. Ask for clarification when an
  ambiguous transcription would materially change a calculation.

## What the analysis workspace generates

| Output | Grounding and interaction |
| --- | --- |
| Capability chart | Horizontal bars from recorded facet scores; show the score scale, labels, and source assessment. |
| Eligibility map | Requirement → company/tender values → rule result → recommendation, including evidence and overrides. |
| Calculation card | Inputs, units, formula, substitutions, result, rounding, and evidence. |
| Deadline timeline | Known dates plus clearly labeled user-defined preparation milestones. |
| Scenario chart | User-adjustable assumptions, baseline comparison, and recalculated results using deterministic tools. |
| Draft checklist | Grounded requirements and suggested preparation tasks, with unknown items called out. |

Each saved output is an artifact with a stable ID, version, title, originating
message, context version, typed payload, sources, assumptions, and timestamps.
The conversation can revise an existing artifact: “Make that a bar chart,”
“Use 15% instead,” or “Explain the second requirement in Bangla.” Preserve earlier
versions. Display chart data in an accessible table; support CSV for chart data,
SVG/PNG for charts where supported, and Markdown/text for drafts.

“Reasoning” here means a checkable explanation: evidence, the applicable rule,
calculation steps, assumptions, and conclusion. It must not promise access to
private model deliberations. A fluent explanation cannot substitute for evidence.

### Numerical fidelity

The current default semantic formula is:

`similarity = 0.6 × best_facet + 0.4 × mean(top_3_facets)`

The actual implementation reads configurable weights and thresholds. For an
illustrative set of scores 0.82, 0.76, and 0.70, the default formula gives 0.796.
This is a similarity measure, not a 79.6% chance of winning. Eligibility and
deadline logic separately determine the recommendation.

Current `score_breakdown` saves rounded top-five facet values and a count, but
does not save all formula inputs and weights. Record exact aggregation operands,
weights, top-N, and thresholds in future assessment provenance. Historical rows
without matching provenance must show an approximate illustration or explicitly
unavailable reconstruction; never apply today's configuration as if it were the
historical one. Preserve the existing scoring algorithm and results.

All arithmetic runs through tested server functions, with decimal-aware money
handling, currency checks, and explicit FX rate/date if conversion is used. A
turnover gap can be shown when both values exist; a profit forecast or win
probability cannot be inferred from an estimated tender value alone.

## Technical approach

### Conversation and analysis services

Add `backend/app/modules/assistant/` as a FastAPI vertical slice. It owns
conversations, messages, artifacts, context snapshots, streaming events, and
read-only analysis tools. Reuse existing tender/profile/match/rule services;
derive organization and user identity from authenticated context.

Initial tools: load tender context, explain recorded assessment, inspect
eligibility evidence, calculate supported comparisons, evaluate a hypothetical
scenario, and create/update a validated artifact. Scenario results are separate
from the official stored assessment.

Use discriminated Pydantic/Zod schemas for text, citations, chart specifications,
calculation cards, logical graphs, and checklists. Render approved structures;
do not execute model-generated JavaScript, arbitrary HTML, SQL, or Python.
Validate references against evidence loaded for this conversation. Treat tender
content and quoted documents as data, including any instructions embedded in them.

Start retrieval with the selected tender's available text and structured evidence.
Load additional stored document excerpts only where extracted text and provenance
exist. Missing text remains missing; existing matching embeddings do not by
themselves supply page-level document citations. General PDF/OCR ingestion is a
separate extension.

### Transport and persistence

- REST endpoints under `/api/v1/assistant` for conversation/history/artifacts,
  turn creation, cancellation, deletion, and short-lived voice tickets.
- Text turns: create a turn with a client-generated idempotency key, then consume
  its event stream through authenticated fetch using SSE framing. Share existing
  refresh coordination; do not blindly resend a generation after a disconnect.
- Events carry schema version, conversation ID, turn ID, event ID/sequence, and
  context version. Types include text delta, tool status, artifact update,
  transcript update, interruption, completion, and recoverable error.
- Persist final messages, tool outcomes, and artifacts in PostgreSQL. Use Redis
  for short-lived tickets, active turn coordination, and bounded event replay.
  On reconnect, replay from the last event ID or fetch persisted state if the
  replay window expired. Cancellation invalidates late updates from that turn.
- Conversations are scoped by organization and owner. Check both on all reads,
  writes, streams, and artifact downloads. Clear pending requests, cache, and
  audio on logout or organization switch.
- Store transcripts and artifacts by default, with a delete action and a
  configurable retention window (proposed initial default: 90 days). Do not
  persist raw microphone audio in the application by default. Provider data
  handling is separate and must be reflected accurately in the voice notice.

### Live audio provider

Use a separate conversation/live provider interface alongside the existing batch
`AIClient`, plus a deterministic fake implementation. Gemini Live is the first
candidate because the application already integrates Gemini. Google's current
documentation lists English and Bengali, transcripts, and interruption support;
this is capability evidence, not a guarantee of acceptable mixed-speech quality.
See [Live overview](https://ai.google.dev/gemini-api/docs/live-api) and
[capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).

Proposed first transport: browser → authenticated FastAPI WebSocket relay →
Gemini Live. Keep credentials, context assembly, tool execution, persistence,
and usage enforcement on the server. This adds a network hop and server load;
measure it before finalizing. A direct browser connection with restricted
[ephemeral tokens](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens)
is a later optimization if the relay misses the latency target.

Mint one-use, short-lived application socket tickets through authenticated REST.
Authenticate the socket with an initial ticket frame and a short handshake
timeout, so long-lived access tokens are absent from URLs and proxy logs.
Validate Origin, conversation ownership, and current membership. Enforce duration,
concurrency, payload, and usage limits; recheck authorization during long sessions.
Do not hold a database transaction open for the lifetime of a connection.

The browser audio controller handles capture, required PCM conversion, playback,
echo cancellation requests, and bounded buffering. Interruption clears queued
audio and cancels outstanding tool work. A single turn coordinator serializes
text/voice requests and ignores stale artifact updates.

Support provider connection rotation and session resumption. When resumption
fails, reconstruct from persisted conversation/context and disclose reconnecting.
Google documents session lifecycle controls in
[session management](https://ai.google.dev/gemini-api/docs/live-api/session-management).

Model selection needs an early technical trial: Google's
[tool guide](https://ai.google.dev/gemini-api/docs/live-api/tools) currently says
Gemini 3.1 Flash Live does not support asynchronous function calling. Keep initial
tools fast. For slower analysis, test an immediate job acknowledgment followed
by an application-managed result event and later narration; do not assume
uninterrupted tool-time conversation works on every model. Keep model IDs in
configuration. The Live API is currently documented as preview.

### Frontend composition

Use installed shadcn controls, adding the compatible Base UI chat primitives,
Chart, and Resizable components through the CLI after checking their APIs.
Shadcn provides [chat primitives](https://ui.shadcn.com/docs/changelog/2026-06-chat-components),
[Recharts-based charts](https://ui.shadcn.com/docs/components/base/chart), and
[resizable panels](https://ui.shadcn.com/docs/components/base/resizable).

Use a restricted math renderer for display, and an accessible SVG renderer for
typed logical nodes/edges. Lazy-load charts, math rendering, and live audio when
opened. Keep server data in React Query and local presentation/voice state in
the assistant store/controller.

## Implementation sequence

1. **Frontend interaction prototype.** Create the widget, context picker, three
   layouts, sample conversation, artifact previews, and animated voice states.
   Use explicit demo fixtures; simulated voice must be visibly labeled. Review
   desktop/mobile layouts and English/Bangla typography before integration.
2. **Voice feasibility trial.** Test real English/Bangla/mixed speech, interruptions,
   relay latency, captions, tool calls, and reconnection on target browsers.
   Select/configure the provider model from observed results. This happens early
   so audio constraints can inform the full implementation.
3. **Grounded text assistant.** Add persistence, authenticated streaming, context
   snapshots, evidence references, cancellation, and deterministic analysis tools.
   Connect the prototype to actual tender data.
4. **Interactive analysis workspace.** Add validated artifact creation, chart/data/
   formula/source views, artifact revisions, scenario inputs, and exports. Add
   exact future score provenance without changing matching behavior.
5. **Integrated live conversation.** Connect the tested audio transport to the
   same tools, history, artifacts, and turn coordinator. Drive animation from
   real input/output audio levels. Complete permission and lifecycle handling.
6. **Release validation.** Complete isolation, numerical, browser, accessibility,
   usage-limit, proxy, and recovery checks. Ship behind independently controlled
   assistant and voice feature flags.

### New files and modules

- `frontend/src/features/assistant/AssistantProvider.tsx`, `AssistantLauncher.tsx`,
  `AssistantWidget.tsx`, `AssistantWorkspace.tsx` — shell and layout modes.
- `frontend/src/features/assistant/TenderContext.tsx`, `Conversation.tsx`,
  `Composer.tsx`, `Citation.tsx` — tender selection and conversation UI.
- `frontend/src/features/assistant/artifacts/` — chart, formula, logical graph,
  checklist renderers, artifact history, and export helpers.
- `frontend/src/features/assistant/voice/` — session controller, transport,
  capture/playback worklets, controls, captions, and visualizer.
- `frontend/src/features/assistant/{api,stream,schemas,store}.ts` — contracts and
  state boundaries; associated component/transport tests alongside them.
- `backend/app/modules/assistant/{router,schemas,models,repository,service,context,tools,voice}.py`
  — domain slice; split larger transport/tool modules as necessary.
- `backend/app/ai/conversation/` — provider protocol, Gemini adapters, prompts,
  and fake conversation/live events.
- New Alembic migration — conversations, messages, artifacts, and any required
  usage/provenance storage. Use the next migration identifier at implementation.
- `backend/tests/unit/test_assistant_*.py`,
  `backend/tests/integration/test_assistant_*.py`,
  `frontend/e2e/assistant.spec.ts` — focused verification.

### Existing files modified

- `frontend/src/routes/_app.tsx` and tender detail route — mount assistant and
  add contextual entry action, with access only for eligible app sessions.
- `frontend/src/lib/api/query-keys.ts`, auth/session integration — user/org-scoped
  cache keys and teardown; regenerate `frontend/src/lib/api/schema.d.ts`.
- `frontend/src/index.css`, `frontend/package.json`, lockfile and added UI files
  — semantic visual tokens, verified Bangla font coverage, required dependencies.
- `frontend/src/mocks/{handlers,fixtures}.ts` — deterministic demo and test data.
- `backend/app/api/v1.py`, `backend/app/db/models.py` — register router/models.
- `backend/app/core/config.py`, `.env.example`, relevant Compose service
  environment entries — feature flags, model selection, limits, and timeouts.
- `backend/app/modules/matching/{scoring,service}.py` — additive exact score
  provenance for newly generated assessments; preserve the scoring result.
- AI usage/observability code — separate chat and audio usage with per-org caps;
  audio spending must not silently consume all matching capacity.
- `frontend/vite.config.ts`, `frontend/Caddyfile`, `infra/caddy/Caddyfile` — socket
  forwarding/streaming verification, `microphone=(self)`, and narrowly scoped
  audio/worklet/connection policy changes where needed.

## Tests and acceptance criteria

- Selected tender and organization remain correct across navigation, expansion,
  history restoration, organization switch, and deletion.
- Text and voice share history and artifact references without duplicate turns.
  Reconnect/retry cannot duplicate generation, and canceled tools cannot update
  an unrelated or newer conversation.
- Formula operands reproduce the stored score when provenance exists. Cover
  missing/rounded historical values, top-N variations, negative similarities,
  zero denominators, currency conversion, timezone boundaries, and unknown rules.
- Charts and logical diagrams agree with server data; unsupported/invented values
  are rejected. Hypotheticals never overwrite official results.
- Tenant/user isolation covers REST, stream replay, sockets, and downloads.
  Test expired/reused tickets, revoked membership, embedded document instructions,
  malformed artifacts, and duration/concurrency limits.
- Browser checks cover permission denial, no microphone, mute/end, output
  interruption, reconnect, mobile keyboard, tab/background behavior, and deployed
  Permissions-Policy/CSP. Test real Chrome, Safari, and mobile devices; mocks
  alone cannot establish voice quality.
- Keyboard/focus behavior, reduced motion, readable captions, chart data tables,
  and English/Bangla rendering pass automated and manual accessibility checks.
- Provisional targets to measure in the trial: p95 first text output within 3 s,
  simple voice response within 2 s of the detected end of speech, and local audio
  stopping within 250 ms after an interruption event. Report network, device,
  and model conditions; slower tool work gets a progress state.
- Run frontend lint/typecheck/tests/build and focused Playwright flows; backend
  lint/types/unit/integration checks, migration round-trip, OpenAPI freshness,
  and Compose/Caddy validation for the implementation.

## Boundaries, risks, and complexity

First release covers one selected tender per conversation. Cross-tender
comparison, uploads/OCR, open-web research, executable code notebooks, bid
submission, collaboration/sharing, and business-data updates through chat are
later extensions. Chat drafts are not automatically added to the official pipeline.

Primary risks are voice latency and mixed-language number accuracy; preview model
changes and tool-call limitations; insufficient evidence in scraped notices;
missing historical scoring operands; stream recovery; and concurrent audio load
on the existing single-VM deployment. The early voice trial, additive provenance,
bounded context, validated tools, isolated budgets, and targeted recovery tests
address these directly.

Estimated complexity: **High** for the complete feature. The first reviewable
deliverable is the frontend interaction prototype; it does not require the full
backend to establish the widget, workspace, and voice interaction design.
