# Repository instructions

## Start here

- Read [mdfiles/README.md](mdfiles/README.md), then the assigned task in
  [mdfiles/development-plan.md](mdfiles/development-plan.md).
- For the current resume point, read [mdfiles/next-agent.md](mdfiles/next-agent.md).
- Read the task's context links and inspect the affected implementation. The
  repository map is a navigation aid, not a substitute for reading changed code.
- T01a is merged: local API/auth/UI startup and offline tests exist. AI chat, RAG,
  LLM, and inference features were removed; do not restore them. The remaining
  platform architecture in `mdfiles` is a target, not an implemented feature list.
- Keep this file, `mdfiles/`, and `uv.lock` versioned. Personal scratch notes and
  credentials belong outside shared agent context.
- Develop each bounded block on its own branch from updated `main`, open a draft
  PR against `main`, and leave merging to the user unless explicitly authorized.
- Implement one assigned task at a time. Do not begin the entire roadmap from a
  request to implement one task. Do not delegate unless the user requests it.

## Personal preferences

- Linux / WSL2. Use `uv` for Python commands and dependency management; never pip
  or system Python. Ask before installing anything global.
- Local PostgreSQL and Redis are provided by `~/code/devstack`. Prefer an isolated
  database there; do not change shared devstack configuration or other databases.
- Explain the plan before multi-file changes. Prefer the standard library over
  new dependencies. Use Ruff for formatting/linting and type public functions.
- Never commit secrets. Keep `.env` out of Git; do not print its contents.

## Implementation contracts

- Preserve existing data and migration history. New platform models are separate
  from the dormant `Pipeline` and migration-only historical `BackgroundJob` models.
- Keep SQLAlchemy synchronous initially. Application services own transactions;
  helpers flush as needed, without independently committing workflow fragments.
- Queue external work durably in PostgreSQL. No deployment through FastAPI
  `BackgroundTasks`, and no credentials in operation payloads or API responses.
- Authorization is checked in the API and again before sensitive worker actions.
  Simulation must be explicitly configured and visibly labelled; never silently
  fall back to it after a real integration fails.
- Test the slice's behavior, failure cases, authorization, and migrations where
  applicable. Never weaken assertions or authorization to make checks pass.
- Do not run paid workloads, publish repositories, change external permissions,
  or deploy infrastructure without task-specific user authorization. Prepare
  reviewable code/configuration first. Local reversible work is already in scope.
- Identity/infrastructure changes require human review before merge or external
  activation; this does not prevent implementing and locally testing them.

## Handoff

Before opening or updating an implementation PR, update
[mdfiles/next-agent.md](mdfiles/next-agent.md) in the same PR. Record implemented
behavior, checks actually run, remaining limitations, and the next bounded task.
Replace stale instructions; do not append an endless session log. Keep the handoff
self-contained and never claim an unmerged PR is merged or an unrun check passed.
Use the sections: Implemented state, Verification performed, Remaining work and
limitations, Next task, Files to read first, and Suggested agent prompt.

Avoid temporary checkout/branch-state assumptions. Tell the next agent to inspect
Git status, verify prerequisites on updated main, and create its task branch if
needed. A reviewer must check handoff accuracy; CI checks presence and structure,
not whether its claims are true. Documentation-only PRs need no handoff change
unless they change the next agent's instructions.

Update task status, test evidence, and next steps in
[mdfiles/development-plan.md](mdfiles/development-plan.md). Update affected
contracts and [mdfiles/repository-map.md](mdfiles/repository-map.md) when behavior
or paths change. Record architectural changes in
[mdfiles/decisions.md](mdfiles/decisions.md). Report unrun checks explicitly.
