"""Project decomposition: turn descriptions into executable plans.

The ProjectDecomposer is the orchestrator that coordinates the planning
pipeline: research → architecture → milestones → tasks → DAG validation.

It can run in two modes:
1. LLM-powered: Uses planner/researcher agents to generate plans via LLM
2. Template-powered: Uses predefined templates for common project types
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .dag import TaskDAG
from .schema import (
    ArchitectureComponent,
    ComponentType,
    Milestone,
    ProjectPlan,
    RiskLevel,
    SandboxRequirements,
    TaskSpec,
    TechChoice,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common project templates (bootstrap planning without LLM)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "web_app": {
        "architecture": [
            {
                "id": "frontend",
                "type": "frontend",
                "tech": "React/Next.js",
                "description": "Web client application",
            },
            {
                "id": "api",
                "type": "backend",
                "tech": "FastAPI/Node.js",
                "description": "REST API server",
                "dependencies": ["database"],
            },
            {
                "id": "database",
                "type": "database",
                "tech": "PostgreSQL",
                "description": "Primary data store",
            },
        ],
        "milestones": [
            {
                "name": "Foundation",
                "tasks": [
                    "Set up project scaffolding and CI/CD",
                    "Design database schema and create migrations",
                    "Implement authentication flow",
                ],
            },
            {
                "name": "Core Features",
                "tasks": [
                    "Build core API endpoints",
                    "Implement frontend pages and routing",
                    "Wire frontend to API with data fetching",
                ],
            },
            {
                "name": "Polish & Ship",
                "tasks": [
                    "Add error handling and edge cases",
                    "Implement responsive design and accessibility",
                    "Set up monitoring and deploy to production",
                ],
            },
        ],
    },
    "api_service": {
        "architecture": [
            {
                "id": "api",
                "type": "backend",
                "tech": "FastAPI",
                "description": "API service",
            },
            {
                "id": "database",
                "type": "database",
                "tech": "PostgreSQL",
                "description": "Data persistence",
            },
            {
                "id": "cache",
                "type": "cache",
                "tech": "Redis",
                "description": "Response caching and rate limiting",
            },
        ],
        "milestones": [
            {
                "name": "Foundation",
                "tasks": [
                    "Set up project structure and dependencies",
                    "Design database schema",
                    "Implement core data models and migrations",
                ],
            },
            {
                "name": "API Implementation",
                "tasks": [
                    "Build CRUD endpoints",
                    "Add authentication and authorization",
                    "Implement caching layer",
                ],
            },
            {
                "name": "Hardening",
                "tasks": [
                    "Add rate limiting and input validation",
                    "Write integration tests",
                    "Set up CI/CD and deploy",
                ],
            },
        ],
    },
    "cli_tool": {
        "architecture": [
            {
                "id": "cli",
                "type": "frontend",
                "tech": "Python/Typer",
                "description": "Command-line interface",
            },
            {
                "id": "core",
                "type": "backend",
                "tech": "Python",
                "description": "Core business logic",
            },
        ],
        "milestones": [
            {
                "name": "Foundation",
                "tasks": [
                    "Set up project structure with CLI framework",
                    "Implement core business logic",
                ],
            },
            {
                "name": "Features",
                "tasks": [
                    "Build CLI commands and argument parsing",
                    "Add configuration file support",
                    "Implement output formatting",
                ],
            },
            {
                "name": "Ship",
                "tasks": [
                    "Write tests",
                    "Add documentation and help text",
                    "Set up packaging and distribution",
                ],
            },
        ],
    },
}

# Default agent role assignments by task keyword patterns
_ROLE_HINTS: list[tuple[list[str], str, list[str]]] = [
    (
        ["database", "schema", "migration", "sql"],
        "engineering/backend-architect",
        ["database", "schema", "sql"],
    ),
    (
        ["api", "endpoint", "rest", "graphql"],
        "engineering/backend-architect",
        ["backend", "api"],
    ),
    (
        ["frontend", "ui", "component", "page", "react", "css"],
        "engineering/frontend-developer",
        ["frontend", "ui", "css"],
    ),
    (
        ["deploy", "ci", "cd", "docker", "infrastructure", "monitor"],
        "engineering/devops-automator",
        ["deploy", "ci-cd", "infrastructure"],
    ),
    (
        ["test", "testing", "integration test", "e2e"],
        "testing/evidence-collector",
        ["testing", "qa"],
    ),
    (
        ["scaffold", "setup", "project structure", "boilerplate"],
        "engineering/senior-developer",
        ["backend", "architecture"],
    ),
    (
        ["auth", "authentication", "authorization", "security"],
        "engineering/backend-architect",
        ["backend", "security"],
    ),
]


def _guess_agent_role(task_title: str) -> tuple[str, list[str]]:
    """Guess the best agent role for a task based on keyword matching."""
    title_lower = task_title.lower()
    for keywords, role, tags in _ROLE_HINTS:
        if any(kw in title_lower for kw in keywords):
            return role, tags
    return "engineering/senior-developer", ["backend"]


class ProjectDecomposer:
    """Decomposes a project description into a structured ProjectPlan.

    Usage::

        decomposer = ProjectDecomposer()

        # Template-based (no LLM needed)
        plan = decomposer.from_template("web_app", "My SaaS App", "A project management tool")

        # LLM-powered (requires planner agent)
        plan = decomposer.from_description(
            "Build a Slack bot that summarizes daily standups",
            planner_agent=planner,
        )
    """

    def from_template(
        self,
        template_name: str,
        project_name: str,
        project_description: str,
    ) -> ProjectPlan:
        """Generate a plan from a predefined template.

        Available templates: web_app, api_service, cli_tool
        """
        template = _TEMPLATES.get(template_name)
        if template is None:
            available = ", ".join(_TEMPLATES.keys())
            raise ValueError(
                f"Unknown template {template_name!r}. Available: {available}"
            )

        # Build architecture
        architecture = []
        for comp in template["architecture"]:
            architecture.append(
                ArchitectureComponent(
                    id=comp["id"],
                    type=ComponentType(comp["type"]),
                    description=comp["description"],
                    tech=comp.get("tech", ""),
                    dependencies=comp.get("dependencies", []),
                )
            )

        # Build milestones and tasks
        milestones = []
        all_task_ids: list[str] = []
        prev_milestone_task_ids: list[str] = []

        for m_idx, m_template in enumerate(template["milestones"]):
            milestone_id = f"M{m_idx + 1}"
            tasks = []
            current_milestone_task_ids: list[str] = []

            for t_idx, task_desc in enumerate(m_template["tasks"]):
                task_id = f"T{m_idx + 1}.{t_idx + 1}"
                role, tags = _guess_agent_role(task_desc)

                # First task in milestone depends on all tasks in prev milestone
                depends = []
                if t_idx == 0 and prev_milestone_task_ids:
                    depends = list(prev_milestone_task_ids)

                tasks.append(
                    TaskSpec(
                        id=task_id,
                        milestone_id=milestone_id,
                        title=task_desc,
                        description=f"{task_desc} for {project_name}: {project_description}",
                        agent_role=role,
                        domain_tags=tags,
                        depends_on=depends,
                        acceptance_criteria=[f"{task_desc} is complete and verified"],
                        estimated_tokens=10000,
                        sandbox=SandboxRequirements(
                            needs_network="deploy" in task_desc.lower()
                            or "ci" in task_desc.lower(),
                            needs_browser="frontend" in task_desc.lower()
                            or "ui" in task_desc.lower(),
                        ),
                    )
                )
                current_milestone_task_ids.append(task_id)
                all_task_ids.append(task_id)

            milestones.append(
                Milestone(
                    id=milestone_id,
                    name=m_template["name"],
                    acceptance_criteria=[
                        f"All tasks in {m_template['name']} milestone pass verification"
                    ],
                    effort_days=len(tasks) * 0.5,
                    depends_on=[f"M{m_idx}"] if m_idx > 0 else [],
                    tasks=tasks,
                )
            )
            prev_milestone_task_ids = current_milestone_task_ids

        # Build plan
        plan = ProjectPlan(
            name=project_name,
            description=project_description,
            architecture=architecture,
            tech_stack=[
                TechChoice(
                    layer=comp["type"],
                    technology=comp.get("tech", "TBD"),
                    rationale="Template default",
                )
                for comp in template["architecture"]
            ],
            milestones=milestones,
        )

        # Compute execution order and critical path via DAG
        dag = TaskDAG(plan.all_tasks)
        errors = dag.validate()
        if errors:
            logger.warning(f"DAG validation errors: {errors}")
        else:
            plan.execution_order = dag.topological_sort()
            plan.critical_path = dag.critical_path()

        plan.estimated_total_tokens = sum(t.estimated_tokens for t in plan.all_tasks)
        plan.estimated_total_days = sum(m.effort_days for m in milestones)

        return plan

    def from_description(
        self,
        description: str,
        planner_agent: Any = None,
        researcher_agent: Any = None,
    ) -> ProjectPlan:
        """Generate a plan from a natural-language description using LLM agents.

        If planner_agent is provided, it will be used to generate the plan
        via LLM. Otherwise, falls back to best-guess template matching.

        Args:
            description: Natural language project description.
            planner_agent: Optional BusinessAgent with planner spec.
            researcher_agent: Optional BusinessAgent for pre-planning research.
        """
        if planner_agent is None:
            # Fallback: guess the best template
            template = self._guess_template(description)
            name = self._extract_project_name(description)
            logger.info(f"No planner agent; using template '{template}' for: {name}")
            return self.from_template(template, name, description)

        # --- LLM-powered planning ---

        # Step 1: Research (optional)
        research_context = ""
        if researcher_agent is not None:
            research_result = researcher_agent.execute_task(
                f"Research the technical landscape for this project: {description}",
                {"output_format": "yaml"},
            )
            if research_result.get("success"):
                research_context = research_result["response"]
                logger.info("Architecture research completed")

        # Step 2: Generate plan via planner agent
        planning_prompt = self._build_planning_prompt(description, research_context)
        plan_result = planner_agent.execute_task(planning_prompt)

        if not plan_result.get("success"):
            logger.warning(
                f"Planner failed: {plan_result.get('error')}. Falling back to template."
            )
            template = self._guess_template(description)
            name = self._extract_project_name(description)
            return self.from_template(template, name, description)

        # Step 3: Parse LLM output into ProjectPlan
        plan = self._parse_plan_response(plan_result["response"], description)

        # Step 4: Validate DAG
        dag = TaskDAG(plan.all_tasks)
        errors = dag.validate()
        if errors:
            logger.warning(f"Generated plan has DAG errors: {errors}")
        else:
            plan.execution_order = dag.topological_sort()
            plan.critical_path = dag.critical_path()

        plan.estimated_total_tokens = sum(t.estimated_tokens for t in plan.all_tasks)
        plan.estimated_total_days = sum(m.effort_days for m in plan.milestones)

        return plan

    def _build_planning_prompt(self, description: str, research: str) -> str:
        """Build the prompt sent to the planner agent."""
        prompt = (
            "Generate a complete project plan as structured YAML for the following project.\n\n"
            f"PROJECT DESCRIPTION:\n{description}\n\n"
        )
        if research:
            prompt += f"RESEARCH CONTEXT:\n{research}\n\n"

        prompt += (
            "OUTPUT FORMAT: Respond with a YAML document containing:\n"
            "- name: project name\n"
            "- description: one-line summary\n"
            "- architecture: list of {id, type, description, tech, dependencies}\n"
            "- tech_stack: list of {layer, technology, rationale, risk}\n"
            "- milestones: list of {id, name, acceptance_criteria, effort_days, tasks}\n"
            "  - tasks: list of {id, title, description, agent_role, domain_tags, "
            "depends_on, acceptance_criteria, estimated_tokens}\n"
            "\n"
            "RULES:\n"
            "- Every task must be completable by a single agent in one session\n"
            "- Every task must have testable acceptance criteria\n"
            "- Dependencies must form a DAG (no cycles)\n"
            "- Use agent roles from: engineering/senior-developer, "
            "engineering/backend-architect, engineering/frontend-developer, "
            "engineering/devops-automator, testing/evidence-collector\n"
        )
        return prompt

    def _parse_plan_response(self, response: str, description: str) -> ProjectPlan:
        """Parse LLM response into a ProjectPlan. Robust to formatting variations."""
        # Try YAML parsing first, fall back to structured extraction
        try:
            import yaml  # type: ignore[import-untyped]

            # Extract YAML block if wrapped in code fence
            if "```yaml" in response:
                yaml_block = response.split("```yaml")[1].split("```")[0]
            elif "```" in response:
                yaml_block = response.split("```")[1].split("```")[0]
            else:
                yaml_block = response

            data = yaml.safe_load(yaml_block)
            if isinstance(data, dict):
                return self._dict_to_plan(data)
        except Exception:
            logger.debug("YAML parsing failed, falling back to template")

        # Fallback
        template = self._guess_template(description)
        name = self._extract_project_name(description)
        return self.from_template(template, name, description)

    def _dict_to_plan(self, data: dict) -> ProjectPlan:
        """Convert a parsed YAML dict into a ProjectPlan."""
        architecture = []
        for comp in data.get("architecture", []):
            architecture.append(
                ArchitectureComponent(
                    id=comp.get("id", f"comp-{uuid.uuid4().hex[:4]}"),
                    type=ComponentType(comp.get("type", "backend")),
                    description=comp.get("description", ""),
                    tech=comp.get("tech", ""),
                    dependencies=comp.get("dependencies", []),
                )
            )

        tech_stack = []
        for tc in data.get("tech_stack", []):
            tech_stack.append(
                TechChoice(
                    layer=tc.get("layer", ""),
                    technology=tc.get("technology", ""),
                    rationale=tc.get("rationale", ""),
                    risk=RiskLevel(tc.get("risk", "low")),
                )
            )

        milestones = []
        for m in data.get("milestones", []):
            tasks = []
            for t in m.get("tasks", []):
                role = t.get("agent_role", "engineering/senior-developer")
                tags = t.get("domain_tags", [])
                if not tags:
                    _, tags = _guess_agent_role(t.get("title", ""))
                tasks.append(
                    TaskSpec(
                        id=t.get("id", f"T-{uuid.uuid4().hex[:4]}"),
                        milestone_id=m.get("id", ""),
                        title=t.get("title", ""),
                        description=t.get("description", t.get("title", "")),
                        agent_role=role,
                        domain_tags=tags,
                        depends_on=t.get("depends_on", []),
                        acceptance_criteria=t.get("acceptance_criteria", []),
                        estimated_tokens=t.get("estimated_tokens", 10000),
                    )
                )
            milestones.append(
                Milestone(
                    id=m.get("id", f"M-{uuid.uuid4().hex[:4]}"),
                    name=m.get("name", ""),
                    acceptance_criteria=m.get("acceptance_criteria", []),
                    effort_days=m.get("effort_days", len(tasks) * 0.5),
                    tasks=tasks,
                )
            )

        return ProjectPlan(
            name=data.get("name", "Untitled Project"),
            description=data.get("description", ""),
            architecture=architecture,
            data_flows=[],
            tech_stack=tech_stack,
            milestones=milestones,
        )

    @staticmethod
    def _guess_template(description: str) -> str:
        """Guess the best template based on description keywords."""
        d = description.lower()
        if any(kw in d for kw in ["cli", "command line", "terminal", "script"]):
            return "cli_tool"
        if any(kw in d for kw in ["api", "microservice", "endpoint", "webhook"]):
            return "api_service"
        return "web_app"

    @staticmethod
    def _extract_project_name(description: str) -> str:
        """Extract a short project name from a description."""
        # Take first sentence or first 50 chars
        first_sentence = description.split(".")[0].split("\n")[0]
        if len(first_sentence) > 60:
            return first_sentence[:57] + "..."
        return first_sentence
