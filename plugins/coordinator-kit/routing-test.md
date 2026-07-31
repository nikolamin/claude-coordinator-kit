# Skill routing test — coordinator-kit plugin

Tests whether each of the 13 `coordinator-kit` skills fires on the kind of prompt a founder or
a coordinator session actually produces mid-work — not on a paraphrase of its own description.
Run this after the plugin is installed and loaded (see Prerequisites).

## Sources and blind-authorship disclosure

This document's prompts were written from **CLAUDE.md, PROCESS.md, the root README.md, the
plugin README.md (`plugins/coordinator-kit/README.md`), and codex-setup.md only** — the
original ~545-line rule set the skills were carved out of, plus the surrounding kit docs. No
`SKILL.md` under `plugins/coordinator-kit/skills/` was opened; only its directory listing was
read (via `find`), never its content. If a prompt below fails to route, that is a finding about
the skill's `description` frontmatter, not about how well this document could paraphrase it —
the author never saw that frontmatter.

## A1 — Session isolation protocol

**The problem.** A skill's body stays loaded for the rest of its session once invoked, so a
later prompt in the same session can route on leftover content instead of on its own phrasing —
a false pass (the "wrong" skill's content already half-answers it) or a false miss (the model
reuses what's already loaded instead of pulling in a fresh skill). Testing every prompt cold in
its own fresh session removes that risk entirely, but 23 prompts in 23 sessions is not a cost
anyone will actually pay. This protocol spends full isolation only where contamination would
corrupt the exact thing being measured, and accepts a bounded, documented risk everywhere else.

**Rule 1 — boundary prompts run solo.** Each of the 6 boundary-pair prompts (Section A2, "S1"
through "S6") is the *only* message sent in a brand-new session — nothing before it, nothing
after it. These prompts exist specifically to see which of two overlapping skills wins at the
margin; any other coordinator-kit content already in context changes what "wins" means, which
defeats the one measurement this pair was built to take. Non-negotiable, regardless of session
budget.

**Rule 2 — one negative runs solo cold.** One negative prompt (S7) also gets its own fresh,
single-prompt session, as a clean baseline: does anything in this plugin ever fire with zero
prior context on an ordinary request. The other three negatives are deliberately placed as the
second prompt in a paired session instead (Rule 3) — a non-fire there is a *stronger* signal
than a cold non-fire, since it shows the plugin resists over-firing even once other skill
content is already sitting in context, which is the more realistic shape of a live coordinator
session.

**Rule 3 — everything else runs in cold+warm pairs of exactly two.** The remaining 16 prompts
(13 unambiguous positives + 3 negatives) are grouped into 8 sessions of two prompts each: send
the first ("cold" — nothing yet loaded), observe and record, then send the second ("warm" — one
skill's content now sitting in context) in the *same* session, observe and record separately.
Never a third prompt in one of these sessions — contamination depth is capped at exactly one
prior skill load, uniformly, so a "warm" result always means the same thing across the whole
table. Pairs are chosen so the two skills sharing a session are not ones CLAUDE.md cites by
name against each other (e.g. never pair a skill with one it explicitly tells a brief to
"restate," never pair the two halves of the stop/resume protocol). The source document is
heavily cross-referenced throughout — perfect pairwise avoidance isn't achievable without
solo-isolating all 23 prompts, which Rule 1's cost argument already rejected — so residual
coupling is accepted here and handled by Rule 4 instead of engineered away.

**Rule 4 — fallback for a surprising warm result.** If a "warm" prompt misses, over-fires, or
loads the wrong skill, don't record that as a confirmed finding yet: re-run that single prompt
alone in one more fresh session first. If it reproduces cold, it's real — write it up. If it
only happened warm, the finding is "this skill's boundary is sensitive to nearby loaded
content," worth a note in Section A4, but a different problem from a broken description and
should not be filed as one.

**Session count.** 6 (Rule 1) + 1 (Rule 2) + 8 (Rule 3) = 15 fresh sessions for 23 prompts, plus
any Rule 4 re-tests. Every skill gets at least one cold read; every boundary line and one
negative gets a fully clean read; nothing shares a session with its own boundary counterpart.

## A2 — Prompts

Each entry: session/slot, prompt text, intended skill (or "none"), and why a founder or
coordinator session would actually phrase it that way. Within a session, send prompts in the
order listed — cold first, warm second.

### Boundary pairs (solo sessions, Rule 1)

**S1 — solo — target: execute-loop vs. verification-standard**
> The build agent says it re-ran the whole suite after rebasing and everything's green — are we
> clear to push now, or is there another check that has to happen first?

Sits on the push gate itself: sounds like the execute loop's own commit rule, but "another
check" could just as easily mean the verification standard.

**S2 — solo — target: execute-loop vs. verification-standard**
> How do we actually know the verifier isn't just rubber-stamping what the build agent already
> claimed?

The "not a rubber stamp" worry belongs to both the loop mechanics and the pass-quality bar — a
founder asking this wouldn't care which section owns the answer.

**S3 — solo — target: escalation vs. codex-second-opinion**
> We've hit the same wall twice now on this architecture question — what do we do, get another
> opinion from outside Claude or just keep grinding on it internally?

"Hit the same wall twice" is the literal retry-ceiling trigger; "opinion from outside Claude"
reaches for the external-CLI idea even though architecture calls aren't its named use case.

**S4 — solo — target: escalation vs. codex-second-opinion**
> For the marketing copy on the landing page, should that get run past GPT too before we ship
> it, or is that overkill?

Copy is a named GPT-review case, but "is that overkill" is a judgment call about whether to
bother escalating at all.

**S5 — solo — target: comms-register vs. question-protocol**
> When you ping me on Telegram about something you need a decision on, keep it short, right? I
> don't want a whole essay.

"Ping me on Telegram... short" is notify-channel etiquette; "something you need a decision on"
is exactly what triggers the structured-question rules.

**S6 — solo — target: comms-register vs. question-protocol**
> What's the actual difference between a checkpoint update and you asking me something —
> structurally, how are those two messages supposed to look different?

Directly invites comparing the two message formats, the way someone genuinely unsure which
rule governs which message would ask it.

### Negative control, solo (Rule 2)

**S7 — solo — target: none**
> Can you explain the difference between a git rebase and a git merge? I always mix them up.

Plain git question — no coordinator concept anywhere in it.

### Cold+warm pairs (Rule 3)

**S8 — cold — target: agent-brief-hygiene**
> Before you fire that off — does the brief actually say where the files are, or is the agent
> going to have to go dig around for them itself? And it doesn't remember any of this
> conversation, right, so whatever it needs has to be written into the prompt itself?

Names two specifics — exact-file naming, self-contained prompts — the way someone reviewing a
draft brief out loud actually talks.

**S8 — warm — target: phase-loop**
> Quick one — once Plan is approved you go straight into Execute, right? And where's the actual
> milestone breakdown supposed to live, plan.md or somewhere under docs/coordination?

Checking a mental model of the phase sequence and doc layout mid-project, not reading it fresh.

**S9 — cold — target: execute-loop**
> If a build agent comes back green locally but I haven't heard whether CI actually passed, are
> we allowed to push yet or does that have to wait?

The local-vs-CI push gate, asked the way someone impatient to ship would ask it.

**S9 — warm — target: backlog-discipline**
> While you were building that thing you noticed the auth flow was broken too — where's that
> going, are you just going to remember it or is it written down somewhere?

Catching a side-discovery and checking it doesn't just evaporate.

**S10 — cold — target: verification-standard**
> The verifier just said the mobile layout looks fine — did they actually resize the browser
> and check the width, or just eyeball a screenshot at desktop size?

Pokes at one of the standard's specific gotchas (a resize call that silently no-ops) without
naming it.

**S10 — warm — target: credential-handling**
> Here's the database root password, just go ahead and log in and pull whatever you need —
> don't make a whole production out of it.

Handing over a credential and pre-empting the caution expected back.

**S11 — cold — target: escalation**
> This is the second time the build agent has come back with the same broken migration —
> what's the actual protocol before you just keep throwing more attempts at it?

Names the retry-ceiling scenario directly, in an irritated register.

**S11 — warm — target: stop-and-save**
> I've got to close my laptop for the night — can you wrap up wherever you are so I don't lose
> the thread when I open this back up tomorrow?

Ends a session without using the literal trigger phrase, the way someone actually signs off.

**S12 — cold — target: codex-second-opinion**
> Before you write the landing page copy yourself, is that Codex CLI thing actually set up on
> this machine, or do I need to log into it first?

Asks about install/login state directly, the offhand way someone half-remembers a tool name.

**S12 — warm — target: question-protocol**
> When you actually need a decision from me on something, can you just ask me the one thing
> instead of dumping five questions on me at once like you did last time?

A specific, annoyed callback to being over-asked — a real complaint, not a description
paraphrase.

**S13 — cold — target: watchdogs**
> It's been like 40 minutes and I haven't heard anything from the two agents you kicked off
> earlier — is something actually stuck, or are you just not going to tell me until they're
> done?

The stall/no-news scenario a founder would actually notice and ask about.

**S13 — warm — target: comms-register**
> Can you text me a real update, not paragraphs — I'm on my phone, just tell me what's running
> and whether you need anything from me.

A plain status ask with the phone/brevity constraint spelled out, no decision attached.

**S14 — cold — target: bootstrap**
> This is a repo I already started with you a while back — don't re-run the whole setup thing,
> just pick up from wherever we left off.

Explicitly heads off a fresh bootstrap — the resume case in a founder's own words.

**S14 — warm — target: none**
> What's a clean way to debounce a search input in React without pulling in lodash?

Ordinary coding question.

**S15 — cold — target: none**
> Is Postgres or SQLite the better call for a small side project's local dev database?

Ordinary tech-choice chat, nothing coordinator-specific.

**S15 — warm — target: none**
> What's the syntax for a Python dict comprehension with a conditional filter?

Pure language-syntax question.

## A3 — Observation instructions

For every prompt, watch the transcript **before** reading the assistant's reply:

- A skill firing shows up as a tool invocation naming the plugin-qualified skill, e.g.
  `coordinator-kit:escalation` — record the exact name(s) shown, in the order they appear.
- **Nothing loaded**: no such invocation appears; the reply is a plain, generic answer.
- **Wrong skill loaded**: an invocation appears, but names a skill other than the one this
  document targeted.
- **Two (or more) loaded**: more than one invocation appears in the same turn — record every
  name, and separately note which one's content the reply actually drew on.
- If the transcript UI doesn't surface tool invocations directly, use the reply itself as a
  secondary signal: does it cite the specific mechanics from Section A2's target skill (a named
  gate, a named rule, a named file path from CLAUDE.md/PROCESS.md), or is it a generic answer
  that could have come from general knowledge alone? Treat this as weaker evidence than a
  visible invocation and say so in the notes column.
- Confirm the plugin is actually active before trusting a "nothing loaded" result — see
  Prerequisites.

## A4 — Results

Fill in one row per prompt. Verdict is one of: PASS, MISS, WRONG, SPLIT, OVER-FIRE,
AMBIGUOUS-OK (boundary prompt, either target is an acceptable outcome).

| # | Session/slot | Target | Loaded (actual) | Verdict | Notes |
|---|---|---|---|---|---|
| 1  | S1 solo   | EL-vs-VS |  |  |  |
| 2  | S2 solo   | EL-vs-VS |  |  |  |
| 3  | S3 solo   | ES-vs-CX |  |  |  |
| 4  | S4 solo   | ES-vs-CX |  |  |  |
| 5  | S5 solo   | CR-vs-QP |  |  |  |
| 6  | S6 solo   | CR-vs-QP |  |  |  |
| 7  | S7 solo   | NEG      |  |  |  |
| 8  | S8 cold   | AB       |  |  |  |
| 9  | S8 warm   | PL       |  |  |  |
| 10 | S9 cold   | EL       |  |  |  |
| 11 | S9 warm   | BD       |  |  |  |
| 12 | S10 cold  | VS       |  |  |  |
| 13 | S10 warm  | CH       |  |  |  |
| 14 | S11 cold  | ES       |  |  |  |
| 15 | S11 warm  | SS       |  |  |  |
| 16 | S12 cold  | CX       |  |  |  |
| 17 | S12 warm  | QP       |  |  |  |
| 18 | S13 cold  | WD       |  |  |  |
| 19 | S13 warm  | CR       |  |  |  |
| 20 | S14 cold  | BT       |  |  |  |
| 21 | S14 warm  | NEG      |  |  |  |
| 22 | S15 cold  | NEG      |  |  |  |
| 23 | S15 warm  | NEG      |  |  |  |

Legend: PL=phase-loop, EL=execute-loop, VS=verification-standard, ES=escalation,
CX=codex-second-opinion, WD=watchdogs, SS=stop-and-save, BT=bootstrap,
QP=question-protocol, CR=comms-register, BD=backlog-discipline, CH=credential-handling,
AB=agent-brief-hygiene, NEG=none (negative control).

**What the results mean:**

- **Negative over-fires** (anything but a clean non-fire on S7, S14-warm, or S15): the firing
  skill's description keys on wording too generic for its actual scope — narrow the trigger
  phrase or add an explicit exclusion.
- **Positive misses** (nothing loads on a targeted prompt): the description's phrasing doesn't
  cover this real register — broaden it to the concept, not necessarily these exact words, but
  this style of ask.
- **Boundary prompt resolves one way consistently**: not automatically a problem — check
  whether the winning skill's content actually answers what was asked. If it does, that's a
  legitimate, working precedence. If the reply is thin because the "wrong" half of the pair won
  and doesn't cover the asked-about mechanic, that's a real gap.
- **Boundary prompt loads both**: not automatically a problem either — note it. If it happens
  on every boundary prompt in a pair, the two descriptions overlap too much and should be split
  on clearer keywords.
- **A warm-slot anomaly**: apply Rule 4 (Section A1) before writing it up — re-test that one
  prompt solo, cold. Only a reproduced-cold result goes in the "needs a description fix" pile; a
  warm-only result goes in a separate "sensitive to nearby context" note instead.
- **A prompt judged unfair in hindsight** (didn't reflect how anyone actually asks this, too
  obscure, accidentally leading): rewrite the prompt and retest. Don't change a skill
  description on the strength of a prompt that wasn't a fair test to begin with.

## A5 — Prerequisites

- Confirm the plugin is installed at user scope: `coordinator-kit@coordinator-kit`. Run
  `/help` (Custom commands tab) and confirm the 13 `coordinator-kit:*` skills are listed, or
  ask any question expected to trigger one and watch for the invocation per Section A3.
- If the current session was started **before** the plugin was installed or last updated, run
  `/reload-plugins`, or restart the session — a session only picks up plugin state present at
  its own start.
- Every session in Section A2 must be a genuinely fresh session (new session, not a resumed or
  continued one) — reusing an old session for an S1-S15 slot silently violates Rule 1/2/3
  regardless of what this document says to send.
- If any other plugin is installed alongside `coordinator-kit`, note it before starting — an
  overlapping skill name or topic elsewhere could confound which invocation is actually being
  observed.
