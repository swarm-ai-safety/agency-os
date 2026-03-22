import { rm, mkdir } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";

const ROOT = process.cwd();
const COVERAGE_DIR = path.join(ROOT, "coverage");
const TMP_DIR = path.join(COVERAGE_DIR, ".tmp");
const VITEST_BIN = path.join(ROOT, "node_modules", "vitest", "vitest.mjs");
const MAX_ATTEMPTS = 2;
const ENOENT_TMP_PATTERN = /ENOENT: no such file or directory.*coverage\/\.tmp\/coverage-\d+\.json/s;

function runVitestCoverage() {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [VITEST_BIN, "run", "--coverage"], {
      stdio: ["inherit", "inherit", "pipe"],
      env: process.env,
    });

    let stderr = "";
    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      process.stderr.write(text);
    });

    child.on("close", (code) => {
      resolve({ code: code ?? 1, stderr });
    });
  });
}

for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
  await rm(COVERAGE_DIR, { recursive: true, force: true });
  await mkdir(TMP_DIR, { recursive: true });

  const { code, stderr } = await runVitestCoverage();
  if (code === 0) {
    process.exit(0);
  }

  const isRetryableTmpEnoent = ENOENT_TMP_PATTERN.test(stderr);
  if (!isRetryableTmpEnoent || attempt === MAX_ATTEMPTS) {
    process.exit(code);
  }

  console.error(
    `Vitest coverage hit transient tmp ENOENT (attempt ${attempt}/${MAX_ATTEMPTS}); retrying once...`,
  );
}
