# Synthesis

Produce the final deliverable for the product owner: a self-contained HTML file with
BEFORE -> AFTER visual mockups and descriptions, built from the feature map, the persona
briefs, the runnable matrix, and every test report I am giving you. If any of these four are
missing, ask me for them before starting.

Work out the product's real design tokens, colours, spacing and real interface copy by
reading them from the repo, so the mockups look like THIS product and not a template. If
you cannot locate the styles, ask me where they live.

FIRST, ANALYSE ACROSS BOTH AXES — this is the point of running a matrix, not just a list of
personas:

PER FEATURE: roll up every report that touched each in-scope feature. Which features failed
across MULTIPLE personas, including ones assigned to it because it plausibly suited them?
Treat that as strong, corroborating evidence — fix it first — but say plainly that it is
corroboration, not independent statistical proof: these personas were derived from the same
product and market evidence, possibly by the same model, so agreement across them means "the
same reasoning kept finding the same problem," not "N unrelated humans hit this
independently."

PER PERSONA: roll up every story each persona ran. Which personas failed across MULTIPLE
features? A persona who abandons everywhere is either a genuine gap in the product's target
market (a real, if uncomfortable, finding) or evidence the persona itself was drawn too
harshly — say which you think it is, and why.

PER CELL: each individual abandonment is still its own ranked finding in its own right — do
not let the roll-ups above bury one sharp, individual failure.

CROSS-TYPE CELLS get their own explicit read: did the mismatched persona bounce off the
feature as expected (confirms it's correctly outside their world — low priority), or did
they get further, succeed, or express real interest (a real positioning or audience
signal worth flagging prominently — but call it a hypothesis this single run raised, not a
confirmed surprise; it's exactly what cross-type runs exist to catch, and exactly the kind
of thing that needs a real signal, per the instrumentation section, to actually confirm)?

Then, unchanged from the original method:
- Where did two personas want OPPOSITE things? Do not average them into mush — name the
  conflict, take a position, and say who you are choosing to serve and what it costs.
- Where did a persona abandon? Each abandonment point is a ranked finding in its own right.
- Did any persona misunderstand what the product IS? That is a positioning problem, not a
  UI problem, and must be reported separately and first.

THEN BUILD THE DOCUMENT:
- For each significant change, a BEFORE -> AFTER mockup drawn in HTML and CSS.
- Alongside each: what is wrong now, what changes, why it matters, and WHICH FEATURE, WHICH
  PERSONA, and which runnable item and moment in their session is the evidence. Quote them.
- Order strictly by impact on a first-time visitor understanding and completing the core
  action. On a product with no users, comprehension and activation outrank everything.
- Tag every item "already being fixed" only when a canonical task and current evidence
  confirm it; otherwise use "new proposal, needs a decision". Link the supporting task when present.
- Since there is no traffic, there are no real measurements. Say so explicitly in the
  document. Every number in a mockup is illustrative and must be labelled as such. Do not
  manufacture percentages. Rank by reasoning and state the reasoning.
- Include a "what works — do not break it" section.
- Include a short "what this audit did and did not cover" section, near the top: state
  plainly that the matrix records EXECUTION coverage, not a guarantee of RISK coverage, and
  carry forward whatever gaps the matrix-building phase flagged (cross-feature journeys,
  accumulated session state, recovery/cancellation/concurrency) so the founder sees the
  boundary of what was actually tested, not just what was found within it.
- Include a final section: WHAT TO INSTRUMENT BEFORE LAUNCH. List the specific events and
  funnel steps to track so that the next audit can be run on real data instead of personas,
  and name which of the assumptions in this document — including any cross-type "audience
  surprise" hypotheses — each one would confirm or kill.
- Produce a reviewable draft first. The coordinator arranges a design opinion from a
  second model on the key screens, then supplies that opinion for finalization. Incorporate
  it and document disagreements and reasons. If it is unavailable, label the review as
  pending unless the owner explicitly accepts an exception; never invent a second opinion.
- Write it in the product's own language, and keep it skimmable on a phone.
- Self-contained: all CSS inline, no external fonts, images or CDN requests. Theme aware
  for light and dark. No horizontal page scrolling on mobile; wide content scrolls inside
  its own container.

Include an execution ledger keyed to every approved runnable item: each attempt's outcome,
report and evidence paths, the current outcome, and any unexecuted or blocked cells. Keep
earlier attempts visible when a blocked run is retried. Preserve exact abandonment details;
never count a tooling block as a user abandoning. Mark before views reconstructed from
evidence separately from actual screenshots, and label all after views as proposals.

Flag whether the same failure mechanism appears in other in-scope surfaces, with evidence.
Do not expand the approved matrix or imply untested siblings were exercised. Recommend a
post-launch follow-up using observed behaviour and real analytics. Write only audit artifacts,
not product fixes, and do not install instrumentation as part of this audit.
