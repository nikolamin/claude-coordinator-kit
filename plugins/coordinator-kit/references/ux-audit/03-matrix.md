# Matrix

Read-only research on this project. NO code changes.

You are given:
1. The FEATURE MAP: [paste it here]
2. The PERSONA BRIEFS, all of them: [paste them here]

Turn these into a RUNNABLE MATRIX: personas (rows) × features/stories (columns), where
every assigned cell becomes a self-contained task a tester agent can be handed with nothing
else.

STEP 1 — WRITE STORIES. For each in-scope feature in the map, write one or more STORIES: a
specific task with a specific goal, a definite entry point (the feature map already gives
you this), and a definite success/failure condition — the same bar the original method
holds scenarios to: not "explore the feature," something a tester can actually attempt end
to end and either complete or visibly fail. A feature with several meaningfully different
ways to use it (first-time vs. returning, happy path vs. recovering from a mistake) gets
more than one story.

STEP 2 — ASSIGN PERSONAS TO STORIES. TARGETED IS THE DEFAULT, NOT CARTESIAN. Do not cross
every persona against every story — n personas × m stories is a blind cartesian product,
produces hundreds of runs on a broad scope, and buries the real findings in noise. Instead,
for each story, decide which persona(s) would PLAUSIBLY attempt it, given that persona's
actual goal, trigger, and tech comfort. This is what gives each runnable item its own
intention: the specific reason THIS persona attempts THIS story, in their own words — not a
generic "test this feature." Most stories get 1-3 assigned personas, not all of them.

If even this targeted set produces an uncomfortably large run count on a broad scope (a
wide feature map can still yield hundreds of "plausible" pairings before you've added a
single cross-type run), thin further by the CORE/SUPPORTING tag from the feature map: CORE
features can justify multiple assigned personas per the coverage guarantee below, but a
SUPPORTING feature should default to exactly one assigned persona — its single most
representative plausible attempt — unless you have a specific reason to assign more. Say
explicitly if and how you thinned this way, so the founder can see the trade-off, not just
the resulting count.

STEP 3 — ADD DELIBERATE CROSS-TYPE RUNS. On top of the targeted assignments, deliberately
add a handful of runs where a persona attempts a story they would NOT obviously attempt.
The mismatch itself is a pre-launch audit's reason to exist: a persona bouncing off a
feature that clearly isn't for them, or unexpectedly succeeding at (or wanting) one that was
supposedly not for them, is exactly the kind of finding this method should surface. Mark
these cells CROSS-TYPE, distinct from the targeted assignments in step 2. Do not let this
creep toward full coverage — a handful is enough; judgement decides the count, not a
formula.

COVERAGE GUARANTEES — hold these regardless of how sparse the matrix otherwise is:
- Every in-scope feature is exercised by at least one persona, targeted or cross-type. An
  untouched feature is either a scope mistake (raise it now) or a real persona gap (report
  it — this should already have surfaced in the persona-definition phase's coverage check).
- Every persona runs at least one story. A persona nobody assigns anything to should not
  have been defined in the first place.
- The CORE VALUE ACTION — the feature the product exists to deliver — is run by SEVERAL
  diverse personas, always including at least one skeptical/low-motivation persona and at
  least one low-tech-comfort persona. This is the one place density is deliberately higher
  than everywhere else in the matrix.

THE FULL CARTESIAN PRODUCT IS AN OPTION, NOT THE DEFAULT. If the scope is small enough that
n × m stays modest (roughly, comfortably under 20-30 runs), you may additionally recommend
running every persona against every in-scope story, and state that count explicitly as an
alternative to your targeted-plus-cross-type recommendation. Present both counts and let the
founder choose; do not silently substitute one for the other.

OUTPUT, in this order:
1. The stories list, one or more per feature, each with its entry point and
   success/failure condition.
2. A COMPACT MATRIX TABLE: personas as rows, features/stories as columns, each cell marked
   ASSIGNED, CROSS-TYPE, or blank/dash for not-run.
3. For every ASSIGNED and CROSS-TYPE cell, one numbered, paste-able RUNNABLE ITEM
   containing: the persona's full brief, the story, the entry point, the intention (why
   this persona is attempting this story now, in their own words), and the success/failure
   criterion. These get pasted one at a time into the tester prompt — nothing else should
   need to be added.
4. THE RUN COUNT: total runnable items in your recommended (targeted + cross-type) matrix,
   and, if you offered it, the full-cartesian alternative count. State both plainly — this
   is the number the founder approves next, before any tester agent is dispatched.
5. A short honest caveat, in your own words: this matrix is a record of EXECUTION coverage
   (which cells got run), not a guarantee of RISK coverage (whether the user risk that
   actually matters got addressed). Name, explicitly, what kind of risk a grid of
   single-story, isolated cells structurally does not catch — cross-feature journeys (a
   user moving from one feature into another in one sitting), accumulated state across a
   session (what changes after the third action, not just the first), and recovery,
   cancellation, or concurrency scenarios spanning more than one story. If any of those
   matter for this product, say so and flag them as a real gap this matrix leaves open, not
   something the matrix should be stretched to cover by adding more cells.

If the feature map or persona briefs are missing or incomplete, ask before starting rather
than guessing at either.
