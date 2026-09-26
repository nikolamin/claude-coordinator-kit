# Feature Map

Read-only research on this project. NO code changes.

The founder has scoped this audit to: [paste the founder's scope answer here — a named
list of feature-areas, or "everything"]. If that scope doesn't obviously map onto anything
you can find in the repo, STOP and ask which part of the product it refers to — do not
guess at the mapping.

Work out for yourself, from the repo and any docs, landing copy or README in it, what this
product actually does end to end, who it's for, and what the core action is that makes it
valuable. If the product's purpose is not genuinely discoverable, STOP and ask me — do not
invent a product vision and do not proceed on an assumption.

Within the founder's scope, enumerate the concrete FEATURES AND FUNCTIONALITIES: each one a
discrete, testable capability with a real entry point — a URL, a screen, a control that a
person on the other side of the screen could actually reach and operate. Not an internal
module, not an implementation detail, not something only visible in code. If a control
exists in the UI but does nothing reachable end to end yet, say so and mark it as such
rather than listing it as a working feature.

A feature that exists but that no plausible user would ever need is itself a finding —
report it as one; do not just fold it silently into the list.

If the scope excludes real parts of the product, name those excluded areas too, briefly, so
the founder can see what this pass is deliberately not covering. Do not enumerate them at
the same depth, and nothing later in this method should test them.

FOR EACH IN-SCOPE FEATURE WRITE:
- A short, plain name.
- Entry point: the exact URL/route, screen, or control that reaches it.
- One line: what it lets a user actually do, in plain terms.
- Whether it's CORE (the thing the product exists to deliver) or SUPPORTING.
- Any evidence in the repo of who it was built for — a feature flag, an internal-only
  route, a paywall, an admin-only control, copy that addresses one kind of user and not
  another. The next phase needs this as a grounding signal, so surface it even if it seems
  minor.

Finish with a short honest section: which features you are confident you found completely,
and which parts of the given scope you are NOT sure you covered fully (an area gated behind
a login you couldn't reach, code you could see but no live screen for, a route that returned
an error).

Output a FEATURE MAP: a numbered list, in-scope features only, in the form above. The next
two phases consume this directly, so keep the names and entry points exact and stable.
