"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

type DashboardTab =
  | "usage"
  | "timeline"
  | "run_health"
  | "effectiveness"
  | "reputation"
  | "agents"
  | "tasks"
  | "governance"
  | "settings";

interface Stats {
  total_requests: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_customer_cost: number;
  avg_latency_ms: number;
  cache_hits: number;
}

interface Savings {
  total_requests: number;
  cache_hits: number;
  cache_savings_usd: number;
  smart_routed: number;
  total_cost_usd: number;
}

interface GatewayRequest {
  request_id: string;
  model_id: string;
  tokens_in: number;
  tokens_out: number;
  customer_cost: number;
  cached: boolean;
  routed_by: string;
  timestamp: number;
}

interface TopModel {
  model_id: string;
  request_count: number;
}

interface TenantInfo {
  tenant_id: string;
  name: string;
  tier: string;
  budget_limit_usd: number;
  total_spent_usd: number;
  billing_status?: string;
  stripe_customer_id?: string;
}

interface CreditBalanceSummary {
  object?: string;
  balances?: Array<{
    available_balance?: {
      monetary?: {
        currency?: string;
        value?: number;
      };
    };
  }>;
}

interface CreditTopUpConfig {
  enabled: boolean;
  price_id?: string | null;
  amount_value?: number | null;
  currency?: string | null;
  name?: string | null;
}

interface Organization {
  org_id: string;
  name: string;
  status: string;
  agent_count: number;
  created_at: string;
}

interface Agent {
  agent_id: string;
  name: string;
  division?: string;
  balance: number;
  reputation: number;
  tasks_completed?: number;
  tasks_failed?: number;
  trust_score?: number;
  trust_tier?: string;
}

interface TaskItem {
  task_id: string;
  description: string;
  assigned_to?: string;
  status: string;
  governance_preset?: string;
  result?: unknown;
  created_at?: string;
}

interface Governance {
  preset: "conservative" | "balanced" | "aggressive";
  overrides?: {
    audit_frequency?: number;
    tax_rate?: number;
    circuit_breaker?: {
      enabled?: boolean;
      threshold?: number;
    };
  };
  policy_version?: number;
  previous_policy_version?: number;
  rollout?: {
    status?: string;
    strategy?: string;
    canary_percent?: number;
  };
}

interface AuditTimelineEntry {
  timestamp?: number;
  actor?: string;
  action?: string;
  resource?: string;
  resource_id?: string;
  summary?: string;
}

interface CircuitBreakerHistoryEntry {
  timestamp?: number;
  event_type?: string;
  agent_id?: string;
  task_id?: string;
  threshold?: number;
  consecutive_failures?: number;
  reason?: string;
  duration_sec?: number;
}

interface GovernanceHistory {
  audit_timeline: AuditTimelineEntry[];
  circuit_breaker_history: CircuitBreakerHistoryEntry[];
  stats?: {
    audit_events?: number;
    circuit_breaker_trips?: number;
  };
}

interface TimelineEventItem {
  org_id?: string;
  event_type?: string;
  title?: string;
  detail?: string;
  agent_id?: string;
  agent_name?: string;
  agent_division?: string;
  agent_color?: string;
  artifact_type?: string;
  artifact_ref?: string;
  timestamp?: number;
  relative_time?: number;
  replay_time?: number;
}

interface TimelineReplay {
  org_id?: string;
  events: TimelineEventItem[];
  agents?: Array<{
    agent_id?: string;
    name?: string;
    division?: string;
    color?: string;
  }>;
  duration_seconds?: number;
  replay_duration_seconds?: number;
  speed?: number;
  start_timestamp?: number;
  end_timestamp?: number;
}

interface AgentTrustSnapshot {
  score: number;
  tier: string;
  total_tasks: number;
  successes: number;
  failures: number;
  partials: number;
}

interface AgentSuccessRate {
  total_tasks: number;
  successes: number;
  rate: number;
}

interface AgentEffectiveness {
  agent_id: string;
  current_trust: AgentTrustSnapshot | null;
  duration_percentiles: Record<string, number>;
  success_rate: AgentSuccessRate;
  effectiveness_trend: string;
}

const DASHBOARD_ORG_ID_STORAGE_KEY = "zhl_dashboard_org_id";
const WARNING_SUPPRESSION_STORAGE_KEY = "zhl_dashboard_warning_suppression";
const WARNING_THRESHOLDS = [50, 80, 90];
const DEFAULT_ONBOARDING_PACKAGE = "saas_dev_studio";

type WarningSeverity = "warning" | "danger";

interface QuotaWarning {
  id: string;
  metric: "budget" | "tokens";
  threshold: number;
  severity: WarningSeverity;
  title: string;
  detail: string;
}

type AuthErrorDetails = {
  message: string;
  canRetrySignIn: boolean;
};

const AUTH_ERROR_DETAILS: Record<string, AuthErrorDetails> = {
  oidc_unavailable: {
    message:
      "Single sign-on is not enabled for this deployment. Ask your operator to configure OIDC and try again.",
    canRetrySignIn: false,
  },
  misconfigured: {
    message:
      "Single sign-on is partially configured. Ask your operator to finish dashboard OIDC setup and try again.",
    canRetrySignIn: false,
  },
  oidc_init_failed: {
    message:
      "Unable to start single sign-on right now. Please try again in a moment or contact your operator.",
    canRetrySignIn: true,
  },
  oidc_failed: {
    message:
      "Single sign-on could not be completed. Please try again, and contact your operator if it keeps failing.",
    canRetrySignIn: true,
  },
  state_mismatch: {
    message:
      "Your sign-in session expired while authenticating. Please start sign-in again.",
    canRetrySignIn: true,
  },
};

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asText(value: unknown, fallback = "n/a"): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

function trackDashboardEvent(
  eventName: string,
  props?: Record<string, string | number | boolean>
): void {
  if (typeof window === "undefined") {
    return;
  }
  const maybeWindow = window as Window & {
    plausible?: (name: string, options?: { props?: Record<string, unknown> }) => void;
  };
  if (typeof maybeWindow.plausible !== "function") {
    return;
  }
  maybeWindow.plausible(eventName, props ? { props } : undefined);
}

