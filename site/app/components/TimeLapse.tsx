"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimelineEvent {
  event_type: string;
  title: string;
  detail?: string;
  agent_id?: string;
  agent_name?: string;
  agent_division?: string;
  agent_color?: string;
  artifact_type?: string;
  artifact_ref?: string;
  budget_snapshot?: number;
  reputation_snapshot?: number;
  timestamp: number;
  relative_time?: number;
  replay_time?: number;
  metadata?: Record<string, unknown>;
}

interface AgentInfo {
  agent_id: string;
  name: string;
  division: string;
  color: string;
}

interface ReplayData {
  org_id: string;
  events: TimelineEvent[];
  agents: AgentInfo[];
  duration_seconds: number;
  replay_duration_seconds: number;
  speed: number;
  start_timestamp: number;
  end_timestamp: number;
}

// ---------------------------------------------------------------------------
// Color mapping for agent divisions / event types
// ---------------------------------------------------------------------------

const DIVISION_COLORS: Record<string, string> = {
  engineering: "#22d3ee",
  marketing: "#f472b6",
  operations: "#fbbf24",
  design: "#a78bfa",
  product: "#4ade80",
  finance: "#fb923c",
  research: "#38bdf8",
};

const EVENT_ICONS: Record<string, string> = {
  "org.started": "\u25B6",
  "org.stopped": "\u25A0",
  "agent.joined": "\u2795",
  "agent.frozen": "\u2744",
  "agent.unfrozen": "\u2600",
  "task.submitted": "\u{1F4CB}",
  "task.bid_placed": "\u{1F4B0}",
  "task.assigned": "\u{1F3AF}",
  "task.completed": "\u2705",
  "task.failed": "\u274C",
  "budget.update": "\u{1F4B8}",
  "governance.audit": "\u{1F50D}",
  "governance.circuit_breaker": "\u26A1",
  "artifact.produced": "\u{1F4E6}",
  "workflow.started": "\u{1F680}",
  "workflow.stage_passed": "\u2705",
  "workflow.completed": "\u{1F3C1}",
};

