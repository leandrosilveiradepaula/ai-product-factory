"use strict";

// createWorkflowDispatch does not return a run id. Require a unique nonce,
// the exact child workflow, pinned main SHA and immutable GitHub run identity.
const WORKFLOW_PATH = ".github/workflows/console-browser-evidence.yml";
const SHA = /^[0-9a-f]{40}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function evidenceRunTitle(requestId) {
  if (typeof requestId !== "string" || !UUID.test(requestId)) {
    throw new Error("invalid browser correlation identifier");
  }
  return "Console evidence " + requestId;
}

function selectBrowserRun(runs, {requestId, factorySha, startedAtMs}) {
  const title = evidenceRunTitle(requestId);
  if (!SHA.test(factorySha) || !Number.isFinite(startedAtMs) || startedAtMs < 0) {
    throw new Error("invalid pinned Factory run identity");
  }
  if (!Array.isArray(runs) || runs.length > 100) {
    throw new Error("invalid browser run listing");
  }
  const matching = runs.filter((run) => {
    if (!run || typeof run !== "object") return false;
    const started = Date.parse(run.created_at);
    return run.display_title === title
      && run.path === WORKFLOW_PATH
      && run.event === "workflow_dispatch"
      && run.head_branch === "main"
      && run.head_sha === factorySha
      && run.run_attempt === 1
      && Number.isSafeInteger(run.id) && run.id > 0
      && run.html_url === "https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/" + run.id
      && Number.isFinite(started)
      && started >= startedAtMs - 5000;
  });
  if (matching.length > 1) throw new Error("ambiguous correlated browser runs");
  return matching[0] || null;
}

module.exports = {evidenceRunTitle, selectBrowserRun};
