"use strict";
/* Parse the production Edge TypeScript source with the pinned Console compiler.
 * This check runs after npm ci --ignore-scripts and requires no Deno secrets,
 * network access, Supabase credentials, Github App token or paid model.
 */
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const ts = require(path.join(root, "apps", "console", "node_modules", "typescript"));
const file = path.join(root, "supabase", "functions", "factory-runtime-control-plane", "index.ts");
const source = fs.readFileSync(file, "utf8");
const parsed = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const diagnostics = parsed.parseDiagnostics || [];
if (!source.includes("b4ReadOnlyComparedSource") ||
    !source.includes("B4_COMPARE_PERMISSIONS") ||
    diagnostics.length) {
  for (const issue of diagnostics.slice(0, 10)) {
    const pos = parsed.getLineAndCharacterOfPosition(issue.start || 0);
    // Only compiler error codes and positions. Never show raw source, URLs or tokens.
    process.stderr.write("B4_EDGE_TYPESCRIPT_PARSE_ERROR=" + issue.code +
      " line=" + (pos.line + 1) + "\n");
  }
  process.exitCode = 1;
} else {
  process.stdout.write("B4_EDGE_TYPESCRIPT_SYNTAX=PASS\n");
}
