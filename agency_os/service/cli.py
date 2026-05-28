"""CLI for agency-os: `agency-os run`, `list-packages`, etc."""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agency_os.agent_git import (
    AgentDelegation,
    AgentGitAction,
    AgentGitAttestation,
    AgentGitScope,
    AgentGitWorkspace,
    agent_ref,
    evaluate_action,
)
from agency_os.orchestration.organization import Organization
from agency_os.packages.loader import (
    list_builtin_packages,
    load_package,
    validate_package,
)

app = typer.Typer(
    name="agency-os",
    help="Turnkey autonomous AI organization platform.",
    no_args_is_help=True,
)
console = Console()
agent_git_app = typer.Typer(
    name="agent-git",
    help="Delegated identity, policy, and provenance for coding agents.",
    no_args_is_help=True,
)
app.add_typer(agent_git_app)


@app.command()
def run(
    package: str = typer.Argument(help="Path to package YAML or built-in name"),
    task: str | None = typer.Option(
        None, "--task", "-t", help="Submit a task after launch"
    ),
    org_id: str | None = typer.Option(None, "--org-id", help="Custom organization ID"),
) -> None:
    """Launch an organization from a package."""
    # Resolve package: file path or built-in name
    package_path = Path(package)
    if package_path.exists():
        console.print(f"Loading package from: [bold]{package}[/bold]")
        org = Organization.from_file(str(package_path), org_id=org_id)
    else:
        console.print(f"Loading built-in package: [bold]{package}[/bold]")
        org = Organization.from_builtin(package, org_id=org_id)

    org.start()

    console.print(f"\n[green]Organization started:[/green] {org.org_id}")
    _print_org_status(org)

    if task:
        console.print(f"\n[blue]Submitting task:[/blue] {task}")
        result = org.submit_task(task)
        console.print(f"  Assigned to: [bold]{result['assigned_to']}[/bold]")
        console.print(f"  Winning bid: {result['bid_amount']:.2f}")


@app.command(name="list-packages")
def list_packages() -> None:
    """List available built-in packages."""
    packages = list_builtin_packages()
    if not packages:
        console.print("[yellow]No built-in packages found.[/yellow]")
        return

    table = Table(title="Built-in Packages")
    table.add_column("Name", style="bold")
    table.add_column("File")

    for name in packages:
        table.add_row(name, f"agency_os/packages/library/{name}.yaml")

    console.print(table)


@app.command()
def validate(
    package: str = typer.Argument(help="Path to package YAML file"),
) -> None:
    """Validate a package YAML file."""
    errors = validate_package(package)
    if errors:
        console.print("[red]Validation failed:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(code=1)
    else:
        console.print(f"[green]Package is valid:[/green] {package}")


@app.command()
def status(
    package: str = typer.Argument(help="Path to package YAML or built-in name"),
) -> None:
    """Show package info without launching."""
    package_path = Path(package)
    try:
        if package_path.exists():
            spec = load_package(str(package_path))
        else:
            from agency_os.packages.loader import load_package_from_name

            spec = load_package_from_name(package)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    console.print(f"[bold]{spec.metadata.display_name or spec.metadata.name}[/bold]")
    console.print(f"  Tier: {spec.metadata.tier.value}")
    console.print(f"  Agents: {len(spec.agents)}")
    console.print(f"  Governance: {spec.governance.preset}")
    console.print(f"  Model: {spec.deployment.model}")
    console.print(f"  Budget: ${spec.deployment.budget_limit_usd:.2f}")

    if spec.agents:
        console.print("\n  Agents:")
        for a in spec.agents:
            suffix = f" (x{a.count})" if a.count > 1 else ""
            console.print(f"    - {a.ref}{suffix}")

    if spec.workflows:
        console.print("\n  Workflows:")
        for w in spec.workflows:
            console.print(f"    - {w.name} ({w.pipeline})")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, help="Enable auto-reload (dev only)"),
) -> None:
    """Start the API server."""
    import uvicorn

    console.print(f"Starting API server on [bold]{host}:{port}[/bold]")
    uvicorn.run("agency_os.service.api.app:app", host=host, port=port, reload=reload)


@app.command(name="run-task")
def run_task(
    package: str = typer.Option(
        ..., "--package", "-p", help="Built-in package name or path to YAML"
    ),
    task: str = typer.Option(..., "--task", "-t", help="Task description to execute"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show assignment without executing"
    ),
) -> None:
    """Submit and execute a task against an organization."""
    package_path = Path(package)
    if package_path.exists():
        org = Organization.from_file(str(package_path))
    else:
        org = Organization.from_builtin(package)

    org.start()

    if dry_run:
        result = org.submit_task(task, execute=False)
        console.print(
            f"[yellow]Dry run:[/yellow] would assign to [bold]{result['assigned_to']}[/bold]"
        )
        console.print(f"  Winning bid: {result['bid_amount']:.2f}")
    else:
        result = org.submit_task(task, execute=True)
        console.print(
            f"[green]Assigned to:[/green] [bold]{result['assigned_to']}[/bold]"
        )
        console.print(f"  Winning bid: {result['bid_amount']:.2f}")
        exec_result = result.get("result", {})
        if exec_result.get("success"):
            console.print("  Status: [green]success[/green]")
            console.print(
                f"  Tokens: {exec_result.get('tokens_in', 0)} in / {exec_result.get('tokens_out', 0)} out"
            )
            console.print(
                f"\n[bold]Response:[/bold]\n{exec_result.get('response', '')}"
            )
        else:
            console.print("  Status: [red]failed[/red]")
            console.print(f"  Error: {exec_result.get('error', 'unknown')}")


