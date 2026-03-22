"""Factory: build BusinessAgent instances from package config + registry."""

from __future__ import annotations

from agency_os.agents.business_agent import BusinessAgent
from agency_os.agents.registry import AgentRegistry
from agency_os.packages.schema import AgentRef, DeploymentConfig
from swarm.agents.llm_config import LLMConfig, LLMProvider

_PROVIDER_MAP = {
    "anthropic": LLMProvider.ANTHROPIC,
    "openai": LLMProvider.OPENAI,
    "ollama": LLMProvider.OLLAMA,
    "openrouter": LLMProvider.OPENROUTER,
    "groq": LLMProvider.GROQ,
    "together": LLMProvider.TOGETHER,
    "deepseek": LLMProvider.DEEPSEEK,
    "google": LLMProvider.GOOGLE,
}


class AgentFactory:
    """
    Creates BusinessAgent instances from package agent refs.

    Uses the registry to resolve agent specs, then builds configured
    BusinessAgent instances with proper LLM config, wallet, and permissions.
    """

    def __init__(self, registry: AgentRegistry, deployment: DeploymentConfig):
        self._registry = registry
        self._deployment = deployment

    def create_agent(
        self, agent_ref: AgentRef, instance_index: int = 0
    ) -> BusinessAgent:
        """
        Create a single BusinessAgent from a package agent reference.

        Args:
            agent_ref: The agent ref from the package YAML.
            instance_index: Index for generating unique IDs when count > 1.

        Returns:
            Configured BusinessAgent.
        """
        spec = self._registry.get_or_raise(agent_ref.ref)

        # Generate unique agent ID
        slug_suffix = agent_ref.ref.replace("/", "-")
        agent_id = (
            f"{slug_suffix}-{instance_index}" if agent_ref.count > 1 else slug_suffix
        )

        llm_config = LLMConfig(
            provider=_PROVIDER_MAP.get(
                self._deployment.llm_provider, LLMProvider.ANTHROPIC
            ),
            model=self._deployment.model,
        )

        return BusinessAgent(
            agent_id=agent_id,
            spec=spec,
            llm_config=llm_config,
            economic=agent_ref.economic,
            permissions=agent_ref.permissions,
            role_override=agent_ref.role_override if agent_ref.role_override else None,
            domain_tags=agent_ref.domain_tags,
        )

    def create_agents(self, agent_refs: list[AgentRef]) -> list[BusinessAgent]:
        """
        Create all agents for a package.

        Handles count > 1 by creating multiple instances.

        Args:
            agent_refs: List of agent refs from the package YAML.

        Returns:
            List of configured BusinessAgents.
        """
        agents: list[BusinessAgent] = []
        for ref in agent_refs:
            for i in range(ref.count):
                agents.append(self.create_agent(ref, instance_index=i))
        return agents
