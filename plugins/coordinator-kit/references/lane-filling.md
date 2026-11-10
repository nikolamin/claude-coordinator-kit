# Automatic lane filling

This exists because one measured coordinator sat for hours with thirteen idle work lanes. Three things
went wrong together. Dispatched agents were not recorded as lanes with an agent id, so the idle check
saw zero running agents. The idle alarm named idle lanes but did not say what to start or how many
slots were free. And nothing said that an idle wake requires a dispatch.

## 1. Every dispatch is recorded (bundled hook)

`scripts/autolane.py` runs on PostToolUse for `Agent` and on SubagentStop. It acts only in the main
session of a workspace that has `.coordinator/coord.db`.

- **Background launch** (`status: async_launched` plus an agent id in the tool response; content
  blocks and plain text are parsed too): the hook records an active lane with `agent_id`, the
  subagent transcript path, the model and the dispatch time.
  - If an active lane for the same task has no `agent_id` yet (the coordinator claimed it before
    dispatching), the hook attaches the agent id to that lane and keeps its exclusive checkout.
  - Otherwise it creates `lane-agent-<id>` with `shared_checkout: true`. The unique resource of a
    shared-checkout lane is the agent itself, not the checkout, so agents sharing a trunk checkout
    never collide on the one-active-lane-per-checkout rule. Exclusive claims still collide.
  - A brief without a linked task gets an auto task `agent-<id>` (in progress) so the lane has a
    task record.
- **SubagentStop** releases every active lane carrying that agent id, including a lane the
  coordinator claimed by hand, and closes the auto task.
- A synchronous agent has already finished when PostToolUse fires, so it is skipped. Nested
  dispatches inside an agent are skipped too. An agent continued later through a message (rather
  than a new dispatch) is not re-recorded after its first stop; record its lane by hand.
- The hook never blocks a call. A failure is recorded in `.coordinator/autolane-health.json`, shown
  once as a system message, and reported by `coord.py idle`, `sweep --available-slots auto` and the
  combined watch until a later run succeeds. In the measured incident a silent hook failure was what
  hid every agent.
- To turn it off, put `{"autolane": {"mode": "off"}}` in `.coordinator/guards.json`, or set
  `COORDINATOR_KIT_AUTOLANE=off`.

**Brief marker lines** link the agent. Print them with
`coord.py brief-contract --scratch DIR --task ID --lane NAME [--checkout PATH]`:

```
Task: login-fix
Lane: web
Checkout: services/api
```

If there is no `Task:` line, the hook looks for `TASK_ID=<id>` and then for the first backticked id of
an open task. `Lane:` sets the lane's work lane. `Checkout:` must be an existing directory inside the
workspace; the default is the workspace root.

Codex and other hosts without a PostToolUse `Agent` event or SubagentStop do not run this hook. There,
record `agent_id` on the lane when you dispatch, and release the lane when the agent finishes.

## 2. `coord.py idle`: one pick per idle lane, and FREE-SLOTS

| Term | Meaning |
|---|---|
| Work lane | A task's `data.lane`. Tasks without one form the `unassigned` pool. |
| Running agent | An active lane with an `agent_id` whose recorded transcript was written within `quiet_minutes`. A lane without an `agent_id` also counts while it was claimed within `claim_minutes`; after that it is reported as unattached. |
| Idle lane | A work lane with at least one ready task (the same rule as sweep's dispatch candidates), no running agent bound to it, and no recorded blocker. |
| Pick | The lane's first ready task. Ordinary work comes before last-resort work (`last_resort: true`, or an id starting with one of `last_resort_prefixes`, default `weekly-`, for example weekly or test-failure tasks). Then priority: P0 < P1 < … < numeric < none. Then queue order. |
| FREE-SLOTS | `capacity.max_agents` minus running agents, never below 0. It is 0 while host free memory is under `capacity.min_free_memory_pct`. |

Picks fill FREE-SLOTS best first across idle lanes, and the `unassigned` pool fills whatever is left.
Running a second agent in a busy lane stays a coordinator decision: use `sweep --available-slots N`
for that.

```
coord.py idle                      # JSON: dispatch, idle_lanes, busy_lanes, free_slots, memory, health
coord.py idle --lines              # IDLE-LANES lines, printed only when action is required
coord.py idle --check              # exit 2 when a pick should start now or the hook is failing
coord.py idle block web --reason "waits for the API contract decision" [--hours 4]
coord.py idle block '*' --reason "user stop in force"        # all lanes
coord.py idle unblock web
sweep --available-slots auto       # sweep's dispatch candidates come from the idle picks
```

Sample `--lines` output:

```
IDLE-LANES: FREE-SLOTS: 3 (agents 1/4, mem 41% free)
IDLE-LANES: web (2) pick login-fix P0 Login fails after password reset
IDLE-LANES: api (5) pick rate-limit P2 Rate limit per key [prepare first]
```

Each pick also carries an action. `[prepare first]` means the task has no acceptance or queue position
yet. `[check hold scope]` means an active hold may cover it.

The profile's `capacity` block holds the settings (all optional):

```json
"capacity": {"max_agents": 4, "min_free_memory_pct": 15, "quiet_minutes": 30,
             "claim_minutes": 30, "blocker_hours": 4, "last_resort_prefixes": ["weekly-"]}
```

Free memory is read from `memory_pressure` on macOS and from `/proc/meminfo` on Linux. On any other
host there is no memory gate, and the output shows `mem ?`.

The combined watch (`scripts/watch.py`) includes this check unless `.coordinator/watch.json` sets
`"idle": false`. It prints `IDLE_LANES free=N picks=lane:task,...`, `LANE_HOOK_FAILING` or
`LANE_UNATTACHED`. Its lines leave out the memory reading, so an unchanged state is not reported
again before `repeat_after_seconds`.

## 3. The rule: an idle wake obliges a dispatch or a blocker

On an idle wake (watch line, `idle --check` exit 2, or `sweep --available-slots auto --check-idle`
exit 2), do one of these two things for every pick, up to FREE-SLOTS:

1. Dispatch it now: claim the lane, then send a brief with the `Task:` and `Lane:` lines and the
   execution contract. A `prepare` pick gets intake first, then dispatch.
2. Record why it cannot start: `idle block LANE --reason …` with the concrete dependency, user
   decision, access or hold, and fix its records where they are wrong. A blocker that belongs to
   the task rather than the lane goes on the task (`blocked_on`, `needs_user`, a linked question
   or a dependency); that removes it from the picks, and the lane's next task becomes its pick.

Never re-arm the watch or end the turn with neither. FREE-SLOTS 0 is itself the blocker: the watch
stays silent, and the next completion frees a slot. An explicit user stop is recorded as
`idle block '*' --reason` with that stop's source. A pick never grants authority the task lacks,
such as release, production, spending or a user-reserved action.
