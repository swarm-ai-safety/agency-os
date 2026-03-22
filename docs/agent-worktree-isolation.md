# Agent Worktree Isolation

## Goal

Keep each agent in a clean, independent git working tree so one agent's edits never pollute another agent's workspace.

## Standard Layout

Use this layout at the repository root:

```text
/workspace-repo
  /.worktrees/
    /ceo
    /coo
    /cpo
    /cmo
    /founding-engineer
    /security-researcher
```

Each worktree has its own branch and its own personal memory folder (`agents/<name>/`).

## Branch Naming

Use one long-lived branch per agent:

- `agent/ceo/workspace`
- `agent/coo/workspace`
- `agent/cpo/workspace`
- `agent/cmo/workspace`
- `agent/founding-engineer/workspace`
- `agent/security-researcher/workspace`

This makes branch ownership explicit and prevents accidental commits on `main`.

## Setup

Create a clean worktree for an agent:

```bash
scripts/agent-worktree.sh create coo
```

Print environment values for shell/session launchers:

```bash
scripts/agent-worktree.sh env coo
```

Example output:

```text
AGENT_ID=coo
AGENT_WORKTREE=/path/to/repo/.worktrees/coo
AGENT_HOME=/path/to/repo/.worktrees/coo/agents/coo
```

## Daily Workflow

1. `cd "$AGENT_WORKTREE"`
2. Start the agent process from that worktree
3. Keep all code changes scoped to that agent branch
4. Rebase branch from `main` before landing changes
5. Land changes via PR or cherry-pick into `main`

## Hygiene Rules

- Never run multiple agents from the same worktree.
- Never use the repository root as an agent runtime workspace.
- Keep agent memory in each worktree's `agents/<name>/` folder.
- Run `scripts/agent-worktree.sh list` weekly to detect stale worktrees.
- Remove abandoned worktrees with `scripts/agent-worktree.sh remove <agent>`.

## Why This Solves the Current Problem

- Eliminates cross-agent file contamination in local uncommitted changes.
- Reduces checkout conflicts caused by shared branch state.
- Makes ownership clear when debugging failures.
- Keeps personal memory and notes physically separated by agent runtime.
