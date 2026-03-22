#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/agent-worktree.sh create <agent> [branch]
  scripts/agent-worktree.sh remove <agent>
  scripts/agent-worktree.sh list
  scripts/agent-worktree.sh env <agent>

Behavior:
- Creates isolated worktrees under .worktrees/<agent>
- Creates per-agent branches named agent/<agent>/workspace by default
- Prints AGENT_HOME and worktree path for shell integration
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

command="$1"
shift || true

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "error: not inside a git repository" >&2
  exit 1
fi

worktree_root="$repo_root/.worktrees"

case "$command" in
  create)
    if [[ $# -lt 1 ]]; then
      usage
      exit 1
    fi
    agent="$1"
    branch="${2:-agent/$agent/workspace}"
    path="$worktree_root/$agent"

    mkdir -p "$worktree_root"

    if [[ -d "$path/.git" || -f "$path/.git" ]]; then
      echo "worktree already exists: $path"
      exit 0
    fi

    if git show-ref --verify --quiet "refs/heads/$branch"; then
      git worktree add "$path" "$branch"
    else
      git worktree add -b "$branch" "$path" HEAD
    fi

    echo "created worktree"
    echo "agent=$agent"
    echo "branch=$branch"
    echo "path=$path"
    ;;

  remove)
    if [[ $# -lt 1 ]]; then
      usage
      exit 1
    fi
    agent="$1"
    path="$worktree_root/$agent"

    if [[ ! -e "$path" ]]; then
      echo "worktree not found: $path"
      exit 0
    fi

    git worktree remove --force "$path"
    git worktree prune
    echo "removed worktree: $path"
    ;;

  list)
    git worktree list --porcelain
    ;;

  env)
    if [[ $# -lt 1 ]]; then
      usage
      exit 1
    fi
    agent="$1"
    path="$worktree_root/$agent"
    agent_home="$path/agents/$agent"

    cat <<ENV
AGENT_ID=$agent
AGENT_WORKTREE=$path
AGENT_HOME=$agent_home
ENV
    ;;

  *)
    usage
    exit 1
    ;;
esac
