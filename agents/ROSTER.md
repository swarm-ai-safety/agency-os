# Agent Roster

This is the team directory. Use `GET /api/companies/{companyId}/agents` for live data.

| Role | Name | Specialization | When to delegate to them |
|------|------|---------------|--------------------------|
| CEO | @CEO | Strategy, hiring, unblocking, board liaison | Escalate blockers, request new hires, strategic decisions |
| Founding Engineer | @Founding-Engineer | Full-stack development, architecture | Code changes, feature implementation, bug fixes, tests |
| CMO | @CMO | Marketing, content, brand, analytics | Landing page copy, campaigns, SEO, social media, analytics |
| COO | @COO | Infrastructure, DevOps, incidents, process | Deployment, CI/CD, monitoring, operational issues |
| CPO | @CPO | Product strategy, specs, prioritization, roadmap | Feature specs, user research, prioritization decisions |
| Security Researcher | @Security-Researcher | Code audits, threat models, CVE review | Security audits, vulnerability reports, dependency review |

## How to communicate with other agents

### Creating a task for another agent

```
POST /api/companies/{companyId}/issues
Headers: Authorization: Bearer $PAPERCLIP_API_KEY, X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID
{
  "title": "Clear, actionable title",
  "description": "Context and requirements",
  "assigneeAgentId": "<target-agent-id>",
  "parentId": "<your-current-task-id>",
  "goalId": "<goal-id-if-applicable>",
  "priority": "medium"
}
```

This triggers a heartbeat for the target agent.

### Requesting input via comment

If you need input from another agent on an existing issue, @mention them in a comment:

```
POST /api/issues/{issueId}/comments
Headers: Authorization: Bearer $PAPERCLIP_API_KEY, X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID
{
  "body": "@Security-Researcher Can you review this endpoint for auth bypass risks?",
  "mentionedAgentIds": ["<agent-id>"]
}
```

This triggers a heartbeat for the mentioned agent. Use sparingly — each mention costs budget.

### Discovering agents dynamically

```
GET /api/companies/{companyId}/agents
```

Returns all agents with their id, name, role, status, and capabilities. Use this to find the right agent ID before creating tasks or mentioning.

## Delegation guidelines

- **Delegate when the task falls outside your specialization.** A CMO finding a bug should create a task for the Founding Engineer, not fix it themselves.
- **Always set `parentId`** to link subtasks to the parent issue for traceability.
- **Escalate to CEO** when you're blocked, need a hire, or face a cross-team conflict.
- **Don't over-delegate.** If you can do it in < 5 minutes and it's within your domain, just do it.
- **Include enough context** in task descriptions so the assignee can work independently.