@agent_git_app.command("delegate")
def agent_git_delegate(
    agent_id: str = typer.Option(..., help="Agent principal receiving authority"),
    delegated_by: str = typer.Option(..., help="Human or org granting authority"),
    repo: str = typer.Option(..., help="Repository slug, e.g. owner/name"),
    purpose: str = typer.Option(..., help="Task or reason for this delegation"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write delegation JSON to this path"
    ),
    action: list[AgentGitAction] | None = typer.Option(
        None,
        "--action",
        help="Delegated action; repeat for multiple actions",
    ),
    ttl_minutes: int = typer.Option(240, help="Delegation lifetime in minutes"),
    ref_prefix: list[str] | None = typer.Option(
        None, "--ref-prefix", help="Allowed git ref prefix"
    ),
    protected_path: list[str] | None = typer.Option(
        None, "--protected-path", help="Path prefix the agent may not touch"
    ),
    max_changed_files: int | None = typer.Option(
        None, help="Optional cap on changed files"
    ),
    require_human_approval: bool = typer.Option(
        True, help="Mark resulting work as requiring human approval"
    ),
) -> None:
    """Mint a time-bound delegation document for an agent."""
    issued_at = time.time()
    delegation = AgentDelegation(
        agent_id=agent_id,
        delegated_by=delegated_by,
        purpose=purpose,
        issued_at=issued_at,
        expires_at=issued_at + ttl_minutes * 60,
        scopes=(
            AgentGitScope(
                repo=repo,
                actions=frozenset(
                    action
                    or (
                        AgentGitAction.CREATE_REF,
                        AgentGitAction.COMMIT,
                        AgentGitAction.PUSH,
                    )
                ),
                ref_prefixes=tuple(ref_prefix or ("refs/agents/",)),
                protected_paths=tuple(protected_path or ()),
                max_changed_files=max_changed_files,
                require_human_approval=require_human_approval,
            ),
        ),
    )
    _write_or_print_json(delegation.to_dict(), output)


@agent_git_app.command("check")
def agent_git_check(
    delegation_file: Path = typer.Argument(help="Delegation JSON file"),
    repo: str = typer.Option(..., help="Repository slug to evaluate"),
    action: AgentGitAction = typer.Option(..., help="Requested git action"),
    ref: str = typer.Option(..., help="Target git ref"),
    changed_file: list[str] | None = typer.Option(
        None, "--changed-file", help="Changed file path; repeat for multiple"
    ),
) -> None:
    """Evaluate a requested git action against a delegation."""
    delegation = AgentDelegation.from_dict(json.loads(delegation_file.read_text()))
    decision = evaluate_action(
        delegation,
        repo=repo,
        action=action,
        ref=ref,
        changed_files=changed_file or (),
    )
    _write_or_print_json(decision.to_dict(), None)
    raise typer.Exit(code=0 if decision.allowed else 1)


@agent_git_app.command("attest")
def agent_git_attest(
    delegation_file: Path = typer.Argument(help="Delegation JSON file"),
    repo: str = typer.Option(..., help="Repository slug"),
    task_id: str = typer.Option(..., help="Task id for the agent workspace"),
    action: AgentGitAction = typer.Option(
        AgentGitAction.COMMIT, help="Attested action"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write attestation JSON to this path"
    ),
    check: list[str] | None = typer.Option(
        None, "--check", help="Check command that was run"
    ),
    tool: list[str] | None = typer.Option(
        None, "--tool", help="Tool used by the agent"
    ),
    changed_file: list[str] | None = typer.Option(
        None, "--changed-file", help="Changed file path; repeat for multiple"
    ),
    base_ref: str = typer.Option("refs/heads/main", help="Workspace base ref"),
    trailers: bool = typer.Option(
        False, help="Print git commit trailers instead of JSON"
    ),
) -> None:
    """Create structured provenance for a commit, PR, or audit log."""
    delegation = AgentDelegation.from_dict(json.loads(delegation_file.read_text()))
    workspace = AgentGitWorkspace(
        agent_id=delegation.agent_id,
        task_id=task_id,
        repo=repo,
        ref=agent_ref(delegation.agent_id, task_id),
        base_ref=base_ref,
    )
    attestation = AgentGitAttestation(
        delegation=delegation,
        workspace=workspace,
        action=action,
        checks=tuple(check or ()),
        tools_used=tuple(tool or ()),
        changed_files=tuple(changed_file or ()),
    )
    if trailers:
        console.print("\n".join(attestation.commit_trailers()))
        return
    _write_or_print_json(attestation.to_dict(), output)


def _write_or_print_json(data: dict, output: Path | None) -> None:
    """Write JSON to disk or stdout."""
    rendered = json.dumps(data, indent=2, sort_keys=True)
    if output:
        output.write_text(rendered + "\n")
        console.print(f"[green]Wrote:[/green] {output}")
    else:
        console.print(rendered)


def _print_org_status(org: Organization) -> None:
    """Print org status table."""
    table = Table()
    table.add_column("Agent", style="bold")
    table.add_column("Division")
    table.add_column("Balance", justify="right")
    table.add_column("Bid Strategy")

    for agent in org.agents:
        table.add_row(
            agent.name,
            agent.spec.division,
            f"{agent.balance:.0f}",
            agent.economic.bid_strategy.value,
        )

    console.print(table)


if __name__ == "__main__":
    app()
