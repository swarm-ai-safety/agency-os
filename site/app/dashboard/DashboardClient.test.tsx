import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardClient from "./DashboardClient";

let searchParamsValue = "";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));

function unauthorizedJsonResponse(): Response {
  return new Response(JSON.stringify({ detail: "Unauthorized" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

describe("DashboardClient auth UX", () => {
  beforeEach(() => {
    searchParamsValue = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => unauthorizedJsonResponse()) as unknown as typeof fetch
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("hides OIDC sign-in CTA when OIDC is unavailable", async () => {
    searchParamsValue = "auth_error=oidc_unavailable";

    render(<DashboardClient />);

    expect(
      await screen.findByText(/Single sign-on is not enabled for this deployment/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign in with OIDC" })).toBeNull();
    expect(
      screen.getByText(/Sign-in is temporarily unavailable until OIDC is configured/i)
    ).toBeInTheDocument();
  });

  it("shows OIDC sign-in CTA when auth is required without OIDC config errors", async () => {
    render(<DashboardClient />);

    expect(
      await screen.findByRole("link", { name: "Sign in with OIDC" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Your session expired or is missing. Sign in to continue/i)
    ).toBeInTheDocument();
  });

  it("does not crash when dashboard numeric fields are malformed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: "not-a-number",
              total_tokens_in: null,
              total_tokens_out: "7",
              total_customer_cost: undefined,
              avg_latency_ms: "bad",
              cache_hits: "0",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: "0",
              cache_hits: "0",
              cache_savings_usd: null,
              smart_routed: "0",
              total_cost_usd: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: "bad",
              total_spent_usd: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
  });

  it("does not crash when org-scoped payloads are malformed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              total_tokens_in: 0,
              total_tokens_out: 0,
              total_customer_cost: 0,
              avg_latency_ms: 0,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(
            JSON.stringify([
              {
                org_id: "org-1",
                name: "Org One",
                status: "active",
                agent_count: 0,
                created_at: "2026-03-01T00:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 0,
              total_spent_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/agents")) {
          return new Response(JSON.stringify({ not: "an-array" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/tasks")) {
          return new Response(JSON.stringify({ also: "bad" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance/history")) {
          return new Response(JSON.stringify({ audit_timeline: {}, circuit_breaker_history: {} }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance")) {
          return new Response(JSON.stringify({}), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
  });

  it("renders object-like task descriptions without throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              total_tokens_in: 0,
              total_tokens_out: 0,
              total_customer_cost: 0,
              avg_latency_ms: 0,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(
            JSON.stringify([
              {
                org_id: "org-1",
                name: "Org One",
                status: "active",
                agent_count: 1,
                created_at: "2026-03-01T00:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 0,
              total_spent_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/agents")) {
          return new Response(
            JSON.stringify([
              {
                agent_id: "agent-1",
                name: "Agent One",
                balance: 0,
                reputation: 0,
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/tasks")) {
          return new Response(
            JSON.stringify([
              {
                task_id: "task-1",
                description: { type: "string", loc: ["body"], msg: "Bad input", input: {} },
                status: "failed",
                governance_preset: "balanced",
                assigned_to: "agent-1",
                created_at: "2026-03-01T00:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance/history")) {
          return new Response(
            JSON.stringify({ audit_timeline: [], circuit_breaker_history: [] }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance")) {
          return new Response(
            JSON.stringify({
              preset: "balanced",
              overrides: { audit_frequency: 0.1, tax_rate: 0.05, circuit_breaker: { enabled: true, threshold: 3 } },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
  });

  it("renders timeline data in the timeline tab", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 1,
              total_tokens_in: 10,
              total_tokens_out: 20,
              total_customer_cost: 0.01,
              avg_latency_ms: 100,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 1,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0.01,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(
            JSON.stringify([
              {
                org_id: "org-1",
                name: "Org One",
                status: "active",
                agent_count: 1,
                created_at: "2026-03-01T00:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 0,
              total_spent_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/agents")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/tasks")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance/history")) {
          return new Response(
            JSON.stringify({ audit_timeline: [], circuit_breaker_history: [] }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance")) {
          return new Response(
            JSON.stringify({
              preset: "balanced",
              overrides: {
                audit_frequency: 0.1,
                tax_rate: 0.05,
                circuit_breaker: { enabled: true, threshold: 3 },
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline/replay")) {
          return new Response(
            JSON.stringify({
              org_id: "org-1",
              duration_seconds: 6,
              replay_duration_seconds: 3,
              events: [
                {
                  event_type: "org.started",
                  title: "Org started",
                  agent_name: "System",
                  timestamp: 1700000000,
                },
                {
                  event_type: "task.completed",
                  title: "Task done",
                  agent_name: "Agent One",
                  timestamp: 1700000006,
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline?")) {
          return new Response(
            JSON.stringify({
              count: 2,
              events: [
                {
                  event_type: "org.started",
                  title: "Org started",
                  agent_name: "System",
                  timestamp: 1700000000,
                },
                {
                  event_type: "task.completed",
                  title: "Task done",
                  agent_name: "Agent One",
                  timestamp: 1700000006,
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);

    const timelineTab = await screen.findByRole("button", { name: "Timeline" });
    fireEvent.click(timelineTab);

    expect(await screen.findByText("Organization Timeline")).toBeInTheDocument();
    expect(screen.getByText("Task done")).toBeInTheDocument();
  });

  it("shows empty onboarding state with create organization CTA", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              total_tokens_in: 0,
              total_tokens_out: 0,
              total_customer_cost: 0,
              avg_latency_ms: 0,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 0,
              total_spent_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);

    expect(await screen.findByText("Onboarding Checklist")).toBeInTheDocument();
    expect(screen.getAllByText("No organizations yet").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Create organization" })).toBeInTheDocument();
    expect(screen.getByText("Progress: 1/4 complete")).toBeInTheDocument();
  });

  it("updates onboarding progress for partial and complete live states", async () => {
    const createFetch = (opts: {
      hasTask: boolean;
      billingConfigured: boolean;
    }): typeof fetch =>
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 1,
              total_tokens_in: 10,
              total_tokens_out: 20,
              total_customer_cost: 0.01,
              avg_latency_ms: 100,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 1,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0.01,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/tenants/me/organizations")) {
          return new Response(
            JSON.stringify([
              {
                org_id: "org-1",
                name: "Org One",
                status: "active",
                agent_count: 1,
                created_at: "2026-03-01T00:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 0,
              total_spent_usd: 0,
              stripe_customer_id: opts.billingConfigured ? "cus_123" : null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/agents")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/tasks")) {
          return new Response(
            JSON.stringify(
              opts.hasTask
                ? [
                    {
                      task_id: "task-1",
                      description: "First task",
                      status: "completed",
                      governance_preset: "balanced",
                      assigned_to: "agent-1",
                      created_at: "2026-03-01T00:00:00Z",
                    },
                  ]
                : []
            ),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance/history")) {
          return new Response(
            JSON.stringify({ audit_timeline: [], circuit_breaker_history: [] }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance")) {
          return new Response(
            JSON.stringify({
              preset: "balanced",
              overrides: {
                audit_frequency: 0.1,
                tax_rate: 0.05,
                circuit_breaker: { enabled: true, threshold: 3 },
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline/replay")) {
          return new Response(JSON.stringify({ events: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline?")) {
          return new Response(JSON.stringify({ count: 0, events: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch;

    vi.stubGlobal("fetch", createFetch({ hasTask: false, billingConfigured: false }));
    const { unmount } = render(<DashboardClient />);

    expect(await screen.findByText("Onboarding Checklist")).toBeInTheDocument();
    expect(screen.getByText("Progress: 2/4 complete")).toBeInTheDocument();

    unmount();
    vi.stubGlobal("fetch", createFetch({ hasTask: true, billingConfigured: true }));
    render(<DashboardClient />);

    expect(await screen.findByText("Progress: 4/4 complete")).toBeInTheDocument();
  });
  it("creates organization and emits telemetry events", async () => {
    let organizations: Array<{
      org_id: string;
      name: string;
      status: string;
      agent_count: number;
      created_at: string;
    }> = [];
    const plausible = vi.fn();
    (window as Window & { plausible?: (name: string, payload?: unknown) => void }).plausible =
      plausible;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              total_tokens_in: 0,
              total_tokens_out: 0,
              total_customer_cost: 0,
              avg_latency_ms: 0,
              cache_hits: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(
            JSON.stringify({
              total_requests: 0,
              cache_hits: 0,
              cache_savings_usd: 0,
              smart_routed: 0,
              total_cost_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/dashboard/tenants/me/organizations")) {
          return new Response(JSON.stringify(organizations), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/dashboard/tenants/me")) {
          return new Response(
            JSON.stringify({
              tenant_id: "tenant-1",
              name: "Tenant 1",
              tier: "free",
              budget_limit_usd: 100,
              total_spent_usd: 0,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.endsWith("/api/dashboard/orgs") && init?.method === "POST") {
          organizations = [
            {
              org_id: "org-1",
              name: "Org One",
              status: "running",
              agent_count: 4,
              created_at: "2026-03-01T00:00:00Z",
            },
          ];
          return new Response(JSON.stringify({ org_id: "org-1", status: "running" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/agents")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/tasks")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance/history")) {
          return new Response(
            JSON.stringify({ audit_timeline: [], circuit_breaker_history: [] }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/governance")) {
          return new Response(
            JSON.stringify({
              preset: "balanced",
              overrides: { audit_frequency: 0.1, tax_rate: 0.05, circuit_breaker: { enabled: true, threshold: 3 } },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          );
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline/replay")) {
          return new Response(JSON.stringify({ events: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/dashboard/orgs/org-1/timeline?")) {
          return new Response(JSON.stringify({ count: 0, events: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);
    fireEvent.click(await screen.findByRole("button", { name: "Create organization" }));

    expect(await screen.findByText("Org One (running)")).toBeInTheDocument();
    expect(plausible).toHaveBeenCalledWith("org_create_cta_clicked", expect.anything());
    expect(plausible).toHaveBeenCalledWith("org_create_succeeded", expect.anything());
  });

  it("surfaces create-organization failure and emits failure telemetry", async () => {
    const plausible = vi.fn();
    (window as Window & { plausible?: (name: string, payload?: unknown) => void }).plausible =
      plausible;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/dashboard/gateway/stats")) {
          return new Response(JSON.stringify({ total_requests: 0, total_tokens_in: 0, total_tokens_out: 0, total_customer_cost: 0, avg_latency_ms: 0, cache_hits: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/dashboard/gateway/savings")) {
          return new Response(JSON.stringify({ total_requests: 0, cache_hits: 0, cache_savings_usd: 0, smart_routed: 0, total_cost_usd: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/dashboard/gateway/requests")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/dashboard/gateway/top-models")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/api/dashboard/tenants/me/organizations")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/api/dashboard/tenants/me")) {
          return new Response(JSON.stringify({ tenant_id: "tenant-1", name: "Tenant 1", tier: "free", budget_limit_usd: 100, total_spent_usd: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/api/dashboard/orgs") && init?.method === "POST") {
          return new Response(JSON.stringify({ detail: "Billing required" }), {
            status: 402,
            headers: { "Content-Type": "application/json" },
          });
        }
        return unauthorizedJsonResponse();
      }) as unknown as typeof fetch
    );

    render(<DashboardClient />);
    fireEvent.click(await screen.findByRole("button", { name: "Create organization" }));

    expect(await screen.findByText("Billing required")).toBeInTheDocument();
    expect(plausible).toHaveBeenCalledWith("org_create_failed", expect.anything());
  });

  it("starts billing setup from dashboard when tenant has no Stripe customer", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/dashboard/gateway/stats")) {
        return new Response(JSON.stringify({ total_requests: 0, total_tokens_in: 0, total_tokens_out: 0, total_customer_cost: 0, avg_latency_ms: 0, cache_hits: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/savings")) {
        return new Response(JSON.stringify({ total_requests: 0, cache_hits: 0, cache_savings_usd: 0, smart_routed: 0, total_cost_usd: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/requests")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/top-models")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me/organizations")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me")) {
        return new Response(JSON.stringify({ tenant_id: "tenant-1", name: "Tenant 1", tier: "free", budget_limit_usd: 100, total_spent_usd: 0, billing_status: null, stripe_customer_id: null }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/setup-customer") && init?.method === "POST") {
        return new Response(JSON.stringify({ stripe_customer_id: "cus_123", status: "created" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/checkout") && init?.method === "POST") {
        return new Response(JSON.stringify({ checkout_url: "#billing-settings" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return unauthorizedJsonResponse();
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardClient />);
    fireEvent.click(await screen.findByRole("button", { name: "Add Billing Details" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/dashboard/billing/setup-customer")
        )
      ).toBe(true);
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/dashboard/billing/checkout")
        )
      ).toBe(true);
    });
  });

  it("uses checkout directly when tenant already has Stripe customer but inactive billing", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/dashboard/gateway/stats")) {
        return new Response(JSON.stringify({ total_requests: 0, total_tokens_in: 0, total_tokens_out: 0, total_customer_cost: 0, avg_latency_ms: 0, cache_hits: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/savings")) {
        return new Response(JSON.stringify({ total_requests: 0, cache_hits: 0, cache_savings_usd: 0, smart_routed: 0, total_cost_usd: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/requests")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/top-models")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me/organizations")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me")) {
        return new Response(JSON.stringify({ tenant_id: "tenant-1", name: "Tenant 1", tier: "free", budget_limit_usd: 100, total_spent_usd: 0, billing_status: "past_due", stripe_customer_id: "cus_123" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/checkout") && init?.method === "POST") {
        return new Response(JSON.stringify({ checkout_url: "#billing-settings" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return unauthorizedJsonResponse();
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardClient />);
    fireEvent.click(await screen.findByRole("button", { name: "Complete Billing Setup" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/dashboard/billing/checkout")
        )
      ).toBe(true);
    });
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/dashboard/billing/setup-customer")
      )
    ).toBe(false);
  });

  it("shows credit balance and starts credit top-up checkout for active billing", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/dashboard/gateway/stats")) {
        return new Response(JSON.stringify({ total_requests: 0, total_tokens_in: 0, total_tokens_out: 0, total_customer_cost: 0, avg_latency_ms: 0, cache_hits: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/savings")) {
        return new Response(JSON.stringify({ total_requests: 0, cache_hits: 0, cache_savings_usd: 0, smart_routed: 0, total_cost_usd: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/requests")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/dashboard/gateway/top-models")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me/organizations")) {
        return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/tenants/me")) {
        return new Response(JSON.stringify({ tenant_id: "tenant-1", name: "Tenant 1", tier: "paid", budget_limit_usd: 100, total_spent_usd: 0, billing_status: "active", stripe_customer_id: "cus_123" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/credit-balance-summary")) {
        return new Response(JSON.stringify({ object: "billing.credit_balance_summary", balances: [{ available_balance: { monetary: { currency: "usd", value: 2500 } } }] }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/credit-topup-config")) {
        return new Response(JSON.stringify({ enabled: true, price_id: "price_topup", amount_value: 2500, currency: "usd", name: "Buy Credits" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/credit-topup-checkout") && init?.method === "POST") {
        return new Response(JSON.stringify({ checkout_url: "#credits-checkout" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/dashboard/billing/portal") && init?.method === "POST") {
        return new Response(JSON.stringify({ portal_url: "#portal" }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return unauthorizedJsonResponse();
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardClient />);

    expect(
      await screen.findByText("Available prepaid credits: $25.0000")
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "Buy Credits" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).endsWith("/api/dashboard/billing/credit-topup-checkout") &&
            init?.method === "POST"
        )
      ).toBe(true);
    });
  });
});
