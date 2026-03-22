const requiredMajor = 22;
const skipCheck = process.env.SKIP_NODE_VERSION_CHECK === "1";

if (skipCheck) {
  process.exit(0);
}

const [nodeMajorRaw] = process.versions.node.split(".");
const nodeMajor = Number(nodeMajorRaw);

if (Number.isNaN(nodeMajor) || nodeMajor !== requiredMajor) {
  console.error(
    [
      `Unsupported Node.js version: ${process.versions.node}.`,
      `Use Node ${requiredMajor}.x for deterministic frontend installs in this repository.`,
      "Tip: run `nvm use 22` before installing site dependencies.",
    ].join("\n"),
  );
  process.exit(1);
}
