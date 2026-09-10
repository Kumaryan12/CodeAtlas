// Trusted launcher: no package scripts, dependency installs, or repository options.
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
const tests = [];
function visit(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) visit(path);
    else if (/\.(test|spec)\.(js|cjs|mjs|ts)$/.test(entry.name)) tests.push(path);
  }
}
visit("/workspace");
if (!tests.length) {
  console.error("No .test/.spec JS or TS files discovered.");
  process.exit(5);
}
const result = spawnSync(process.execPath, ["--test", "--test-concurrency=1", "--test-reporter=tap", ...tests.sort()], { stdio: "inherit" });
process.exit(result.status ?? 1);
