# Personas

Read-only research on this project. NO code changes.

You are given the FEATURE MAP below, produced by an earlier read-only pass over this repo,
scoped to what the founder asked to test:

[paste the feature map here]

Work out for yourself, from the repo and any docs, landing copy or README in it, who this
product is for and what a returning user would come back for — treat the feature map above
as evidence of what was actually built, not a starting guess. If the product's purpose or
audience is not genuinely discoverable beyond what the feature map shows, STOP and ask me
rather than inventing one.

There is no traffic and no analytics yet, so you cannot observe real users. You are going
to derive personas instead. That is a weaker foundation than real data and you must treat
it as such: every persona has to be grounded in something real about this product and its
market, and you must show your grounding.

GROUND THEM IN:
- What the feature map shows the product actually builds. Features that exist reveal who
  they were built for. A feature nobody would need was already flagged upstream — use it.
- Who the competitors serve, and where this product differs from them.
- The real constraints of the market it launches into: devices, connection quality,
  payment habits, language, average tech comfort, what people already use instead.
- Any real signal already present: waitlist, early users, the founder's own notes, support
  questions, seed data in the database.

DEFINE BETWEEN 3 AND 13 PERSONAS. Decide the number yourself and justify it from two
things: the scope you were given, and the breadth of the feature map above — a narrowly
scoped test of one or two features needs only a few personas; a broad or "everything" scope
needs more, up to 13, to plausibly cover it. Do not pad the count past what the feature map
actually justifies, and do not under-count a broad scope just to keep things simple.

They must differ along axes that actually change behaviour, not just demographics.
Required coverage:
- The ideal user the product was clearly designed for.
- At least one LOW-MOTIVATION or SKEPTICAL persona — curious, not committed, will abandon
  the moment anything is confusing. Most real first visitors are this person, and products
  are almost never designed for them.
- At least one LOW TECH COMFORT persona, on a mid-range phone, possibly on mobile data.
- At least one persona the product does NOT obviously serve but who will plausibly show up
  anyway — adjacent need, wrong expectation, arrived from the wrong context.

NEW COVERAGE REQUIREMENT: taken together, this set of personas must be capable of
plausibly touching every in-scope feature in the map above — for each feature, at least one
persona in your set could plausibly attempt it, even reluctantly or by accident. If you
cannot construct a persona who would plausibly touch a given feature, say so explicitly:
that is itself a finding (the feature has no natural audience within scope), not a gap to
quietly patch over by inventing an implausible persona just to fill a cell later.

THE REVERSE GAP MATTERS TOO: while you ground personas in the feature map, do not let the
feature map become the ceiling of who you can imagine. If your market research surfaces a
real job-to-be-done or a real kind of person this product should plausibly serve but for
which you find NO supporting feature at all, say so explicitly and name it as a finding —
"the market has this need, the feature map has nothing for it" is exactly the kind of gap a
feature-first process can quietly miss, and it matters as much as a persona invented just to
fit an existing feature.

FOR EACH PERSONA WRITE:
- Name, age, occupation, where they live, what device and connection they are on.
- Their actual goal — the real-world outcome they want, not "use the app".
- What triggered them to look for this today.
- What they already use instead, and what would have to be true to switch.
- Their desires and their fears about this kind of product. What makes them distrust it.
- Their tech comfort, in concrete terms: what they will and will not do.
- What would make them leave within 30 seconds.
- What would make them come back a week later.
- Their success criterion, in their own words.
- THE EVIDENCE: what in the product, the market or the code led you to this persona. Mark
  clearly which parts are grounded and which are your assumption. A persona that is
  entirely assumption is allowed, but it must be labelled as such.

Do NOT write scenarios here — a later phase turns these persona briefs into specific
stories matched against the feature map. Your job here is only to define the people, and
to show which in-scope features each one could plausibly touch.

Output the persona briefs in a form I can paste one at a time into a tester agent, plus a
short table: persona name × which in-scope features they could plausibly touch (this feeds
the matrix phase directly).

Finish with a short honest section: which of these personas you are most confident in and
which are the weakest guesses, and what real-world signal would confirm or kill each one.
