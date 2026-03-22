import fs from "node:fs";
import path from "node:path";

const summaryPath = path.resolve(process.cwd(), "coverage", "coverage-summary.json");

const minimumCoverage = {
  statements: 10.0,
  branches: 4.5,
  functions: 13.0,
  lines: 9.0,
};

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!fs.existsSync(summaryPath)) {
  fail(
    `Coverage summary not found at ${summaryPath}. ` +
      "Run Vitest coverage with the json-summary reporter enabled."
  );
}

const raw = fs.readFileSync(summaryPath, "utf8");
const summary = JSON.parse(raw);
const total = summary.total ?? {};

const failures = [];

for (const [metric, minimum] of Object.entries(minimumCoverage)) {
  const actual = total[metric]?.pct;
  if (typeof actual !== "number") {
    failures.push(`${metric}: missing coverage metric`);
    continue;
  }
  if (actual < minimum) {
    failures.push(`${metric}: ${actual.toFixed(2)}% < ${minimum.toFixed(2)}%`);
  }
}

if (failures.length > 0) {
  fail(`Frontend coverage guardrail failed:\n- ${failures.join("\n- ")}`);
}

console.log("Frontend coverage guardrail passed.");
