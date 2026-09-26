---
name: ux-audit
description: Run a requested pre-launch UX audit with a feature-by-persona matrix, isolated browser tests, and an evidence-backed HTML report.
---

# Pre-launch UX audit

In Codex, invoke this skill with `$ux-audit`; in Claude Code use
`/coordinator-kit:ux-audit`. Follow the [runtime adapter](../../references/runtime.md).

Coordinate the five-stage workflow below for the current project. This is an audit of a
pre-launch product with derived personas, not observed user research. Create audit artifacts;
application changes and implementation of recommendations need their own authorization.

## Scope and saved progress

1. Use the explicit scope supplied with this invocation or in the user's current request,
   preserving its exact wording. If absent or ambiguous, immediately ask: "Which feature
   areas should this audit cover? You can name specific areas or say 'everything'." Then
   wait for the answer before inspecting the project, initializing records or dispatching.
   Do not substitute "everything" for an empty argument or stop at promising to ask later.
2. Run `coordinator-kit:bootstrap`'s database ensure/reconciliation as needed. Honor existing
   holds and guardrails. Create or resume one canonical audit task with the source request,
   scope, acceptance criteria, stage, artifact paths and run ledger. A repeat invocation is
   not permission to duplicate an active fleet; check its agents and saved progress first.
3. Allocate a unique `.coordinator-scratch/ux-audit/<audit-id>/` directory. Give each agent
   its own report path. Keep scope/count approvals and execution status in database records
   and events, with links to these artifacts; the reports are evidence, not another backlog.
   On retry, preserve every previous report and evidence file; allocate a new attempt id and
   path and append its result to the run ledger instead of overwriting the previous attempt.
   Preserve the final HTML and evidence under `docs/validation/ux-audit/<audit-id>/` or the
   project's recorded deliverable directory, and record that location in the audit task.

The coordinator dispatches research, browser testing and synthesis; it does not impersonate
all personas itself. Select the workspace's supported model or record the inherited model when
the host requires it. Follow `coordinator-kit:agent-brief-hygiene`: bounded inputs, owned outputs and no
recursive delegation. Forward blockers to the coordinator; workers do not ask the user directly.

## 1. Feature map

Dispatch one read-only researcher with the exact scope and
[feature-map prompt](../../references/ux-audit/01-feature-map.md). Resolve the linked reference relative to this
SKILL.md and fill its scope slot before dispatch; do not send an unresolved paste placeholder. Wait for `feature-map.md`.

Require stable feature ids, reachable entry points, core/supporting labels, audience evidence,
excluded areas and explicit coverage uncertainty. If purpose or scope cannot be established,
resolve that gap before proceeding. The researcher may also establish a permitted live/local
entry URL and startup instructions for later testers; this does not authorize browser runs yet.

## 2. Grounded personas

Dispatch one researcher with the feature map and
[persona prompt](../../references/ux-audit/02-personas.md). Wait for `personas.md`.

Derive 3–13 personas from the scope, product evidence and sourced market/competitor research.
Label assumptions and synthetic details; do not copy real personal data into personas. Cover
the ideal user, a skeptic, low tech comfort and a plausible adjacent audience. Record both
features with no natural audience and real audience needs with no supporting feature. Research
access limits remain disclosed uncertainties, not invented facts or analytics.

## 3. Matrix and approval

Dispatch one planner with both artifacts and
[matrix prompt](../../references/ux-audit/03-matrix.md). Wait for `matrix.md` and self-contained
numbered run briefs. Fill every input slot; use stable feature, persona, story and run ids.

Use targeted assignments plus a few deliberate cross-type runs. Each feature and each persona
needs coverage; exercise the core value action with diverse personas including the skeptic and
low-tech persona. A feature with no plausible audience is an explicit gap to resolve or remove
from scope with the user, never a fabricated pairing. Supporting features usually get one
representative run. Full Cartesian coverage is an offered alternative, never an automatic choice.

Present the concrete matrix, recommended total, optional Cartesian total, any thinning and risk
gaps. **Get the user's go-ahead for that matrix and run count before any tester dispatch**, even
when the initial scope was "everything". Record the exact approval and matrix revision in a
decision/question record. Reuse a matching approval on resume; changes to scope or runnable
items require updated approval. More cells do not resolve cross-feature/session-state risks.

## 4. Isolated persona runs

Before launch, establish the permitted environment, verified start URL, test accounts/data and
runtime/browser capabilities. A setup agent may start one authorized shared dev server if
needed; coordinate ownership and disable unintended outbound effects per project guardrails.
Launch one fresh agent per approved runnable item, in parallel up to available agent/browser
capacity; queue the remainder without merging cells or carrying a tester's context across runs.

Use the [tester prompt](../../references/ux-audit/04-tester.md), filled with only that item's full
persona brief, story, intention, feature/run ids, entry point and success/failure criterion.
Supply verified environment details, a new output path
`runs/<run-id>/<attempt-id>/report.md` and evidence paths in that attempt's directory.
Do not include implementation hints, other personas' reports or another run's observations.
Testers must not read source to solve the journey; cause analysis can happen after the run.

Assign an explicit tab per run and isolated browser contexts/profiles and test identities when
state matters. Separate tabs do not isolate shared accounts or server-side data. If isolation
is unavailable, provision it or record blocked cells; serialization is acceptable only with
verified reset state and fresh agents. Never count a harness/login block as persona abandonment.
Read-only testers own browser/data resources and report paths, not product-writing checkout lanes.

Require real controls/input, first-30-seconds evidence at each entry, persona-appropriate
viewport/language, relevant empty states and one recoverable mistake. Stop where the persona
would stop. Preserve completed, partial, abandoned and blocked outcomes separately, with exact
abandonment points, on-screen quotes and decisive screenshots. These are simulated reactions,
not measured human conversion rates. Wait for every approved item to finish or be explicitly
accounted for; preserve original reports intact for synthesis.

## 5. Synthesis and design review

Dispatch one synthesis agent with the feature map, full persona set, approved matrix, execution
ledger, every report/evidence path and relevant canonical task references, using the
[synthesis prompt](../../references/ux-audit/05-synthesis.md). It produces a draft HTML report with
feature/persona/cell rollups, positioning issues first, cross-type hypotheses, conflicting needs,
ranked abandonment findings and before/after mockups in the product's actual design language.

Arrange a genuine second-model opinion on the draft's key screens via the project's configured
reviewer, using `coordinator-kit:codex-second-opinion` when appropriate. A dispatched reviewer
owns that invocation. Have the synthesis agent incorporate it from saved artifacts and preserve
disagreements and rationale. This audit explicitly requires that opinion: if unavailable, keep
it pending and deliver the draft with that gap; only an explicit user waiver permits completion
without it. Do not invent consensus, install tools or silently substitute same-model self-review.

Validate the final self-contained HTML in a browser at phone and desktop sizes, in light/dark
themes. Keep CSS and assets embedded, make no external font/image/CDN requests, and confine wide
tables to their own scrolling containers. Label illustrative values and reconstructed before
views; after views are proposals. Include what works, actual execution coverage versus remaining
risk gaps, and instrumentation to confirm or reject the assumptions after launch.

Record the deliverable, limitations, second-opinion status and evidence in the audit task.
Proposed fixes enter canonical records with source references and remain proposals until
authorized. Report completion only for the approved audit coverage and required review; an
HTML file alone does not establish that the browser runs occurred. Resume blocked work from
the saved ledger and approval instead of silently rerunning or inventing missing results.