function getAgentColor(agent?: {
  color?: string;
  division?: string;
  agent_color?: string;
  agent_division?: string;
}): string {
  if (!agent) return "#71717a";
  const colorKey = agent.color ?? agent.agent_color;
  const divisionKey = agent.division ?? agent.agent_division;
  if (colorKey && DIVISION_COLORS[colorKey]) return DIVISION_COLORS[colorKey];
  if (divisionKey && DIVISION_COLORS[divisionKey]) return DIVISION_COLORS[divisionKey];
  return "#22d3ee";
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Demo data generator (for the marketing page / when no API data available)
// ---------------------------------------------------------------------------

function generateDemoReplay(): ReplayData {
  const now = Date.now() / 1000;
  const events: TimelineEvent[] = [
    {
      event_type: "org.started",
      title: "Organization started: saas-dev-studio",
      detail: "6 agents initialized",
      timestamp: now,
      relative_time: 0,
      replay_time: 0,
    },
    {
      event_type: "agent.joined",
      title: "Product Manager joined the organization",
      agent_id: "pm-001",
      agent_name: "Product Manager",
      agent_division: "product",
      agent_color: "product",
      budget_snapshot: 100,
      timestamp: now + 1,
      relative_time: 1,
      replay_time: 1,
    },
    {
      event_type: "agent.joined",
      title: "Senior Developer joined the organization",
      agent_id: "dev-001",
      agent_name: "Senior Developer",
      agent_division: "engineering",
      agent_color: "engineering",
      budget_snapshot: 100,
      timestamp: now + 2,
      relative_time: 2,
      replay_time: 2,
    },
    {
      event_type: "agent.joined",
      title: "UI Designer joined the organization",
      agent_id: "design-001",
      agent_name: "UI Designer",
      agent_division: "design",
      agent_color: "design",
      budget_snapshot: 100,
      timestamp: now + 3,
      relative_time: 3,
      replay_time: 3,
    },
    {
      event_type: "agent.joined",
      title: "Marketing Lead joined the organization",
      agent_id: "mkt-001",
      agent_name: "Marketing Lead",
      agent_division: "marketing",
      agent_color: "marketing",
      budget_snapshot: 75,
      timestamp: now + 4,
      relative_time: 4,
      replay_time: 4,
    },
    {
      event_type: "task.submitted",
      title: "Task submitted: Write product requirements document",
      detail: "Write a comprehensive PRD for a SaaS analytics dashboard",
      timestamp: now + 8,
      relative_time: 8,
      replay_time: 8,
    },
    {
      event_type: "task.bid_placed",
      title: "Product Manager bid $10.00",
      agent_id: "pm-001",
      agent_name: "Product Manager",
      agent_division: "product",
      agent_color: "product",
      budget_snapshot: 100,
      timestamp: now + 10,
      relative_time: 10,
      replay_time: 10,
    },
    {
      event_type: "task.bid_placed",
      title: "Senior Developer bid $8.50",
      agent_id: "dev-001",
      agent_name: "Senior Developer",
      agent_division: "engineering",
      agent_color: "engineering",
      budget_snapshot: 100,
      timestamp: now + 11,
      relative_time: 11,
      replay_time: 11,
    },
    {
      event_type: "task.assigned",
      title: "Product Manager won task: Write product requirements doc",
      agent_id: "pm-001",
      agent_name: "Product Manager",
      agent_division: "product",
      agent_color: "product",
      budget_snapshot: 90,
      timestamp: now + 13,
      relative_time: 13,
      replay_time: 13,
    },
    {
      event_type: "task.completed",
      title: "Product Manager completed task",
      agent_id: "pm-001",
      agent_name: "Product Manager",
      agent_division: "product",
      agent_color: "product",
      budget_snapshot: 90,
      reputation_snapshot: 1.1,
      artifact_type: "document",
      artifact_ref: "prd-v1.md",
      timestamp: now + 30,
      relative_time: 30,
      replay_time: 30,
    },
    {
      event_type: "task.submitted",
      title: "Task submitted: Design dashboard wireframes",
      detail: "Create wireframes for the analytics dashboard UI",
      timestamp: now + 32,
      relative_time: 32,
      replay_time: 32,
    },
    {
      event_type: "task.assigned",
      title: "UI Designer won task: Design dashboard wireframes",
      agent_id: "design-001",
      agent_name: "UI Designer",
      agent_division: "design",
      agent_color: "design",
      budget_snapshot: 85,
      timestamp: now + 35,
      relative_time: 35,
      replay_time: 35,
    },
    {
      event_type: "task.submitted",
      title: "Task submitted: Build REST API for analytics endpoints",
      detail: "Create the backend API with auth, data ingestion, and query endpoints",
      timestamp: now + 38,
      relative_time: 38,
      replay_time: 38,
    },
    {
      event_type: "task.assigned",
      title: "Senior Developer won task: Build REST API",
      agent_id: "dev-001",
      agent_name: "Senior Developer",
      agent_division: "engineering",
      agent_color: "engineering",
      budget_snapshot: 85,
      timestamp: now + 40,
      relative_time: 40,
      replay_time: 40,
    },
    {
      event_type: "task.completed",
      title: "UI Designer completed task",
      agent_id: "design-001",
      agent_name: "UI Designer",
      agent_division: "design",
      agent_color: "design",
      budget_snapshot: 82,
      reputation_snapshot: 1.15,
      artifact_type: "wireframes",
      artifact_ref: "wireframes.png",
      timestamp: now + 55,
      relative_time: 55,
      replay_time: 55,
    },
    {
      event_type: "governance.audit",
      title: "Audit passed: Senior Developer",
      agent_id: "dev-001",
      agent_name: "Senior Developer",
      agent_division: "engineering",
      agent_color: "engineering",
      reputation_snapshot: 1.05,
      timestamp: now + 60,
      relative_time: 60,
      replay_time: 60,
    },
    {
      event_type: "task.completed",
      title: "Senior Developer completed task",
      agent_id: "dev-001",
      agent_name: "Senior Developer",
      agent_division: "engineering",
      agent_color: "engineering",
      budget_snapshot: 78,
      reputation_snapshot: 1.2,
      artifact_type: "code",
      artifact_ref: "api/endpoints.py",
      timestamp: now + 72,
      relative_time: 72,
      replay_time: 72,
    },
    {
      event_type: "task.submitted",
      title: "Task submitted: Launch SEO campaign for landing page",
      detail: "Create and deploy SEO-optimized content strategy",
      timestamp: now + 75,
      relative_time: 75,
      replay_time: 75,
    },
    {
      event_type: "task.assigned",
      title: "Marketing Lead won task: Launch SEO campaign",
      agent_id: "mkt-001",
      agent_name: "Marketing Lead",
      agent_division: "marketing",
      agent_color: "marketing",
      budget_snapshot: 68,
      timestamp: now + 78,
      relative_time: 78,
      replay_time: 78,
    },
    {
      event_type: "task.completed",
      title: "Marketing Lead completed task",
      agent_id: "mkt-001",
      agent_name: "Marketing Lead",
      agent_division: "marketing",
      agent_color: "marketing",
      budget_snapshot: 62,
      reputation_snapshot: 1.1,
      artifact_type: "content",
      artifact_ref: "seo-strategy.md",
      timestamp: now + 95,
      relative_time: 95,
      replay_time: 95,
    },
  ];

  return {
    org_id: "demo-org",
    events,
    agents: [
      { agent_id: "pm-001", name: "Product Manager", division: "product", color: "product" },
      { agent_id: "dev-001", name: "Senior Developer", division: "engineering", color: "engineering" },
      { agent_id: "design-001", name: "UI Designer", division: "design", color: "design" },
      { agent_id: "mkt-001", name: "Marketing Lead", division: "marketing", color: "marketing" },
    ],
    duration_seconds: 95,
    replay_duration_seconds: 95,
    speed: 1.0,
    start_timestamp: now,
    end_timestamp: now + 95,
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AgentBadge({ agent }: { agent?: Partial<AgentInfo> }) {
  if (!agent?.name) return null;
  const color = getAgentColor(agent);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
      style={{ backgroundColor: `${color}15`, color, border: `1px solid ${color}30` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {agent.name}
    </span>
  );
}

function EventRow({
  event,
  isActive,
  elapsedTime,
}: {
  event: TimelineEvent;
  isActive: boolean;
  elapsedTime: number;
}) {
  const icon = EVENT_ICONS[event.event_type] || "\u2022";
  const relativeTime = event.relative_time ?? 0;
  const agentColor = getAgentColor(event);

  return (
    <div
      className={`
        flex items-start gap-3 rounded-lg border px-4 py-3 transition-all duration-300
        ${
          isActive
            ? "border-[var(--color-accent)]/40 bg-[var(--color-accent)]/5 shadow-[0_0_20px_rgba(34,211,238,0.08)]"
            : "border-[var(--color-border)] bg-[var(--color-bg-card)]"
        }
        ${relativeTime > elapsedTime ? "opacity-30" : "opacity-100"}
      `}
    >
      {/* Timestamp */}
      <div className="flex-shrink-0 pt-0.5 font-mono text-xs text-[var(--color-text-dim)] w-12">
        {formatTime(relativeTime)}
      </div>

      {/* Icon */}
      <div className="flex-shrink-0 text-base pt-0.5">{icon}</div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-[var(--color-text)]">
            {event.title}
          </span>
          {event.agent_name && (
            <AgentBadge agent={event} />
          )}
        </div>
        {event.detail && event.event_type !== event.detail && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)] line-clamp-2">
            {event.detail}
          </p>
        )}
        {/* Artifact indicator */}
        {event.artifact_type && (
          <div className="mt-1.5 inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-0.5 text-xs text-[var(--color-text-muted)]">
            <span>{"\u{1F4CE}"}</span>
            <span>{event.artifact_ref || event.artifact_type}</span>
          </div>
        )}
        {/* Budget/reputation snapshot */}
        {(event.budget_snapshot != null || event.reputation_snapshot != null) && (
          <div className="mt-1 flex gap-3 text-xs text-[var(--color-text-dim)]">
            {event.budget_snapshot != null && (
              <span>Budget: ${event.budget_snapshot.toFixed(0)}</span>
            )}
            {event.reputation_snapshot != null && (
              <span>Rep: {event.reputation_snapshot.toFixed(2)}</span>
            )}
          </div>
        )}
      </div>

      {/* Timeline connector dot */}
      <div
        className="flex-shrink-0 mt-2 h-2 w-2 rounded-full"
        style={{
          backgroundColor: relativeTime <= elapsedTime ? agentColor : "#3f3f46",
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TimeLapse({
  replayData,
  autoPlay = true,
}: {
  replayData?: ReplayData;
  autoPlay?: boolean;
}) {
  const data = replayData || generateDemoReplay();
  const [isPlaying, setIsPlaying] = useState(autoPlay);
  const [elapsed, setElapsed] = useState(0);
  const [speed, setSpeed] = useState(data.speed);
  const [activeEventIndex, setActiveEventIndex] = useState(-1);
  const timelineRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const totalDuration = data.duration_seconds;

  // Playback loop
  useEffect(() => {
    if (!isPlaying) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    intervalRef.current = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.1 * speed;
        if (next >= totalDuration) {
          setIsPlaying(false);
          return totalDuration;
        }
        return next;
      });
    }, 100);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, speed, totalDuration]);

  // Update active event index based on elapsed time
  useEffect(() => {
    let idx = -1;
    for (let i = data.events.length - 1; i >= 0; i--) {
      if ((data.events[i].relative_time ?? 0) <= elapsed) {
        idx = i;
        break;
      }
    }
    setActiveEventIndex(idx);
  }, [elapsed, data.events]);

  // Auto-scroll to active event
  useEffect(() => {
    if (activeEventIndex >= 0 && timelineRef.current) {
      const children = timelineRef.current.children;
      if (children[activeEventIndex]) {
        children[activeEventIndex].scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      }
    }
  }, [activeEventIndex]);

  const handleRestart = useCallback(() => {
    setElapsed(0);
    setActiveEventIndex(-1);
    setIsPlaying(true);
  }, []);

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      setElapsed(pct * totalDuration);
    },
    [totalDuration]
  );

  const progress = totalDuration > 0 ? (elapsed / totalDuration) * 100 : 0;
  const visibleEvents = data.events.filter(
    (ev) => (ev.relative_time ?? 0) <= elapsed
  );

  // Agent activity summary (live org chart)
  const agentActivity: Record<string, { tasks: number; latestEvent: string }> = {};
  for (const ev of visibleEvents) {
    if (ev.agent_id) {
      if (!agentActivity[ev.agent_id]) {
        agentActivity[ev.agent_id] = { tasks: 0, latestEvent: "" };
      }
      agentActivity[ev.agent_id].latestEvent = ev.event_type;
      if (ev.event_type === "task.completed") {
        agentActivity[ev.agent_id].tasks += 1;
      }
    }
  }

  return (
    <div className="w-full max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6 text-center">
        <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
          Watch AI Agents <span className="text-[var(--color-accent)]">Build</span>
        </h2>
        <p className="mt-2 text-[var(--color-text-muted)]">
          A real-time time-lapse of an autonomous AI company at work
        </p>
      </div>

      {/* Agent org chart */}
      <div className="mb-4 flex flex-wrap gap-2 justify-center">
        {data.agents.map((agent) => {
          const color = getAgentColor(agent);
          const activity = agentActivity[agent.agent_id];
          const isWorking =
            activity?.latestEvent === "task.assigned" ||
            activity?.latestEvent === "task.bid_placed";
          return (
            <div
              key={agent.agent_id}
              className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-all"
              style={{
                borderColor: activity ? `${color}40` : "#27272a",
                backgroundColor: activity ? `${color}08` : "transparent",
              }}
            >
              <span
                className={`h-2 w-2 rounded-full ${isWorking ? "animate-pulse" : ""}`}
                style={{ backgroundColor: color }}
              />
              <span className="font-medium" style={{ color }}>
                {agent.name}
              </span>
              {activity && (
                <span className="text-[var(--color-text-dim)]">
                  {activity.tasks} tasks
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
        <div className="flex items-center gap-3">
          {/* Play/Pause */}
          <button
            onClick={() => {
              if (elapsed >= totalDuration) handleRestart();
              else setIsPlaying(!isPlaying);
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-accent)] hover:bg-[var(--color-bg-card-hover)] transition-colors"
          >
            {isPlaying ? "\u23F8" : elapsed >= totalDuration ? "\u21BA" : "\u25B6"}
          </button>

          {/* Seek bar */}
          <div
            className="relative flex-1 h-2 rounded-full bg-[var(--color-bg)] cursor-pointer group"
            onClick={handleSeek}
          >
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-[var(--color-accent-dim)] to-[var(--color-accent)] transition-all duration-100"
              style={{ width: `${progress}%` }}
            />
            <div
              className="absolute top-1/2 -translate-y-1/2 h-3 w-3 rounded-full bg-[var(--color-accent)] shadow-[0_0_8px_rgba(34,211,238,0.4)] opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ left: `${progress}%` }}
            />
          </div>

          {/* Time display */}
          <span className="font-mono text-xs text-[var(--color-text-muted)] w-20 text-right">
            {formatTime(elapsed)} / {formatTime(totalDuration)}
          </span>

          {/* Speed control */}
          <div className="flex items-center gap-1">
            {[1, 2, 5, 10].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`rounded px-1.5 py-0.5 text-xs font-mono transition-colors ${
                  speed === s
                    ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                    : "text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Timeline events */}
      <div
        ref={timelineRef}
        className="space-y-2 max-h-[500px] overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 scroll-smooth"
      >
        {data.events.length === 0 ? (
          <div className="py-12 text-center text-[var(--color-text-dim)]">
            No events yet. Start an organization to see the time-lapse.
          </div>
        ) : (
          data.events.map((event, idx) => (
            <EventRow
              key={`${event.timestamp}-${idx}`}
              event={event}
              isActive={idx === activeEventIndex}
              elapsedTime={elapsed}
            />
          ))
        )}
      </div>

      {/* Stats footer */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-6 text-xs text-[var(--color-text-dim)]">
        <span>{visibleEvents.length} / {data.events.length} events</span>
        <span>{data.agents.length} agents</span>
        <span>{formatTime(totalDuration)} total runtime</span>
        <span>
          {Object.values(agentActivity).reduce((sum, a) => sum + a.tasks, 0)} tasks
          completed
        </span>
      </div>
    </div>
  );
}
