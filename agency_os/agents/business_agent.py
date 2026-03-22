"""BusinessAgent — adapter from agency-agents specs to SWARM's LLMAgent."""

from __future__ import annotations

import logging
import threading
from typing import Any

from agency_os.agents.spec_parser import AgentSpec
from agency_os.governance.task_sanitizer import (
    sanitize_task_description,
    wrap_task_for_llm,
)
from agency_os.packages.schema import AgentEconomicConfig, AgentPermissions, BidStrategy
from swarm.agents.base import Role
from swarm.agents.llm_agent import LLMAgent
from swarm.agents.llm_config import LLMConfig, PersonaType

logger = logging.getLogger(__name__)


class BusinessAgent(LLMAgent):
    """
    Extends SWARM's LLMAgent with business-domain capabilities.

    Adds:
    - Agent spec-derived system prompts
    - Wallet/balance tracking
    - Bid strategy for task competition
    - Per-agent tool permissions
    - Role override from package config
    """

    def __init__(
        self,
        agent_id: str,
        spec: AgentSpec,
        llm_config: LLMConfig,
        economic: AgentEconomicConfig | None = None,
        permissions: AgentPermissions | None = None,
        role_override: dict[str, Any] | None = None,
        roles: list[Role] | None = None,
        domain_tags: list[str] | None = None,
    ):
        # Build system prompt from spec
        system_prompt = self._build_system_prompt(spec, role_override)

        # Override the LLM config's system prompt with spec-derived one
        llm_config = LLMConfig(
            provider=llm_config.provider,
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
            timeout=llm_config.timeout,
            max_retries=llm_config.max_retries,
            persona=PersonaType.OPEN,
            system_prompt=system_prompt,
            cost_tracking=llm_config.cost_tracking,
        )

        super().__init__(
            agent_id=agent_id,
            llm_config=llm_config,
            roles=roles,
            name=role_override.get("title", spec.name) if role_override else spec.name,
        )

        self.spec = spec
        self.economic = economic or AgentEconomicConfig()
        self.permissions = permissions or AgentPermissions()
        self.role_override = role_override or {}
        self.domain_tags: list[str] = domain_tags or []

        # Wallet state (guarded by _lock for thread safety)
        self._lock = threading.Lock()
        self._balance: float = self.economic.initial_balance
        self._reputation: float = 1.0
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._consecutive_failures: int = 0
        self._frozen: bool = False

    @staticmethod
    def _build_system_prompt(
        spec: AgentSpec, role_override: dict[str, Any] | None = None
    ) -> str:
        """Build system prompt from agent spec and optional overrides."""
        title = spec.name
        if role_override and "title" in role_override:
            title = role_override["title"]

        prompt = f"You are {title}, a {spec.description}\n\n"
        prompt += f"Division: {spec.division}\n\n"
        prompt += spec.identity
        return prompt

    # -- Wallet operations --

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def reputation(self) -> float:
        return self._reputation

    def credit(self, amount: float) -> None:
        """Add tokens to wallet."""
        if amount < 0:
            raise ValueError(f"Credit amount must be non-negative, got {amount}")
        with self._lock:
            self._balance += amount

    def debit(self, amount: float) -> bool:
        """Remove tokens from wallet. Returns False if insufficient balance."""
        if amount < 0:
            raise ValueError(f"Debit amount must be non-negative, got {amount}")
        with self._lock:
            if amount > self._balance:
                return False
            self._balance -= amount
            return True

    def record_task_outcome(
        self,
        success: bool,
        reputation_delta: float = 0.0,
        freeze_threshold: int = 3,
    ) -> None:
        """Update stats after task completion.

        Consecutive failures are tracked for circuit-breaker purposes.
        When *freeze_threshold* consecutive failures are reached the agent
        is frozen and will refuse further task execution.
        """
        if success:
            self._tasks_completed += 1
            self._consecutive_failures = 0
        else:
            self._tasks_failed += 1
            self._consecutive_failures += 1
            if self._consecutive_failures >= freeze_threshold:
                self._frozen = True
                logger.warning(
                    f"Circuit breaker tripped for {self.agent_id}: "
                    f"{self._consecutive_failures} consecutive failures"
                )
        self._reputation = max(0.0, min(2.0, self._reputation + reputation_delta))

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def unfreeze(self) -> None:
        """Manually reset the circuit breaker."""
        self._frozen = False
        self._consecutive_failures = 0
        logger.info(f"Circuit breaker reset for {self.agent_id}")

    # -- Bidding --

    def compute_bid(self, task_description: str) -> float:
        """Compute a bid amount for a task based on the agent's bid strategy."""
        base_bid = self._balance * 0.1  # Bid 10% of balance by default

        if self.economic.bid_strategy == BidStrategy.QUALITY_WEIGHTED:
            return base_bid * self._reputation
        elif self.economic.bid_strategy == BidStrategy.SPECIALIZATION_BONUS:
            # Higher bid if task matches agent's division
            return base_bid * 1.2
        elif self.economic.bid_strategy == BidStrategy.BUDGET_CONSCIOUS:
            return base_bid * 0.5
        else:
            return base_bid

    # -- Task execution --

    def execute_task(
        self, description: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Execute a task by calling the LLM with the agent's system prompt.

        Pre-execution checks (mechanical, not conversational):
        1. Circuit breaker — frozen agents cannot execute.
        2. Tool permissions — if context specifies a required_tool, it must
           be on the allow list and not on the deny list.

        Args:
            description: The task description / user prompt.
            context: Optional dict of additional context merged into the prompt.

        Returns:
            Dict with keys: response, tokens_in, tokens_out, success, and
            optionally error on failure.
        """
        # -- Pre-execution gates --
        if self._frozen:
            return {
                "response": "",
                "tokens_in": 0,
                "tokens_out": 0,
                "success": False,
                "error": f"Agent {self.agent_id} is frozen (circuit breaker tripped)",
            }

        required_tool = (context or {}).get("required_tool")
        if required_tool and not self.is_tool_allowed(required_tool):
            return {
                "response": "",
                "tokens_in": 0,
                "tokens_out": 0,
                "success": False,
                "error": f"Agent {self.agent_id} denied access to tool: {required_tool}",
            }

        # Sanitize and wrap the task description for safe LLM consumption
        sanitized = sanitize_task_description(description)
        if sanitized.flagged:
            logger.warning(
                "Prompt injection patterns in task for agent %s: %s",
                self.agent_id,
                sanitized.flags,
            )
        user_prompt = f"Task: {wrap_task_for_llm(sanitized.sanitized)}"
        if context:
            user_prompt += "\n\nContext:\n"
            for key, value in context.items():
                user_prompt += f"- {key}: {value}\n"

        try:
            text, tokens_in, tokens_out = self._call_llm_sync(
                self.llm_config.system_prompt,
                user_prompt,
            )
            return {
                "response": text,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "success": True,
            }
        except Exception as e:
            return {
                "response": "",
                "tokens_in": 0,
                "tokens_out": 0,
                "success": False,
                "error": str(e),
            }

    # -- Permissions --

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed for this agent.

        Deny list is checked first (always wins). If an allow list is
        configured, only tools on that list are permitted.  An empty
        allow list means *no* tools are allowed — the previous behavior
        of treating ``[]`` as "allow everything" was a security gap.
        """
        if tool_name in self.permissions.deny:
            return False
        if (
            self.permissions.tools is not None
            and tool_name not in self.permissions.tools
        ):
            return False
        return True

    # -- Status --

    def status_dict(self) -> dict[str, Any]:
        """Return agent status as a dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "spec_slug": self.spec.slug,
            "division": self.spec.division,
            "balance": self._balance,
            "reputation": self._reputation,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "bid_strategy": self.economic.bid_strategy.value,
            "allowed_tools": self.permissions.tools,
            "denied_tools": self.permissions.deny,
            "frozen": self._frozen,
            "consecutive_failures": self._consecutive_failures,
        }

    def __repr__(self) -> str:
        return (
            f"BusinessAgent(id={self.agent_id}, name={self.name!r}, "
            f"slug={self.spec.slug!r}, balance={self._balance:.0f}, "
            f"reputation={self._reputation:.2f})"
        )
