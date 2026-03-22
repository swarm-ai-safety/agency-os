export type ModelPricing = {
  name: string;
  input: number;
  output: number;
  provider: string;
};

export const models: ModelPricing[] = [
  { name: "GPT-4.1 Nano", input: 0.13, output: 0.52, provider: "OpenAI" },
  { name: "GPT-4.1 Mini", input: 0.52, output: 2.08, provider: "OpenAI" },
  { name: "GPT-4o Mini", input: 0.26, output: 1.01, provider: "OpenAI" },
  { name: "GPT-4o", input: 3.25, output: 13.0, provider: "OpenAI" },
  { name: "GPT-4.1", input: 2.60, output: 10.4, provider: "OpenAI" },
  { name: "Claude Haiku 3.5", input: 1.04, output: 5.20, provider: "Anthropic" },
  { name: "Claude Haiku 4.5", input: 1.30, output: 6.50, provider: "Anthropic" },
  { name: "Claude Sonnet 4", input: 3.90, output: 19.5, provider: "Anthropic" },
  { name: "Claude Sonnet 4.5", input: 3.90, output: 19.5, provider: "Anthropic" },
  { name: "Claude Sonnet 4.6", input: 3.90, output: 19.5, provider: "Anthropic" },
  { name: "Claude Opus 4", input: 19.5, output: 97.5, provider: "Anthropic" },
  { name: "Claude Opus 4.5", input: 6.50, output: 32.5, provider: "Anthropic" },
  { name: "Claude Opus 4.6", input: 6.50, output: 32.5, provider: "Anthropic" },
];

const directCosts: Record<string, { input: number; output: number }> = {
  "GPT-4.1 Nano": { input: 0.10, output: 0.40 },
  "GPT-4.1 Mini": { input: 0.40, output: 1.60 },
  "GPT-4o Mini": { input: 0.15, output: 0.60 },
  "GPT-4o": { input: 2.50, output: 10.0 },
  "GPT-4.1": { input: 2.00, output: 8.00 },
  "Claude Haiku 3.5": { input: 0.80, output: 4.00 },
  "Claude Haiku 4.5": { input: 1.00, output: 5.00 },
  "Claude Sonnet 4": { input: 3.00, output: 15.0 },
  "Claude Sonnet 4.5": { input: 3.00, output: 15.0 },
  "Claude Sonnet 4.6": { input: 3.00, output: 15.0 },
  "Claude Opus 4": { input: 15.0, output: 75.0 },
  "Claude Opus 4.5": { input: 5.00, output: 25.0 },
  "Claude Opus 4.6": { input: 5.00, output: 25.0 },
};

export function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toString();
}

export function fmtDollars(n: number): string {
  return n < 0.01 && n > 0
    ? `$${n.toFixed(3)}`
    : n >= 1000
      ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${n.toFixed(2)}`;
}

export function calcSmartRoutingCost(tokens: number): { agencyOs: number; label: string } {
  const input = tokens / 2;
  const output = tokens / 2;

  const simpleInput = input * 0.6 * (0.13 / 1_000_000);
  const simpleOutput = output * 0.6 * (0.52 / 1_000_000);
  const medInput = input * 0.3 * (0.52 / 1_000_000);
  const medOutput = output * 0.3 * (2.08 / 1_000_000);

  return {
    agencyOs: simpleInput + simpleOutput + medInput + medOutput,
    label: "auto (smart routing)",
  };
}

export function calcDirectCost(model: string, tokens: number): number {
  const costs = directCosts[model];
  if (!costs) return 0;
  const input = tokens / 2;
  const output = tokens / 2;
  return (input * costs.input + output * costs.output) / 1_000_000;
}

export function calcAgencyOsCost(model: string, tokens: number): number {
  const m = models.find((x) => x.name === model);
  if (!m) return 0;

  const smartPortion = calcSmartRoutingCost(tokens);
  const complexInput = (tokens / 2) * 0.1 * (m.input / 1_000_000);
  const complexOutput = (tokens / 2) * 0.1 * (m.output / 1_000_000);

  return smartPortion.agencyOs + complexInput + complexOutput;
}
