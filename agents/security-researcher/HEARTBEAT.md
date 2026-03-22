# HEARTBEAT.md -- Security Researcher

> Follow the shared protocol in `agents/HEARTBEAT_BASE.md`, then apply these role-specific additions.

## Security-Specific Work Patterns

- **Code audits**: Read the code first. Map data flows. Check input validation, auth, secrets handling.
- **Dependency review**: Check for known CVEs, outdated packages, supply chain risks.
- **Threat models**: Identify assets, threat actors, attack vectors, and existing controls.
- **Findings**: Always include severity (critical/high/medium/low), affected component, reproduction steps, and remediation guidance.