export default function DashboardClient() {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<DashboardTab>("usage");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);

  const [stats, setStats] = useState<Stats | null>(null);
  const [savings, setSavings] = useState<Savings | null>(null);
  const [requests, setRequests] = useState<GatewayRequest[]>([]);
  const [topModels, setTopModels] = useState<TopModel[]>([]);
  const [tenantInfo, setTenantInfo] = useState<TenantInfo | null>(null);
  const [creditSummary, setCreditSummary] = useState<CreditBalanceSummary | null>(null);
  const [creditTopUpConfig, setCreditTopUpConfig] = useState<CreditTopUpConfig | null>(
    null
  );

  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const [orgPackageName, setOrgPackageName] = useState(DEFAULT_ONBOARDING_PACKAGE);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [orgLoading, setOrgLoading] = useState(false);
  const [orgError, setOrgError] = useState("");

  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [governance, setGovernance] = useState<Governance | null>(null);
  const [governanceHistory, setGovernanceHistory] = useState<GovernanceHistory | null>(
    null
  );
  const [effectivenessByAgent, setEffectivenessByAgent] = useState<
    Record<string, AgentEffectiveness>
  >({});
  const [effectivenessLoading, setEffectivenessLoading] = useState(false);
  const [effectivenessError, setEffectivenessError] = useState("");
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventItem[]>([]);
  const [timelineReplay, setTimelineReplay] = useState<TimelineReplay | null>(null);

  const [taskDescription, setTaskDescription] = useState("");
  const [submittingTask, setSubmittingTask] = useState(false);

  const [govPreset, setGovPreset] = useState<Governance["preset"]>("balanced");
  const [govAuditFrequency, setGovAuditFrequency] = useState(0.1);
  const [govTaxRate, setGovTaxRate] = useState(0.05);
  const [govCircuitBreakerEnabled, setGovCircuitBreakerEnabled] = useState(true);
  const [govCircuitBreakerThreshold, setGovCircuitBreakerThreshold] = useState(3);
  const [govUpdating, setGovUpdating] = useState(false);
  const [billingLoading, setBillingLoading] = useState(false);
  const [suppressedWarnings, setSuppressedWarnings] = useState<string[]>([]);

  // Settings / key rotation state
  const [showRotateConfirm, setShowRotateConfirm] = useState(false);
  const [rotatingKey, setRotatingKey] = useState(false);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [rotateError, setRotateError] = useState("");
  const [keyCopied, setKeyCopied] = useState(false);

  const selectedOrg = useMemo(
    () => organizations.find((org) => org.org_id === selectedOrgId) ?? null,
    [organizations, selectedOrgId]
  );
  const authErrorCode = searchParams.get("auth_error");
  const authError = authErrorCode ? AUTH_ERROR_DETAILS[authErrorCode] : undefined;
  const authCanRetrySignIn = authError?.canRetrySignIn ?? true;

  const asNumber = (value: unknown, fallback = 0): number => {
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  const formatCost = (cost: unknown) => `$${asNumber(cost).toFixed(4)}`;
  const formatNumber = (n: unknown) => asNumber(n).toLocaleString();

  const firstCallDone = (stats?.total_requests ?? 0) > 0;
  const billingConfigured = Boolean(tenantInfo?.stripe_customer_id);
  const billingStatus =
    typeof tenantInfo?.billing_status === "string" ? tenantInfo.billing_status : "not_started";
  const billingActive = billingStatus === "active";
  const hasOrganization = organizations.length > 0;
  const firstTaskDone = tasks.length > 0;
  const onboardingComplete = hasOrganization && firstTaskDone && billingConfigured;
  const availableCreditValue =
    creditSummary?.balances?.reduce((sum, balance) => {
      const cents = Number(balance.available_balance?.monetary?.value ?? 0);
      return sum + (Number.isFinite(cents) ? cents : 0);
    }, 0) ?? 0;
  const formattedAvailableCredits = formatCost(availableCreditValue / 100);
  const onboardingCompletedRef = useRef({
    hasOrganization: false,
    firstTaskDone: false,
    billingConfigured: false,
  });
  const onboardingViewedRef = useRef(false);
  const orgEmptyStateViewedRef = useRef(false);
  const activeWarnings = useMemo(() => {
    if (!tenantInfo || !stats) {
      return [] as QuotaWarning[];
    }

    const period = new Date().toISOString().slice(0, 7);
    const tenantId = tenantInfo.tenant_id;
    const warnings: QuotaWarning[] = [];

    const budgetLimit = Math.max(Number(tenantInfo.budget_limit_usd) || 0, 0);
    const budgetUsed = Math.max(Number(tenantInfo.total_spent_usd) || 0, 0);
    const budgetPercent = budgetLimit > 0 ? (budgetUsed / budgetLimit) * 100 : 0;
    const budgetThreshold = [...WARNING_THRESHOLDS]
      .reverse()
      .find((threshold) => budgetPercent >= threshold);

    if (budgetThreshold !== undefined && budgetPercent < 100) {
      const remaining = Math.max(budgetLimit - budgetUsed, 0);
      warnings.push({
        id: `${tenantId}:${period}:budget:${budgetThreshold}`,
        metric: "budget",
        threshold: budgetThreshold,
        severity: budgetThreshold >= 90 ? "danger" : "warning",
        title: `Budget usage reached ${budgetThreshold}%`,
        detail: `${formatCost(remaining)} remaining before enforcement limits. Review usage or upgrade plan.`,
      });
    }

    return warnings.filter((warning) => !suppressedWarnings.includes(warning.id));
  }, [stats, suppressedWarnings, tenantInfo]);
  const runHealth = useMemo(() => {
    const terminalTasks = tasks.filter((task) => {
      const status = (task.status || "").toLowerCase();
      return status === "completed" || status === "failed";
    });
    const failedTasks = terminalTasks.filter(
      (task) => (task.status || "").toLowerCase() === "failed"
    );
    const totalRuns = terminalTasks.length;
    const failedRuns = failedTasks.length;
    const failureRate = totalRuns > 0 ? (failedRuns / totalRuns) * 100 : 0;

    const extractReason = (task: TaskItem): string => {
      const result = task.result;
      if (result && typeof result === "object" && !Array.isArray(result)) {
        const error = (result as { error?: unknown }).error;
        if (typeof error === "string" && error.trim()) {
          return error.trim();
        }
      }
      if (typeof result === "string" && result.trim()) {
        return result.trim();
      }
      return "Unknown failure";
    };

    const reasonCounts = new Map<string, number>();
    failedTasks.forEach((task) => {
      const reason = extractReason(task).split("\n")[0].slice(0, 100);
      reasonCounts.set(reason, (reasonCounts.get(reason) || 0) + 1);
    });

    const topReasons = Array.from(reasonCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([reason, count]) => ({
        reason,
        count,
        percent: failedRuns > 0 ? (count / failedRuns) * 100 : 0,
      }));

    const today = new Date();
    const dailyBuckets = new Map<string, { runs: number; failures: number }>();
    for (let offset = 6; offset >= 0; offset -= 1) {
      const date = new Date(today);
      date.setDate(today.getDate() - offset);
      dailyBuckets.set(date.toISOString().slice(0, 10), { runs: 0, failures: 0 });
    }

    terminalTasks.forEach((task) => {
      if (!task.created_at) {
        return;
      }
      const taskDate = new Date(task.created_at);
      if (Number.isNaN(taskDate.getTime())) {
        return;
      }
      const key = taskDate.toISOString().slice(0, 10);
      const bucket = dailyBuckets.get(key);
      if (!bucket) {
        return;
      }
      bucket.runs += 1;
      if ((task.status || "").toLowerCase() === "failed") {
        bucket.failures += 1;
      }
    });

    const dailyTrend = Array.from(dailyBuckets.entries()).map(([isoDate, bucket]) => {
      const date = new Date(`${isoDate}T00:00:00`);
      return {
        label: date.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        runs: bucket.runs,
        failures: bucket.failures,
        failureRate: bucket.runs > 0 ? (bucket.failures / bucket.runs) * 100 : 0,
      };
    });

    const weekStartKey = (date: Date): string => {
      const d = new Date(date);
      d.setHours(0, 0, 0, 0);
      const day = d.getDay();
      const offsetToMonday = (day + 6) % 7;
      d.setDate(d.getDate() - offsetToMonday);
      return d.toISOString().slice(0, 10);
    };

    const weeklyBuckets = new Map<string, { runs: number; failures: number }>();
    for (let offset = 5; offset >= 0; offset -= 1) {
      const date = new Date(today);
      date.setDate(today.getDate() - offset * 7);
      weeklyBuckets.set(weekStartKey(date), { runs: 0, failures: 0 });
    }

    terminalTasks.forEach((task) => {
      if (!task.created_at) {
        return;
      }
      const taskDate = new Date(task.created_at);
      if (Number.isNaN(taskDate.getTime())) {
        return;
      }
      const key = weekStartKey(taskDate);
      const bucket = weeklyBuckets.get(key);
      if (!bucket) {
        return;
      }
      bucket.runs += 1;
      if ((task.status || "").toLowerCase() === "failed") {
        bucket.failures += 1;
      }
    });

    const weeklyTrend = Array.from(weeklyBuckets.entries()).map(([weekStartIso, bucket]) => {
      const weekStart = new Date(`${weekStartIso}T00:00:00`);
      return {
        label: `Week of ${weekStart.toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        })}`,
        runs: bucket.runs,
        failures: bucket.failures,
        failureRate: bucket.runs > 0 ? (bucket.failures / bucket.runs) * 100 : 0,
      };
    });

    return {
      totalRuns,
      failedRuns,
      failureRate,
      successRate: totalRuns > 0 ? 100 - failureRate : 0,
      topReasons,
      dailyTrend,
      weeklyTrend,
      recentFailures: failedTasks
        .slice()
        .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
        .slice(0, 5)
        .map((task) => ({
          taskId: task.task_id,
          createdAt: task.created_at,
          reason: extractReason(task),
        })),
    };
  }, [tasks]);

  const reputationAnalytics = useMemo(() => {
    if (agents.length === 0) {
      return {
        average: 0,
        median: 0,
        highest: null as Agent | null,
        lowest: null as Agent | null,
        trustTierCounts: {} as Record<string, number>,
        atRisk: [] as Agent[],
      };
    }

    const byReputation = agents
      .slice()
      .sort((a, b) => (b.reputation ?? 0) - (a.reputation ?? 0));
    const values = byReputation.map((agent) => agent.reputation ?? 0);
    const middle = Math.floor(values.length / 2);
    const median =
      values.length % 2 === 0
        ? (values[middle - 1] + values[middle]) / 2
        : values[middle];

    const trustTierCounts = agents.reduce<Record<string, number>>((counts, agent) => {
      const tier = (agent.trust_tier || "unknown").toLowerCase();
      counts[tier] = (counts[tier] || 0) + 1;
      return counts;
    }, {});

    const atRisk = byReputation
      .slice()
      .reverse()
      .filter((agent) => {
        const tier = (agent.trust_tier || "").toLowerCase();
        return (agent.reputation ?? 0) < 0 || tier === "low";
      })
      .slice(0, 5);

    return {
      average:
        agents.reduce((sum, agent) => sum + (agent.reputation ?? 0), 0) / agents.length,
      median,
      highest: byReputation[0] ?? null,
      lowest: byReputation[byReputation.length - 1] ?? null,
      trustTierCounts,
      atRisk,
    };
  }, [agents]);

  const effectivenessAnalytics = useMemo(() => {
    const rows = agents.map((agent) => {
      const effectiveness = effectivenessByAgent[agent.agent_id];
      const successRate = (effectiveness?.success_rate?.rate ?? 0) * 100;
      const totalTasks =
        effectiveness?.success_rate?.total_tasks ??
        (agent.tasks_completed ?? 0) + (agent.tasks_failed ?? 0);
      const trustScore = effectiveness?.current_trust?.score ?? agent.trust_score ?? 0;
      const p50Duration = Number(effectiveness?.duration_percentiles?.p50 ?? 0);
      const trend = (effectiveness?.effectiveness_trend || "stable").toLowerCase();

      return {
        agent,
        successRate,
        totalTasks,
        trustScore,
        p50Duration,
        trend,
        hasEffectiveness: Boolean(effectiveness),
      };
    });

    const modeled = rows.filter((row) => row.hasEffectiveness);
    const modeledTasks = modeled.reduce((sum, row) => sum + row.totalTasks, 0);
    const modeledSuccesses = modeled.reduce(
      (sum, row) => sum + (row.successRate / 100) * row.totalTasks,
      0
    );

    const trendCounts = modeled.reduce<Record<string, number>>((counts, row) => {
      counts[row.trend] = (counts[row.trend] || 0) + 1;
      return counts;
    }, {});

    const topPerformers = rows
      .filter((row) => row.totalTasks > 0)
      .slice()
      .sort((a, b) => {
        if (b.successRate !== a.successRate) {
          return b.successRate - a.successRate;
        }
        return b.trustScore - a.trustScore;
      })
      .slice(0, 5);

    const needsAttention = rows
      .filter((row) => row.totalTasks > 0)
      .slice()
      .sort((a, b) => {
        if (a.successRate !== b.successRate) {
          return a.successRate - b.successRate;
        }
        return (a.agent.reputation ?? 0) - (b.agent.reputation ?? 0);
      })
      .slice(0, 5);

    return {
      rows,
      modeledCount: modeled.length,
      totalAgents: agents.length,
      averageSuccessRate:
        modeledTasks > 0 ? (modeledSuccesses / modeledTasks) * 100 : 0,
      trendCounts,
      topPerformers,
      needsAttention,
    };
  }, [agents, effectivenessByAgent]);
  const timelineAnalytics = useMemo(() => {
    const events = timelineEvents
      .filter((event) => typeof event?.timestamp === "number")
      .slice()
      .sort((a, b) => (b.timestamp ?? 0) - (a.timestamp ?? 0));
    const eventTypeCounts = events.reduce<Record<string, number>>((counts, event) => {
      const key = asText(event.event_type, "unknown");
      counts[key] = (counts[key] || 0) + 1;
      return counts;
    }, {});

    return {
      events,
      eventTypeCounts,
      uniqueAgents: new Set(
        events
          .map((event) => asText(event.agent_id || event.agent_name, ""))
          .filter(Boolean)
      ).size,
      replayDurationSec: asNumber(timelineReplay?.replay_duration_seconds),
      runDurationSec: asNumber(timelineReplay?.duration_seconds),
    };
  }, [timelineEvents, timelineReplay]);

  const updateGovernanceForm = (next: Governance) => {
    setGovPreset(next.preset);
    setGovAuditFrequency(next.overrides?.audit_frequency ?? 0.1);
    setGovTaxRate(next.overrides?.tax_rate ?? 0.05);
    setGovCircuitBreakerEnabled(next.overrides?.circuit_breaker?.enabled ?? true);
    setGovCircuitBreakerThreshold(next.overrides?.circuit_breaker?.threshold ?? 3);
  };

  const resetOrgScopedData = () => {
    setAgents([]);
    setTasks([]);
    setGovernance(null);
    setGovernanceHistory(null);
    setTimelineEvents([]);
    setTimelineReplay(null);
    setEffectivenessByAgent({});
    setEffectivenessError("");
    setEffectivenessLoading(false);
    setOrgError("");
  };

  const loadEffectivenessAnalytics = async (orgId: string, orgAgents: Agent[]) => {
    if (!orgId || orgAgents.length === 0) {
      setEffectivenessByAgent({});
      setEffectivenessError("");
      setEffectivenessLoading(false);
      return;
    }

    setEffectivenessLoading(true);
    setEffectivenessError("");

    try {
      const responses = await Promise.all(
        orgAgents.map(async (agent) => {
          const response = await fetch(
            `/api/dashboard/orgs/${orgId}/agents/${agent.agent_id}/effectiveness`
          );
          if (!response.ok) {
            return {
              agentId: agent.agent_id,
              data: null as AgentEffectiveness | null,
            };
          }
          const payload = (await response.json()) as AgentEffectiveness;
          return { agentId: agent.agent_id, data: payload };
        })
      );

      const next: Record<string, AgentEffectiveness> = {};
      let unavailableCount = 0;
      responses.forEach((entry) => {
        if (entry.data) {
          next[entry.agentId] = entry.data;
        } else {
          unavailableCount += 1;
        }
      });

      setEffectivenessByAgent(next);
      if (unavailableCount > 0) {
        setEffectivenessError(
          `Effectiveness unavailable for ${unavailableCount} agent${
            unavailableCount === 1 ? "" : "s"
          }.`
        );
      }
    } catch {
      setEffectivenessByAgent({});
      setEffectivenessError("Unable to load effectiveness analytics.");
    } finally {
      setEffectivenessLoading(false);
    }
  };

  const loadOrgScopedData = async (orgId: string) => {
    if (!orgId) {
      return;
    }

    setOrgLoading(true);
    setOrgError("");

    try {
      const [
        agentsRes,
        tasksRes,
        governanceRes,
        governanceHistoryRes,
        timelineRes,
        replayRes,
      ] = await Promise.all([
        fetch(`/api/dashboard/orgs/${orgId}/agents`),
        fetch(`/api/dashboard/orgs/${orgId}/tasks`),
        fetch(`/api/dashboard/orgs/${orgId}/governance`),
        fetch(`/api/dashboard/orgs/${orgId}/governance/history?limit=50`),
        fetch(`/api/dashboard/orgs/${orgId}/timeline?limit=300`),
        fetch(`/api/dashboard/orgs/${orgId}/timeline/replay?speed=2`),
      ]);

      const sectionErrors: string[] = [];
      let agentsData: Agent[] = [];

      if (agentsRes.ok) {
        agentsData = asArray<Agent>(await agentsRes.json());
        setAgents(agentsData);
        void loadEffectivenessAnalytics(orgId, agentsData);
      } else {
        setAgents([]);
        setEffectivenessByAgent({});
        setEffectivenessError("");
        sectionErrors.push("Agents unavailable");
      }

      if (tasksRes.ok) {
        const tasksData = asArray<TaskItem>(await tasksRes.json());
        setTasks(tasksData);
      } else {
        setTasks([]);
        sectionErrors.push("Tasks unavailable");
      }

      if (governanceRes.ok) {
        const governanceData = (await governanceRes.json()) as Governance | null;
        if (governanceData && typeof governanceData === "object") {
          setGovernance(governanceData);
          updateGovernanceForm(governanceData);
        } else {
          setGovernance(null);
          sectionErrors.push("Governance unavailable");
        }
      } else {
        setGovernance(null);
        sectionErrors.push("Governance unavailable");
      }

      if (governanceHistoryRes.ok) {
        const governanceHistoryData = (await governanceHistoryRes.json()) as
          | GovernanceHistory
          | null;
        const normalized: GovernanceHistory = {
          audit_timeline: asArray<AuditTimelineEntry>(
            governanceHistoryData?.audit_timeline
          ),
          circuit_breaker_history: asArray<CircuitBreakerHistoryEntry>(
            governanceHistoryData?.circuit_breaker_history
          ),
          stats:
            governanceHistoryData?.stats &&
            typeof governanceHistoryData.stats === "object"
              ? governanceHistoryData.stats
              : undefined,
        };
        setGovernanceHistory(normalized);
      } else {
        setGovernanceHistory(null);
        sectionErrors.push("Audits history unavailable");
      }

      if (timelineRes.ok) {
        const timelineData = (await timelineRes.json()) as
          | { events?: unknown }
          | null;
        setTimelineEvents(asArray<TimelineEventItem>(timelineData?.events));
      } else {
        setTimelineEvents([]);
        sectionErrors.push("Timeline unavailable");
      }

      if (replayRes.ok) {
        const replayData = (await replayRes.json()) as TimelineReplay | null;
        const normalizedReplay: TimelineReplay = {
          ...((replayData && typeof replayData === "object" ? replayData : {}) as TimelineReplay),
          events: asArray<TimelineEventItem>(replayData?.events),
        };
        setTimelineReplay(normalizedReplay);
      } else {
        setTimelineReplay(null);
        sectionErrors.push("Replay unavailable");
      }

      setOrgError(sectionErrors.join(". "));
    } catch {
      setOrgError("Unable to load organization workspace.");
      resetOrgScopedData();
    } finally {
      setOrgLoading(false);
    }
  };

  const fetchDashboard = async () => {
    setLoading(true);
    setError("");
    setAuthRequired(false);

    try {
      const [
        statsRes,
        savingsRes,
        requestsRes,
        topModelsRes,
        tenantRes,
        organizationsRes,
      ] = await Promise.all([
        fetch("/api/dashboard/gateway/stats"),
        fetch("/api/dashboard/gateway/savings"),
        fetch("/api/dashboard/gateway/requests?limit=50"),
        fetch("/api/dashboard/gateway/top-models?limit=5"),
        fetch("/api/dashboard/tenants/me"),
        fetch("/api/dashboard/tenants/me/organizations"),
      ]);

      if (
        [statsRes, savingsRes, requestsRes, topModelsRes, tenantRes, organizationsRes].some(
          (response) => response.status === 401
        )
      ) {
        setAuthRequired(true);
        throw new Error("Sign in required");
      }

      if (
        !statsRes.ok ||
        !savingsRes.ok ||
        !requestsRes.ok ||
        !topModelsRes.ok ||
        !tenantRes.ok ||
        !organizationsRes.ok
      ) {
        throw new Error("Failed to fetch dashboard data. Check your API key.");
      }

      const [
        statsData,
        savingsData,
        requestsData,
        topModelsData,
        tenantData,
        organizationsData,
      ] = await Promise.all([
        statsRes.json(),
        savingsRes.json(),
        requestsRes.json(),
        topModelsRes.json(),
        tenantRes.json(),
        organizationsRes.json(),
      ]);

      setStats((statsData ?? null) as Stats | null);
      setSavings((savingsData ?? null) as Savings | null);
      setRequests(Array.isArray(requestsData) ? (requestsData as GatewayRequest[]) : []);
      setTopModels(Array.isArray(topModelsData) ? (topModelsData as TopModel[]) : []);
      const nextTenantInfo = (tenantData ?? null) as TenantInfo | null;
      setTenantInfo(nextTenantInfo);
      await refreshCreditBilling(Boolean(nextTenantInfo?.stripe_customer_id));

      const nextOrganizations = Array.isArray(organizationsData)
        ? (organizationsData as Organization[])
        : [];
      setOrganizations(nextOrganizations);

      const fallbackOrgId = nextOrganizations[0]?.org_id ?? "";
      const preferredOrgId =
        selectedOrgId &&
        nextOrganizations.some((org) => org.org_id === selectedOrgId)
          ? selectedOrgId
          : fallbackOrgId;

      if (preferredOrgId) {
        setSelectedOrgId(preferredOrgId);
        try {
          window.sessionStorage.setItem(
            DASHBOARD_ORG_ID_STORAGE_KEY,
            preferredOrgId
          );
        } catch {
          // Ignore session storage write errors.
        }
        await loadOrgScopedData(preferredOrgId);
      } else {
        resetOrgScopedData();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load dashboard";
      if (message !== "Sign in required") {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authError) {
      setAuthRequired(true);
    }
  }, [authError]);

  useEffect(() => {
    try {
      const storedOrgId = window.sessionStorage.getItem(
        DASHBOARD_ORG_ID_STORAGE_KEY
      );
      if (storedOrgId) {
        setSelectedOrgId(storedOrgId);
      }
      void fetchDashboard();
    } catch {
      // Ignore session storage failures and still attempt server-side session auth.
      void fetchDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!tenantInfo) {
      setSuppressedWarnings([]);
      return;
    }
    try {
      const raw = window.localStorage.getItem(WARNING_SUPPRESSION_STORAGE_KEY);
      if (!raw) {
        setSuppressedWarnings([]);
        return;
      }
      const parsed = JSON.parse(raw) as Record<string, true> | null;
      if (!parsed || typeof parsed !== "object") {
        setSuppressedWarnings([]);
        return;
      }

      const currentPeriod = new Date().toISOString().slice(0, 7);
      const activeTenantPrefix = `${tenantInfo.tenant_id}:${currentPeriod}:`;
      const validIds = Object.keys(parsed).filter((key) =>
        key.startsWith(activeTenantPrefix)
      );
      setSuppressedWarnings(validIds);
    } catch {
      setSuppressedWarnings([]);
    }
  }, [tenantInfo]);

  useEffect(() => {
    if (!tenantInfo || onboardingViewedRef.current) {
      return;
    }
    onboardingViewedRef.current = true;
    trackDashboardEvent("onboarding_viewed", {
      tenant_id: tenantInfo.tenant_id,
      org_count: organizations.length,
    });
  }, [organizations.length, tenantInfo]);

  useEffect(() => {
    if (!tenantInfo) {
      orgEmptyStateViewedRef.current = false;
      return;
    }
    if (!hasOrganization && !orgEmptyStateViewedRef.current) {
      orgEmptyStateViewedRef.current = true;
      trackDashboardEvent("org_empty_state_viewed", {
        tenant_id: tenantInfo.tenant_id,
      });
    }
    if (hasOrganization) {
      orgEmptyStateViewedRef.current = false;
    }
  }, [hasOrganization, tenantInfo]);

  useEffect(() => {
    const previous = onboardingCompletedRef.current;
    if (hasOrganization && !previous.hasOrganization) {
      trackDashboardEvent("onboarding_step_completed", { step: "create_organization" });
    }
    if (firstTaskDone && !previous.firstTaskDone) {
      trackDashboardEvent("onboarding_step_completed", { step: "first_task" });
    }
    if (billingConfigured && !previous.billingConfigured) {
      trackDashboardEvent("onboarding_step_completed", { step: "billing_configured" });
    }
    onboardingCompletedRef.current = {
      hasOrganization,
      firstTaskDone,
      billingConfigured,
    };
  }, [billingConfigured, firstTaskDone, hasOrganization]);

  useEffect(() => {
    const onBeforeUnload = () => {
      if (tenantInfo && !onboardingComplete) {
        trackDashboardEvent("onboarding_abandoned", {
          tenant_id: tenantInfo.tenant_id,
          has_organization: hasOrganization,
          first_task_done: firstTaskDone,
          billing_configured: billingConfigured,
        });
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [billingConfigured, firstTaskDone, hasOrganization, onboardingComplete, tenantInfo]);

  const signOut = () => {
    setStats(null);
    setSavings(null);
    setRequests([]);
    setTopModels([]);
    setTenantInfo(null);
    setOrganizations([]);
    setSelectedOrgId("");
    setSuppressedWarnings([]);
    resetOrgScopedData();
    setError("");

    window.location.href = "/api/auth/logout?returnTo=/dashboard";
  };

  const handleOrgSelection = async (orgId: string) => {
    setSelectedOrgId(orgId);
    try {
      window.sessionStorage.setItem(DASHBOARD_ORG_ID_STORAGE_KEY, orgId);
    } catch {
      // Ignore session storage write errors.
    }

    if (orgId) {
      await loadOrgScopedData(orgId);
      trackDashboardEvent("onboarding_step_clicked", { step: "select_organization" });
    }
  };

  const handleCreateOrganization = async () => {
    const packageName = orgPackageName.trim() || DEFAULT_ONBOARDING_PACKAGE;
    setCreatingOrg(true);
    setOrgError("");
    trackDashboardEvent("onboarding_step_clicked", { step: "create_organization" });
    trackDashboardEvent("org_create_cta_clicked", { package_name: packageName });
    try {
      const response = await fetch("/api/dashboard/orgs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          package_name: packageName,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail || "Unable to create organization");
      }
      trackDashboardEvent("org_create_succeeded", { package_name: packageName });
      await fetchDashboard();
      setActiveTab("tasks");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unable to create organization";
      setOrgError(message);
      trackDashboardEvent("org_create_failed", {
        package_name: packageName,
        reason: message,
      });
    } finally {
      setCreatingOrg(false);
    }
  };

  const handleTaskSubmit = async () => {
    if (!selectedOrgId || !taskDescription.trim()) {
      return;
    }

    setSubmittingTask(true);
    setOrgError("");

    try {
      const response = await fetch(`/api/dashboard/orgs/${selectedOrgId}/tasks`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          description: taskDescription.trim(),
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail || "Unable to submit task");
      }

      setTaskDescription("");
      await loadOrgScopedData(selectedOrgId);
      setActiveTab("tasks");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unable to submit task";
      setOrgError(message);
    } finally {
      setSubmittingTask(false);
    }
  };

  const handleGovernanceUpdate = async () => {
    if (!selectedOrgId) {
      return;
    }

    setGovUpdating(true);
    setOrgError("");

    try {
      const response = await fetch(`/api/dashboard/orgs/${selectedOrgId}/governance`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          preset: govPreset,
          rollout_strategy: "immediate",
          overrides: {
            audit_frequency: govAuditFrequency,
            tax_rate: govTaxRate,
            circuit_breaker: {
              enabled: govCircuitBreakerEnabled,
              threshold: govCircuitBreakerThreshold,
            },
          },
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail || "Unable to update governance");
      }

      await loadOrgScopedData(selectedOrgId);
      setActiveTab("governance");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unable to update governance";
      setOrgError(message);
    } finally {
      setGovUpdating(false);
    }
  };

  const openBillingPortal = async () => {
    try {
      const response = await fetch("/api/dashboard/billing/portal", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      const payload = (await response.json().catch(() => null)) as
        | { portal_url?: string; detail?: string }
        | null;
      if (!response.ok || !payload?.portal_url) {
        throw new Error(payload?.detail || "Unable to open billing portal");
      }
      window.location.href = payload.portal_url;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unable to open billing portal";
      setError(message);
    }
  };

  const refreshCreditBilling = async (hasStripeCustomer: boolean) => {
    if (!hasStripeCustomer) {
      setCreditSummary(null);
      setCreditTopUpConfig(null);
      return;
    }

    const [summaryResponse, configResponse] = await Promise.all([
      fetch("/api/dashboard/billing/credit-balance-summary"),
      fetch("/api/dashboard/billing/credit-topup-config"),
    ]);

    if (summaryResponse.ok) {
      const summaryPayload = (await summaryResponse.json().catch(() => null)) as
        | CreditBalanceSummary
        | null;
      setCreditSummary(summaryPayload);
    } else {
      setCreditSummary(null);
    }

    if (configResponse.ok) {
      const configPayload = (await configResponse.json().catch(() => null)) as
        | CreditTopUpConfig
        | null;
      setCreditTopUpConfig(configPayload);
    } else {
      setCreditTopUpConfig(null);
    }
  };

  const startBillingCheckout = async () => {
    if (!tenantInfo) {
      return;
    }
    setBillingLoading(true);
    setError("");
    try {
      let stripeCustomerId = tenantInfo.stripe_customer_id ?? null;
      if (!stripeCustomerId) {
        const setupResponse = await fetch("/api/dashboard/billing/setup-customer", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
        });
        const setupPayload = (await setupResponse.json().catch(() => null)) as
          | { stripe_customer_id?: string; detail?: string }
          | null;
        if (!setupResponse.ok || !setupPayload?.stripe_customer_id) {
          throw new Error(setupPayload?.detail || "Unable to initialize billing customer");
        }
        stripeCustomerId = setupPayload.stripe_customer_id;
        setTenantInfo((previous) =>
          previous
            ? {
                ...previous,
                stripe_customer_id: stripeCustomerId ?? previous.stripe_customer_id,
              }
            : previous
        );
      }

      const isHttps = window.location.protocol === "https:";
      const checkoutBody: Record<string, string> = {};
      if (isHttps) {
        checkoutBody.success_url = `${window.location.origin}/welcome?billing=active`;
        checkoutBody.cancel_url = `${window.location.origin}/welcome?billing=cancelled`;
      }

      const checkoutResponse = await fetch("/api/dashboard/billing/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(checkoutBody),
      });
      const checkoutPayload = (await checkoutResponse.json().catch(() => null)) as
        | { checkout_url?: string; detail?: string }
        | null;
      if (!checkoutResponse.ok || !checkoutPayload?.checkout_url) {
        throw new Error(checkoutPayload?.detail || "Unable to create checkout session");
      }
      window.location.href = checkoutPayload.checkout_url;
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unable to start billing checkout";
      setError(message);
    } finally {
      setBillingLoading(false);
    }
  };

  const startCreditTopUpCheckout = async () => {
    setBillingLoading(true);
    setError("");
    try {
      const response = await fetch("/api/dashboard/billing/credit-topup-checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      const payload = (await response.json().catch(() => null)) as
        | { checkout_url?: string; detail?: string }
        | null;
      if (!response.ok || !payload?.checkout_url) {
        throw new Error(payload?.detail || "Unable to start credit top-up checkout");
      }
      window.location.href = payload.checkout_url;
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Unable to start credit top-up checkout";
      setError(message);
    } finally {
      setBillingLoading(false);
    }
  };

  const dismissWarning = (warningId: string) => {
    const next = Array.from(new Set([...suppressedWarnings, warningId]));
    setSuppressedWarnings(next);
    try {
      const payload = Object.fromEntries(next.map((id) => [id, true]));
      window.localStorage.setItem(
        WARNING_SUPPRESSION_STORAGE_KEY,
        JSON.stringify(payload)
      );
    } catch {
      // Ignore local storage failures.
    }
  };

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl flex items-center justify-between px-6 py-4">
          <a href="/" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
              <span className="text-sm font-bold text-black">0H</span>
            </div>
            <span className="text-lg font-bold tracking-tight">Zero Human Labs</span>
          </a>
          <div className="hidden sm:flex gap-4">
            <a
              href="/dashboard"
              className="text-sm text-[var(--color-text)]"
              aria-current="page"
            >
              Dashboard
            </a>
            <a
              href="/quickstart"
              className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            >
              Quickstart
            </a>
            <a
              href="#billing-settings"
              className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            >
              Settings
            </a>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-7xl px-4 pt-30 pb-16 sm:px-6 sm:pt-32 sm:pb-24">
        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Tenant Command Center
            </h1>
            <p className="mt-2 text-[var(--color-text-muted)]">
              Usage, operations, and governance controls in one secure workspace.
            </p>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2 text-xs text-[var(--color-text-muted)]">
            Org-scoped data is loaded through tenant-verified API endpoints.
          </div>
        </div>

        <div className="mb-8 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 sm:p-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
            <div>
              <label className="block text-sm font-semibold mb-2">Session</label>
              <p className="mb-3 text-xs text-[var(--color-text-muted)]">
                Dashboard access uses your OIDC-backed secure session.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={() => void fetchDashboard()}
                  disabled={loading}
                  className="rounded-lg bg-[var(--color-accent)] px-6 py-2 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-50"
                >
                  {loading ? "Loading..." : "Load Dashboard"}
                </button>
                <button
                  onClick={signOut}
                  type="button"
                  className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-all"
                >
                  Sign out
                </button>
                {authRequired && authCanRetrySignIn && (
                  <a
                    href="/api/auth/login?returnTo=/dashboard"
                    className="inline-flex items-center justify-center rounded-lg bg-[var(--color-accent)] px-6 py-2 text-sm font-semibold text-black hover:brightness-110 transition-all"
                  >
                    Sign in with OIDC
                  </a>
                )}
              </div>
              {error && <p className="mt-3 text-sm text-[var(--color-danger)]">{error}</p>}
              {authError?.message && (
                <p className="mt-3 text-sm text-[var(--color-danger)]">{authError.message}</p>
              )}
              {authRequired && (
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  {!authCanRetrySignIn
                    ? "Sign-in is temporarily unavailable until OIDC is configured."
                    : "Your session expired or is missing. Sign in to continue."}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold mb-2">Organization</label>
              <p className="mb-3 text-xs text-[var(--color-text-muted)]">
                Choose an organization from your tenant scope.
              </p>
              <select
                value={selectedOrgId}
                onChange={(event) => {
                  void handleOrgSelection(event.target.value);
                }}
                disabled={!organizations.length || loading}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] disabled:opacity-60"
              >
                <option value="">
                  {organizations.length ? "Select organization" : "No organizations yet"}
                </option>
                {organizations.map((org) => (
                  <option key={org.org_id} value={org.org_id}>
                    {org.name} ({org.status})
                  </option>
                ))}
              </select>
              {selectedOrg && (
                <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                  {selectedOrg.org_id} · created {new Date(selectedOrg.created_at).toLocaleDateString()}
                </p>
              )}
              {!organizations.length && (
                <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                  <p className="text-sm font-semibold">No organizations yet</p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    Create an organization to unlock task execution and onboarding progression.
                  </p>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <input
                      value={orgPackageName}
                      onChange={(event) => setOrgPackageName(event.target.value)}
                      placeholder={DEFAULT_ONBOARDING_PACKAGE}
                      className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        void handleCreateOrganization();
                      }}
                      disabled={creatingOrg || loading}
                      className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:brightness-110 disabled:opacity-50"
                    >
                      {creatingOrg ? "Creating..." : "Create organization"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="sticky top-20 z-20 mb-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)]/95 p-2 backdrop-blur">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-9">
            {[
              { id: "usage", label: "Usage" },
              { id: "timeline", label: "Timeline" },
              { id: "run_health", label: "Run Health" },
              { id: "effectiveness", label: "Effectiveness" },
              { id: "reputation", label: "Reputation" },
              { id: "agents", label: "Agents" },
              { id: "tasks", label: "Tasks" },
              { id: "governance", label: "Governance" },
              { id: "settings", label: "Settings" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as DashboardTab)}
                className={`rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
                  activeTab === tab.id
                    ? "bg-[var(--color-accent)] text-black"
                    : "text-[var(--color-text-muted)] hover:bg-[var(--color-bg-card)] hover:text-[var(--color-text)]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {orgError && (
          <div className="mb-6 rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-4 py-3 text-sm text-[var(--color-danger)]">
            {orgError}
          </div>
        )}

        {activeTab === "usage" && stats && savings && (
          <>
            {activeWarnings.length > 0 && (
              <div className="mb-8 space-y-3">
                {activeWarnings.map((warning) => (
                  <div
                    key={warning.id}
                    className={`rounded-xl border px-4 py-3 ${
                      warning.severity === "danger"
                        ? "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10"
                        : "border-yellow-500/40 bg-yellow-500/10"
                    }`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold">{warning.title}</p>
                        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                          {warning.detail}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => dismissWarning(warning.id)}
                        className="self-start rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                      >
                        Dismiss this threshold
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 mb-8">
              <h2 className="text-2xl font-bold">Onboarding Checklist</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Complete these steps to fully activate your tenant.
              </p>
              <ul className="mt-4 space-y-3 text-sm">
                <li className="flex items-center gap-3">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      tenantInfo
                        ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {tenantInfo ? "✓" : "1"}
                  </span>
                  <span>Account created</span>
                </li>
                <li className="flex items-center gap-3">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      hasOrganization
                        ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {hasOrganization ? "✓" : "2"}
                  </span>
                  <span>
                    Create your first organization{" "}
                    {!hasOrganization && (
                      <button
                        type="button"
                        onClick={() => {
                          trackDashboardEvent("onboarding_step_clicked", { step: "create_organization" });
                          const input = document.querySelector<HTMLInputElement>(
                            "input[placeholder='saas_dev_studio']"
                          );
                          input?.focus();
                        }}
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        (start here)
                      </button>
                    )}
                  </span>
                </li>
                <li className="flex items-center gap-3">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      firstTaskDone
                        ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {firstTaskDone ? "✓" : "3"}
                  </span>
                  <span>
                    Run your first task{" "}
                    {!firstTaskDone && (
                      <button
                        type="button"
                        onClick={() => {
                          trackDashboardEvent("onboarding_step_clicked", { step: "first_task" });
                          setActiveTab("tasks");
                        }}
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        (open Tasks)
                      </button>
                    )}
                  </span>
                </li>
                <li className="flex items-center gap-3">
                  <span
                    className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      billingConfigured
                        ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                        : "bg-[var(--color-bg)] text-[var(--color-text-muted)]"
                    }`}
                  >
                    {billingConfigured ? "✓" : "4"}
                  </span>
                  <span>
                    Configure billing{" "}
                    {!billingConfigured && (
                      <a
                        href="#billing-settings"
                        onClick={() => {
                          trackDashboardEvent("onboarding_step_clicked", {
                            step: "billing_configured",
                          });
                        }}
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        (configure now)
                      </a>
                    )}
                  </span>
                </li>
              </ul>
              <p className="mt-4 text-xs text-[var(--color-text-muted)]">
                Progress: {onboardingComplete ? "4/4 complete" : billingConfigured || firstTaskDone || hasOrganization ? `${1 + Number(hasOrganization) + Number(firstTaskDone) + Number(billingConfigured)}/4 complete` : "1/4 complete"}
              </p>
            </div>

            {stats.total_requests === 0 && (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 mb-8">
                <h2 className="text-2xl font-bold">No requests yet</h2>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  Your dashboard is working. Data will appear after your first API call.
                </p>
                <a
                  href="/quickstart"
                  onClick={() => {
                    trackDashboardEvent("onboarding_step_clicked", { step: "first_api_call" });
                  }}
                  className="mt-4 inline-block rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:brightness-110 transition-all"
                >
                  Make your first API call
                </a>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 mb-8 md:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Total Requests</div>
                <div className="text-3xl font-bold">{formatNumber(stats.total_requests)}</div>
              </div>

              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Total Tokens</div>
                <div className="text-3xl font-bold">{formatNumber(stats.total_tokens_in + stats.total_tokens_out)}</div>
                <div className="text-xs text-[var(--color-text-dim)] mt-1">
                  {formatNumber(stats.total_tokens_in)} in / {formatNumber(stats.total_tokens_out)} out
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Total Cost</div>
                <div className="text-3xl font-bold">{formatCost(stats.total_customer_cost)}</div>
              </div>

              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Avg Latency</div>
                <div className="text-3xl font-bold">{Math.round(stats.avg_latency_ms)}ms</div>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 p-6 mb-8">
              <h2 className="text-2xl font-bold mb-4">Cost Savings</h2>
              <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                <div>
                  <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Cache Savings</div>
                  <div className="text-2xl font-bold text-[var(--color-success)]">{formatCost(savings.cache_savings_usd)}</div>
                  <div className="text-xs text-[var(--color-text-dim)] mt-1">
                    {savings.cache_hits} cached requests ({Math.round((savings.cache_hits / Math.max(savings.total_requests, 1)) * 100)}%)
                  </div>
                </div>

                <div>
                  <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Smart Routing</div>
                  <div className="text-2xl font-bold">{savings.smart_routed} requests</div>
                  <div className="text-xs text-[var(--color-text-dim)] mt-1">Auto-routed to optimal models</div>
                </div>

                <div>
                  <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Cache Hit Rate</div>
                  <div className="text-2xl font-bold">
                    {Math.round((stats.cache_hits / Math.max(stats.total_requests, 1)) * 100)}%
                  </div>
                  <div className="text-xs text-[var(--color-text-dim)] mt-1">Zero-cost cached responses</div>
                </div>
              </div>
            </div>

            {tenantInfo && (
              <div
                id="billing-settings"
                className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 mb-8"
              >
                <h2 className="text-2xl font-bold mb-4">Billing Status</h2>
                {activeWarnings.some((warning) => warning.metric === "budget") && (
                  <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-[var(--color-text-muted)]">
                    Proactive budget warning active. Remaining budget shown below before hard limits trigger.
                  </div>
                )}
                <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                  <div>
                    <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Current Plan</div>
                    <div className="text-2xl font-bold capitalize">{tenantInfo.tier}</div>
                    <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                      Billing status: {billingStatus.replaceAll("_", " ")}
                    </p>
                  </div>

                  <div>
                    <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Usage / Limit</div>
                    <div className="text-2xl font-bold">
                      {formatCost(tenantInfo.total_spent_usd)} / {formatCost(tenantInfo.budget_limit_usd)}
                    </div>
                    <div className="mt-2 h-2 bg-[var(--color-bg)] rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          tenantInfo.total_spent_usd / Math.max(tenantInfo.budget_limit_usd, 1) >= 0.9
                            ? "bg-[var(--color-danger)]"
                            : tenantInfo.total_spent_usd / Math.max(tenantInfo.budget_limit_usd, 1) >= 0.7
                              ? "bg-yellow-500"
                              : "bg-[var(--color-success)]"
                        }`}
                        style={{
                          width: `${Math.min(
                            (tenantInfo.total_spent_usd / Math.max(tenantInfo.budget_limit_usd, 1)) * 100,
                            100
                          )}%`,
                        }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                      Available prepaid credits: {formattedAvailableCredits}
                    </p>
                  </div>

                  <div>
                    <div className="text-sm font-semibold text-[var(--color-text-muted)] mb-2">Actions</div>
                    <div className="flex flex-wrap gap-3">
                      {billingConfigured && billingActive ? (
                        <button
                          type="button"
                          onClick={() => void openBillingPortal()}
                          disabled={billingLoading}
                          className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold hover:bg-[var(--color-bg)] transition-all"
                        >
                          Manage Billing
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            void startBillingCheckout();
                          }}
                          disabled={billingLoading}
                          className="inline-block rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-black hover:brightness-110 transition-all disabled:opacity-60"
                        >
                          {billingLoading
                            ? "Opening checkout..."
                            : billingConfigured
                              ? "Complete Billing Setup"
                              : "Add Billing Details"}
                        </button>
                      )}
                      {billingConfigured && billingActive && creditTopUpConfig?.enabled && (
                        <button
                          type="button"
                          onClick={() => {
                            void startCreditTopUpCheckout();
                          }}
                          disabled={billingLoading}
                          className="rounded-lg border border-[var(--color-border-bright)] px-4 py-2 text-sm font-semibold hover:bg-[var(--color-bg)] transition-all"
                        >
                          {billingLoading
                            ? "Opening checkout..."
                            : creditTopUpConfig.name || "Buy Credits"}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                <p className="mt-4 text-xs text-[var(--color-text-muted)]">
                  Budget warning emails are sent automatically when spending reaches your configured threshold.
                </p>
              </div>
            )}

            {topModels.length > 0 && (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6 mb-8">
                <h2 className="text-2xl font-bold mb-4">Top Models Used</h2>
                <div className="space-y-4">
                  {topModels.map((model) => {
                    const maxCount = topModels[0].request_count;
                    const percentage = (model.request_count / Math.max(maxCount, 1)) * 100;
                    return (
                      <div key={model.model_id}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-mono">{model.model_id}</span>
                          <span className="text-sm text-[var(--color-text-muted)]">
                            {formatNumber(model.request_count)} requests
                          </span>
                        </div>
                        <div className="h-2 bg-[var(--color-bg)] rounded-full overflow-hidden">
                          <div className="h-full bg-[var(--color-accent)]" style={{ width: `${percentage}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {requests.length > 0 && (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <h2 className="text-2xl font-bold mb-4">Recent Requests</h2>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="text-[var(--color-text-muted)]">
                      <tr>
                        <th className="pb-3 pr-4 font-medium">Time</th>
                        <th className="pb-3 pr-4 font-medium">Model</th>
                        <th className="pb-3 pr-4 font-medium">Tokens</th>
                        <th className="pb-3 pr-4 font-medium">Cost</th>
                        <th className="pb-3 pr-4 font-medium">Cache</th>
                      </tr>
                    </thead>
                    <tbody className="text-[var(--color-text)]">
                      {requests.slice(0, 20).map((request) => (
                        <tr key={request.request_id} className="border-t border-[var(--color-border)]">
                          <td className="py-3 pr-4 text-[var(--color-text-muted)]">
                            {new Date(request.timestamp * 1000).toLocaleString()}
                          </td>
                          <td className="py-3 pr-4 font-mono text-xs">{request.model_id}</td>
                          <td className="py-3 pr-4">
                            {formatNumber(request.tokens_in + request.tokens_out)}
                          </td>
                          <td className="py-3 pr-4">{formatCost(request.customer_cost)}</td>
                          <td className="py-3 pr-4">
                            {request.cached ? (
                              <span className="rounded-full bg-[var(--color-success)]/15 px-2 py-1 text-xs text-[var(--color-success)]">
                                Cached
                              </span>
                            ) : (
                              <span className="rounded-full bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text-muted)]">
                                Live
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab !== "usage" && !selectedOrgId && (
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 text-center">
            <h2 className="text-2xl font-bold">Select an organization</h2>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Pick an organization to unlock agent operations, task execution, and governance controls.
            </p>
          </div>
        )}

        {activeTab === "effectiveness" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Effectiveness Analytics</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Success rate, trust, and trend telemetry by agent.
              </p>
            </div>

            {effectivenessError && (
              <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-[var(--color-text-muted)]">
                {effectivenessError}
              </div>
            )}

            {orgLoading || effectivenessLoading ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">
                  Loading effectiveness analytics...
                </p>
              </div>
            ) : agents.length === 0 ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No agents available for effectiveness analytics.
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Agents Modeled
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {effectivenessAnalytics.modeledCount}/{effectivenessAnalytics.totalAgents}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-success)]/25 bg-[var(--color-success)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Weighted Success Rate
                    </p>
                    <p className="mt-2 text-3xl font-extrabold text-[var(--color-success)]">
                      {effectivenessAnalytics.averageSuccessRate.toFixed(1)}%
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Improving
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {formatNumber(effectivenessAnalytics.trendCounts.improving || 0)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-danger)]/25 bg-[var(--color-danger)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Declining
                    </p>
                    <p className="mt-2 text-3xl font-extrabold text-[var(--color-danger)]">
                      {formatNumber(effectivenessAnalytics.trendCounts.declining || 0)}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Top Performers</h3>
                    {effectivenessAnalytics.topPerformers.length === 0 ? (
                      <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                        No task history available yet.
                      </p>
                    ) : (
                      <div className="mt-4 space-y-3">
                        {effectivenessAnalytics.topPerformers.map((entry) => (
                          <article
                            key={entry.agent.agent_id}
                            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4"
                          >
                            <div className="flex items-center justify-between gap-4">
                              <p className="font-semibold">{entry.agent.name || entry.agent.agent_id}</p>
                              <span className="text-sm text-[var(--color-success)]">
                                {entry.successRate.toFixed(1)}%
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                              Trend: {entry.trend} · Trust {entry.trustScore.toFixed(2)} ·
                              p50 duration {Math.round(entry.p50Duration || 0)}s
                            </p>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Needs Attention</h3>
                    {effectivenessAnalytics.needsAttention.length === 0 ? (
                      <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                        No low-performing agents detected.
                      </p>
                    ) : (
                      <div className="mt-4 space-y-3">
                        {effectivenessAnalytics.needsAttention.map((entry) => (
                          <article
                            key={entry.agent.agent_id}
                            className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 p-4"
                          >
                            <div className="flex items-center justify-between gap-4">
                              <p className="font-semibold">{entry.agent.name || entry.agent.agent_id}</p>
                              <span className="text-sm text-[var(--color-danger)]">
                                {entry.successRate.toFixed(1)}%
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                              Trend: {entry.trend} · Reputation {(entry.agent.reputation ?? 0).toFixed(2)} ·
                              Tasks {formatNumber(entry.totalTasks)}
                            </p>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "timeline" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Organization Timeline</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Replay how work unfolded across agents, tasks, and governance events.
              </p>
            </div>

            {orgLoading ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">Loading timeline...</p>
              </div>
            ) : timelineAnalytics.events.length === 0 ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No timeline events yet. Submit tasks to generate a replayable run history.
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Events
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {formatNumber(timelineAnalytics.events.length)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Active Agents
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {formatNumber(timelineAnalytics.uniqueAgents)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Run Duration
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {Math.round(timelineAnalytics.runDurationSec)}s
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-accent)]/25 bg-[var(--color-accent)]/10 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">
                      Replay Duration
                    </p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {Math.round(timelineAnalytics.replayDurationSec)}s
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Event Type Breakdown</h3>
                    <div className="mt-4 space-y-3">
                      {Object.entries(timelineAnalytics.eventTypeCounts)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 8)
                        .map(([eventType, count]) => {
                          const percent =
                            timelineAnalytics.events.length > 0
                              ? (count / timelineAnalytics.events.length) * 100
                              : 0;
                          return (
                            <div key={eventType}>
                              <div className="mb-1 flex items-center justify-between text-sm">
                                <span className="font-mono text-xs">{eventType}</span>
                                <span className="text-[var(--color-text-muted)]">
                                  {formatNumber(count)} ({percent.toFixed(0)}%)
                                </span>
                              </div>
                              <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
                                <div
                                  className="h-full bg-[var(--color-accent)]"
                                  style={{ width: `${Math.min(percent, 100)}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Latest Events</h3>
                    <div className="mt-4 space-y-3">
                      {timelineAnalytics.events.slice(0, 10).map((event, index) => (
                        <article
                          key={`${event.timestamp ?? "ts"}:${event.event_type ?? "event"}:${index}`}
                          className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-medium leading-snug">
                              {asText(event.title, "Untitled event")}
                            </p>
                            <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-accent)]">
                              {asText(event.event_type, "unknown")}
                            </span>
                          </div>
                          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                            {asText(event.agent_name || event.agent_id, "system")} ·{" "}
                            {typeof event.timestamp === "number"
                              ? new Date(event.timestamp * 1000).toLocaleString()
                              : "No timestamp"}
                          </p>
                          {event.detail && (
                            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                              {asText(event.detail, "")}
                            </p>
                          )}
                        </article>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "reputation" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Reputation Analytics</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Monitor trust tiers, score distribution, and risk concentration.
              </p>
            </div>

            {orgLoading ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">Loading reputation analytics...</p>
              </div>
            ) : agents.length === 0 ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">
                  No agents available for reputation analytics.
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Avg Reputation</p>
                    <p className="mt-2 text-3xl font-extrabold">{reputationAnalytics.average.toFixed(2)}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Median Reputation</p>
                    <p className="mt-2 text-3xl font-extrabold">{reputationAnalytics.median.toFixed(2)}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-success)]/25 bg-[var(--color-success)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Highest</p>
                    <p className="mt-2 text-lg font-bold">
                      {reputationAnalytics.highest?.name || reputationAnalytics.highest?.agent_id || "n/a"}
                    </p>
                    <p className="mt-1 text-sm text-[var(--color-success)]">
                      {(reputationAnalytics.highest?.reputation ?? 0).toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-danger)]/25 bg-[var(--color-danger)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Lowest</p>
                    <p className="mt-2 text-lg font-bold">
                      {reputationAnalytics.lowest?.name || reputationAnalytics.lowest?.agent_id || "n/a"}
                    </p>
                    <p className="mt-1 text-sm text-[var(--color-danger)]">
                      {(reputationAnalytics.lowest?.reputation ?? 0).toFixed(2)}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Trust Tier Distribution</h3>
                    <div className="mt-4 space-y-3">
                      {Object.entries(reputationAnalytics.trustTierCounts)
                        .sort((a, b) => b[1] - a[1])
                        .map(([tier, count]) => {
                          const percent = agents.length > 0 ? (count / agents.length) * 100 : 0;
                          return (
                            <div key={tier}>
                              <div className="mb-1 flex items-center justify-between text-sm">
                                <span className="capitalize">{tier}</span>
                                <span className="text-[var(--color-text-muted)]">
                                  {formatNumber(count)} ({percent.toFixed(0)}%)
                                </span>
                              </div>
                              <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
                                <div
                                  className="h-full bg-[var(--color-accent)]"
                                  style={{ width: `${Math.min(percent, 100)}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">At-Risk Agents</h3>
                    {reputationAnalytics.atRisk.length === 0 ? (
                      <p className="mt-4 text-sm text-[var(--color-text-muted)]">
                        No agents currently flagged as at-risk.
                      </p>
                    ) : (
                      <div className="mt-4 space-y-3">
                        {reputationAnalytics.atRisk.map((agent) => (
                          <article
                            key={agent.agent_id}
                            className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 p-4"
                          >
                            <div className="flex items-center justify-between gap-4">
                              <p className="font-semibold">{agent.name || agent.agent_id}</p>
                              <span className="text-sm text-[var(--color-danger)]">
                                {(agent.reputation ?? 0).toFixed(2)}
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                              Trust tier: {agent.trust_tier || "unknown"} · Trust score{" "}
                              {(agent.trust_score ?? 0).toFixed(2)}
                            </p>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "agents" && selectedOrgId && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Agents</p>
                <p className="mt-2 text-3xl font-extrabold">{agents.length}</p>
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Avg Reputation</p>
                <p className="mt-2 text-3xl font-extrabold">
                  {agents.length
                    ? (agents.reduce((sum, agent) => sum + (agent.reputation ?? 0), 0) / agents.length).toFixed(2)
                    : "0.00"}
                </p>
              </div>
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Total Wallet Balance</p>
                <p className="mt-2 text-3xl font-extrabold">
                  {formatCost(agents.reduce((sum, agent) => sum + (agent.balance ?? 0), 0))}
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold mb-4">Agent Comparison</h2>
              {orgLoading ? (
                <p className="text-sm text-[var(--color-text-muted)]">Loading agents...</p>
              ) : agents.length === 0 ? (
                <p className="text-sm text-[var(--color-text-muted)]">No agents found for this organization.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[820px] text-left text-sm">
                    <thead className="text-[var(--color-text-muted)]">
                      <tr>
                        <th className="pb-3 pr-4 font-medium">Agent</th>
                        <th className="pb-3 pr-4 font-medium">Division</th>
                        <th className="pb-3 pr-4 font-medium">Trust</th>
                        <th className="pb-3 pr-4 font-medium">Reputation</th>
                        <th className="pb-3 pr-4 font-medium">Wallet</th>
                        <th className="pb-3 pr-4 font-medium">Tasks</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agents
                        .slice()
                        .sort((a, b) => (b.reputation ?? 0) - (a.reputation ?? 0))
                        .map((agent) => (
                          <tr key={agent.agent_id} className="border-t border-[var(--color-border)]">
                            <td className="py-3 pr-4 font-medium">{agent.name || agent.agent_id}</td>
                            <td className="py-3 pr-4 text-[var(--color-text-muted)]">{agent.division || "-"}</td>
                            <td className="py-3 pr-4">
                              <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-1 text-xs text-[var(--color-accent)]">
                                {agent.trust_tier || "n/a"} ({(agent.trust_score ?? 0).toFixed(2)})
                              </span>
                            </td>
                            <td className="py-3 pr-4">{(agent.reputation ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4">{formatCost(agent.balance ?? 0)}</td>
                            <td className="py-3 pr-4">
                              {(agent.tasks_completed ?? 0) + (agent.tasks_failed ?? 0)}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "tasks" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Submit Task</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Queue work for your organization. Execution happens asynchronously via worker.
              </p>
              <textarea
                value={taskDescription}
                onChange={(event) => setTaskDescription(event.target.value)}
                rows={4}
                placeholder="Describe the task outcome you want."
                className="mt-4 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => {
                    void handleTaskSubmit();
                  }}
                  disabled={!taskDescription.trim() || submittingTask}
                  className="rounded-lg bg-[var(--color-accent)] px-5 py-2 text-sm font-semibold text-black disabled:opacity-50"
                >
                  {submittingTask ? "Submitting..." : "Submit Task"}
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold mb-4">Recent Tasks</h2>
              {orgLoading ? (
                <p className="text-sm text-[var(--color-text-muted)]">Loading tasks...</p>
              ) : tasks.length === 0 ? (
                <p className="text-sm text-[var(--color-text-muted)]">No tasks submitted yet.</p>
              ) : (
                <div className="space-y-3">
                  {tasks
                    .slice()
                    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
                    .slice(0, 12)
                    .map((task) => (
                      <article
                        key={task.task_id}
                        className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4"
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <p className="font-medium leading-relaxed">
                            {asText(task.description, "No description")}
                          </p>
                          <span className="rounded-full bg-[var(--color-accent)]/15 px-2 py-1 text-xs text-[var(--color-accent)]">
                            {asText(task.status, "unknown")}
                          </span>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-text-muted)]">
                          <span>ID: {asText(task.task_id, "").slice(0, 12) || "n/a"}</span>
                          <span>Assigned: {asText(task.assigned_to, "pending")}</span>
                          <span>Governance: {asText(task.governance_preset, "n/a")}</span>
                          <span>
                            {task.created_at
                              ? new Date(task.created_at).toLocaleString()
                              : "No timestamp"}
                          </span>
                        </div>
                      </article>
                    ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "run_health" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Run Failure Metrics</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Health trends computed from task execution outcomes for this organization.
              </p>
            </div>

            {orgLoading ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <p className="text-sm text-[var(--color-text-muted)]">Loading run health...</p>
              </div>
            ) : runHealth.totalRuns === 0 ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                <h3 className="text-xl font-bold">No completed runs yet</h3>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                  Execute tasks from the Tasks tab to populate run health analytics.
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Total Runs</p>
                    <p className="mt-2 text-3xl font-extrabold">{formatNumber(runHealth.totalRuns)}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Failed Runs</p>
                    <p className="mt-2 text-3xl font-extrabold text-[var(--color-danger)]">
                      {formatNumber(runHealth.failedRuns)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Failure Rate</p>
                    <p className="mt-2 text-3xl font-extrabold">
                      {runHealth.failureRate.toFixed(1)}%
                    </p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 p-5">
                    <p className="text-xs uppercase tracking-[0.14em] text-[var(--color-text-dim)]">Success Rate</p>
                    <p className="mt-2 text-3xl font-extrabold text-[var(--color-success)]">
                      {runHealth.successRate.toFixed(1)}%
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Daily Failure Trend (7 days)</h3>
                    <div className="mt-5 space-y-3">
                      {runHealth.dailyTrend.map((point) => (
                        <div key={point.label}>
                          <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                            <span>{point.label}</span>
                            <span>
                              {point.failures}/{point.runs} ({point.failureRate.toFixed(0)}%)
                            </span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
                            <div
                              className="h-full bg-[var(--color-danger)]"
                              style={{ width: `${Math.min(point.failureRate, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Weekly Failure Trend (6 weeks)</h3>
                    <div className="mt-5 space-y-3">
                      {runHealth.weeklyTrend.map((point) => (
                        <div key={point.label}>
                          <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                            <span>{point.label}</span>
                            <span>
                              {point.failures}/{point.runs} ({point.failureRate.toFixed(0)}%)
                            </span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
                            <div
                              className="h-full bg-yellow-500"
                              style={{ width: `${Math.min(point.failureRate, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Failure Reasons Breakdown</h3>
                    {runHealth.topReasons.length === 0 ? (
                      <p className="mt-4 text-sm text-[var(--color-text-muted)]">No failure reasons yet.</p>
                    ) : (
                      <div className="mt-4 space-y-3">
                        {runHealth.topReasons.map((entry) => (
                          <div key={entry.reason}>
                            <div className="mb-1 flex items-center justify-between text-sm">
                              <span className="truncate pr-3">{entry.reason}</span>
                              <span className="text-[var(--color-text-muted)]">
                                {entry.count} ({entry.percent.toFixed(0)}%)
                              </span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
                              <div
                                className="h-full bg-[var(--color-accent)]"
                                style={{ width: `${Math.min(entry.percent, 100)}%` }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
                    <h3 className="text-xl font-bold">Recent Failures</h3>
                    {runHealth.recentFailures.length === 0 ? (
                      <p className="mt-4 text-sm text-[var(--color-text-muted)]">
                        No recent failures in this organization.
                      </p>
                    ) : (
                      <div className="mt-4 space-y-3">
                        {runHealth.recentFailures.map((failure) => (
                          <article
                            key={failure.taskId}
                            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-3"
                          >
                            <p className="text-sm font-medium leading-relaxed">{failure.reason}</p>
                            <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                              Task {failure.taskId.slice(0, 12)} ·{" "}
                              {failure.createdAt
                                ? new Date(failure.createdAt).toLocaleString()
                                : "No timestamp"}
                            </p>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "governance" && selectedOrgId && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="text-2xl font-bold">Governance Controls</h2>
                {governance && (
                  <div className="text-xs text-[var(--color-text-muted)]">
                    Policy v{governance.policy_version ?? 0}
                    {governance.previous_policy_version
                      ? ` (prev v${governance.previous_policy_version})`
                      : ""}
                  </div>
                )}
              </div>

              {orgLoading ? (
                <p className="text-sm text-[var(--color-text-muted)]">Loading governance...</p>
              ) : !governance ? (
                <p className="text-sm text-[var(--color-text-muted)]">Governance is unavailable for this org.</p>
              ) : (
                <div className="space-y-5">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <p className="text-xs uppercase tracking-[0.12em] text-[var(--color-text-dim)]">
                        Audit Events
                      </p>
                      <p className="mt-2 text-2xl font-extrabold">
                        {formatNumber(governanceHistory?.stats?.audit_events ?? 0)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <p className="text-xs uppercase tracking-[0.12em] text-[var(--color-text-dim)]">
                        Circuit Trips
                      </p>
                      <p className="mt-2 text-2xl font-extrabold text-[var(--color-danger)]">
                        {formatNumber(governanceHistory?.stats?.circuit_breaker_trips ?? 0)}
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-semibold">Preset</label>
                    <select
                      value={govPreset}
                      onChange={(event) => setGovPreset(event.target.value as Governance["preset"])}
                      className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                    >
                      <option value="conservative">Conservative</option>
                      <option value="balanced">Balanced</option>
                      <option value="aggressive">Aggressive</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <label className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <span className="block text-xs uppercase tracking-[0.12em] text-[var(--color-text-dim)]">
                        Audit Frequency
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={govAuditFrequency}
                        onChange={(event) => setGovAuditFrequency(Number(event.target.value))}
                        className="mt-3 w-full"
                      />
                      <span className="mt-2 block text-sm">{Math.round(govAuditFrequency * 100)}%</span>
                    </label>

                    <label className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <span className="block text-xs uppercase tracking-[0.12em] text-[var(--color-text-dim)]">
                        Tax Rate
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={0.5}
                        step={0.01}
                        value={govTaxRate}
                        onChange={(event) => setGovTaxRate(Number(event.target.value))}
                        className="mt-3 w-full"
                      />
                      <span className="mt-2 block text-sm">{Math.round(govTaxRate * 100)}%</span>
                    </label>
                  </div>

                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                    <label className="flex items-center gap-3 text-sm font-semibold">
                      <input
                        type="checkbox"
                        checked={govCircuitBreakerEnabled}
                        onChange={(event) => setGovCircuitBreakerEnabled(event.target.checked)}
                      />
                      Circuit Breaker Enabled
                    </label>
                    <div className="mt-4">
                      <label className="mb-2 block text-xs uppercase tracking-[0.12em] text-[var(--color-text-dim)]">
                        Threshold
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={govCircuitBreakerThreshold}
                        onChange={(event) =>
                          setGovCircuitBreakerThreshold(
                            Math.min(10, Math.max(1, Number(event.target.value) || 1))
                          )
                        }
                        className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Rollout: {governance.rollout?.status || "active"}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        void handleGovernanceUpdate();
                      }}
                      disabled={govUpdating}
                      className="rounded-lg bg-[var(--color-accent)] px-5 py-2 text-sm font-semibold text-black disabled:opacity-50"
                    >
                      {govUpdating ? "Applying..." : "Apply Governance Changes"}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <h3 className="text-lg font-bold">Audits Timeline</h3>
                      {orgLoading ? (
                        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                          Loading audits timeline...
                        </p>
                      ) : (governanceHistory?.audit_timeline?.length ?? 0) === 0 ? (
                        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                          No audit events for this organization yet.
                        </p>
                      ) : (
                        <div className="mt-4 space-y-3">
                          {governanceHistory?.audit_timeline.map((event, index) => (
                            <article
                              key={`${event.timestamp ?? "na"}-${event.action ?? "action"}-${index}`}
                              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3"
                            >
                              <p className="text-sm font-semibold">{event.action || "audit.event"}</p>
                              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                                {event.timestamp
                                  ? new Date(event.timestamp * 1000).toLocaleString()
                                  : "No timestamp"}{" "}
                                · {event.actor || "system"}
                              </p>
                              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                                {event.summary || `${event.resource || "resource"} ${event.resource_id || ""}`}
                              </p>
                            </article>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                      <h3 className="text-lg font-bold">Circuit-Breaker History</h3>
                      {orgLoading ? (
                        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                          Loading circuit-breaker history...
                        </p>
                      ) : (governanceHistory?.circuit_breaker_history?.length ?? 0) === 0 ? (
                        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                          No circuit-breaker trips recorded for this organization.
                        </p>
                      ) : (
                        <div className="mt-4 space-y-3">
                          {governanceHistory?.circuit_breaker_history.map((event, index) => (
                            <article
                              key={`${event.timestamp ?? "na"}-${event.agent_id ?? "agent"}-${index}`}
                              className="rounded-lg border border-[var(--color-danger)]/25 bg-[var(--color-danger)]/5 p-3"
                            >
                              <p className="text-sm font-semibold text-[var(--color-danger)]">
                                {event.agent_id || "Unknown agent"} tripped at threshold{" "}
                                {event.threshold ?? "n/a"}
                              </p>
                              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                                {event.timestamp
                                  ? new Date(event.timestamp * 1000).toLocaleString()
                                  : "No timestamp"}{" "}
                                · streak {event.consecutive_failures ?? "n/a"}
                              </p>
                              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                                Task {event.task_id?.slice(0, 12) || "n/a"} ·{" "}
                                {event.reason || "No reason provided"}
                              </p>
                            </article>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {activeTab === "settings" && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">Account</h2>
              {tenantInfo ? (
                <div className="mt-4 space-y-3 text-sm">
                  <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                    <span className="text-[var(--color-text-muted)]">Tenant ID</span>
                    <span className="font-mono text-xs">{tenantInfo.tenant_id}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                    <span className="text-[var(--color-text-muted)]">Name</span>
                    <span>{tenantInfo.name}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                    <span className="text-[var(--color-text-muted)]">Tier</span>
                    <span className="rounded-md bg-[var(--color-accent)]/15 px-2 py-0.5 text-xs font-semibold text-[var(--color-accent)]">
                      {tenantInfo.tier}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                    <span className="text-[var(--color-text-muted)]">Billing</span>
                    <span>{tenantInfo.billing_status || "Not configured"}</span>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-sm text-[var(--color-text-muted)]">
                  Loading account info...
                </p>
              )}
            </div>

            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-6">
              <h2 className="text-2xl font-bold">API Key</h2>
              <p className="mt-2 text-sm text-[var(--color-text-muted)]">
                Your API key authenticates requests to the gateway. Rotating generates a
                new key and <strong>immediately revokes</strong> the old one.
              </p>

              {(tenantInfo as TenantInfo & { key_prefix?: string })?.key_prefix && !newApiKey && (
                <div className="mt-4 flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                  <span className="text-sm text-[var(--color-text-muted)]">Current key</span>
                  <code className="rounded bg-[var(--color-bg-card)] px-2 py-1 font-mono text-sm">
                    {(tenantInfo as TenantInfo & { key_prefix?: string }).key_prefix}••••••••
                  </code>
                </div>
              )}

              {newApiKey && (
                <div className="mt-4 rounded-xl border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 p-4">
                  <p className="text-sm font-semibold text-[var(--color-success)]">
                    New API key generated
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    Copy this key now. It will not be shown again.
                  </p>
                  <div className="mt-3 flex items-center gap-2">
                    <code className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 font-mono text-sm break-all">
                      {newApiKey}
                    </code>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(newApiKey);
                        setKeyCopied(true);
                        setTimeout(() => setKeyCopied(false), 2000);
                      }}
                      className="shrink-0 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-bright)] transition-colors"
                    >
                      {keyCopied ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
              )}

              {rotateError && (
                <div className="mt-4 rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-4 py-3 text-sm text-[var(--color-danger)]">
                  {rotateError}
                </div>
              )}

              {!showRotateConfirm ? (
                <button
                  type="button"
                  onClick={() => {
                    setShowRotateConfirm(true);
                    setRotateError("");
                    setNewApiKey(null);
                  }}
                  className="mt-4 rounded-lg border border-[var(--color-danger)]/40 px-4 py-2 text-sm font-semibold text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 transition-colors"
                >
                  Rotate API Key
                </button>
              ) : (
                <div className="mt-4 rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 p-4">
                  <p className="text-sm font-semibold text-[var(--color-danger)]">
                    Are you sure?
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                    Your current API key will stop working immediately. Any agents or
                    scripts using it will lose access until updated with the new key.
                  </p>
                  <div className="mt-3 flex gap-3">
                    <button
                      type="button"
                      disabled={rotatingKey}
                      onClick={async () => {
                        setRotatingKey(true);
                        setRotateError("");
                        try {
                          const res = await fetch("/api/dashboard/tenants/me/rotate-key", {
                            method: "POST",
                          });
                          if (!res.ok) {
                            const body = await res.json().catch(() => ({}));
                            throw new Error(
                              body.detail || `Rotation failed (${res.status})`
                            );
                          }
                          const data = await res.json();
                          setNewApiKey(data.api_key);
                          setShowRotateConfirm(false);
                          // Refresh tenant info to get updated key_prefix
                          const meRes = await fetch("/api/dashboard/tenants/me");
                          if (meRes.ok) {
                            const meData = await meRes.json();
                            setTenantInfo(meData);
                          }
                        } catch (err) {
                          setRotateError(
                            err instanceof Error ? err.message : "Key rotation failed"
                          );
                        } finally {
                          setRotatingKey(false);
                        }
                      }}
                      className="rounded-lg bg-[var(--color-danger)] px-4 py-2 text-sm font-semibold text-white hover:brightness-110 transition-all disabled:opacity-50"
                    >
                      {rotatingKey ? "Rotating..." : "Yes, rotate key"}
                    </button>
                    <button
                      type="button"
                      disabled={rotatingKey}
                      onClick={() => setShowRotateConfirm(false)}
                      className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
