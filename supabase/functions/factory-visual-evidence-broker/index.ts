import { createRemoteJWKSet, jwtVerify } from "npm:jose@6.1.0";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "factory-visual-evidence";
const JWKS = createRemoteJWKSet(
  new URL("https://token.actions.githubusercontent.com/.well-known/jwks"),
);

const EXPECTED = {
  repository: "leandrosilveiradepaula/ai-product-factory",
  repository_id: "1387883686",
  repository_owner_id: "256917842",
  ref: "refs/heads/main",
  environment: "openai-api",
  workflow_ref:
    "leandrosilveiradepaula/ai-product-factory/.github/workflows/authenticated-visual-evidence.yml@refs/heads/main",
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
    },
  });
}

function randomHex(bytes: number) {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return Array.from(values, (value) =>
    value.toString(16).padStart(2, "0")
  ).join("");
}

async function requireGithub(req: Request) {
  const auth = req.headers.get("authorization") || "";
  if (!auth.startsWith("Bearer ")) {
    throw new Error("missing GitHub OIDC token");
  }

  const token = auth.slice(7);
  const { payload } = await jwtVerify(token, JWKS, {
    issuer: ISSUER,
    audience: AUDIENCE,
  });

  for (const [key, expected] of Object.entries(EXPECTED)) {
    if (String(payload[key] ?? "") !== expected) {
      throw new Error("GitHub OIDC claim mismatch: " + key);
    }
  }

  const event = String(payload.event_name ?? "");
  if (!["push", "workflow_dispatch"].includes(event)) {
    throw new Error("GitHub OIDC event not allowed");
  }

  return payload;
}

function supabaseConfig() {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) {
    throw new Error("Supabase server configuration missing");
  }
  return { url: url.replace(/\/$/, ""), key };
}

async function adminFetch(path: string, init: RequestInit = {}) {
  const { url, key } = supabaseConfig();
  const headers = new Headers(init.headers || {});
  headers.set("apikey", key);
  headers.set("authorization", "Bearer " + key);
  headers.set("content-type", "application/json");

  const response = await fetch(url + path, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      "Supabase admin request failed " +
        response.status +
        ": " +
        detail.slice(0, 300),
    );
  }
  return response;
}

async function cleanupUser(userId: string) {
  try {
    await adminFetch(
      "/rest/v1/factory_console_operators?user_id=eq." +
        encodeURIComponent(userId),
      {
        method: "DELETE",
        headers: { Prefer: "return=minimal" },
      },
    );
  } catch {
    // Auth deletion remains the final cleanup authority.
  }

  await adminFetch(
    "/auth/v1/admin/users/" + encodeURIComponent(userId),
    { method: "DELETE" },
  );
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return json(405, { error: "method_not_allowed" });
  }

  try {
    const claims = await requireGithub(req);
    const body = await req.json();
    const action = String(body.action || "");
    const workflowRunId = Number(body.workflowRunId);

    if (!Number.isSafeInteger(workflowRunId) || workflowRunId <= 0) {
      return json(400, { error: "invalid_workflow_run_id" });
    }

    if (action === "provision") {
      const sourceCommit = String(body.sourceCommit || "");
      if (
        !/^[0-9a-f]{40}$/.test(sourceCommit) ||
        sourceCommit !== String(claims.sha || "")
      ) {
        return json(400, { error: "source_commit_mismatch" });
      }

      const artifactName = "authenticated-console-" + workflowRunId;
      const suffix = randomHex(8);
      const email =
        "factory-visual-" +
        workflowRunId +
        "-" +
        suffix +
        "@example.com";
      const password = "V!sual-" + randomHex(18) + "-9aZ!";
      const encryptionKey = randomHex(32);

      const created = await adminFetch("/auth/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          email_confirm: true,
        }),
      });
      const user = await created.json();
      const userId = String(user.id || "");
      if (!userId) {
        throw new Error("Auth user id missing");
      }

      try {
        await adminFetch("/rest/v1/factory_console_operators", {
          method: "POST",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({
            user_id: userId,
            role: "operator",
            is_active: true,
          }),
        });

        await adminFetch("/rest/v1/factory_visual_evidence_runs", {
          method: "POST",
          headers: {
            Prefer: "return=minimal,resolution=merge-duplicates",
          },
          body: JSON.stringify({
            workflow_run_id: workflowRunId,
            source_commit: sourceCommit,
            artifact_name: artifactName,
            encryption_key: encryptionKey,
            status: "prepared",
            expires_at: new Date(
              Date.now() + 2 * 60 * 60 * 1000,
            ).toISOString(),
          }),
        });
      } catch (error) {
        await cleanupUser(userId);
        throw error;
      }

      return json(200, {
        email,
        password,
        userId,
        encryptionKey,
        artifactName,
      });
    }

    if (action === "captured") {
      await adminFetch(
        "/rest/v1/factory_visual_evidence_runs?workflow_run_id=eq." +
          workflowRunId,
        {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({ status: "captured" }),
        },
      );
      return json(200, { ok: true });
    }

    if (action === "cleanup") {
      const userId = String(body.userId || "");
      if (userId) {
        await cleanupUser(userId);
      }
      return json(200, { ok: true });
    }

    if (action === "expire") {
      const userId = String(body.userId || "");
      if (userId) {
        try {
          await cleanupUser(userId);
        } catch {
          // Registry expiry still proceeds.
        }
      }

      await adminFetch(
        "/rest/v1/factory_visual_evidence_runs?workflow_run_id=eq." +
          workflowRunId,
        {
          method: "PATCH",
          headers: { Prefer: "return=minimal" },
          body: JSON.stringify({ status: "expired" }),
        },
      );
      return json(200, { ok: true });
    }

    return json(400, { error: "unknown_action" });
  } catch (error) {
    console.error("visual evidence broker rejected request");
    return json(403, {
      error: "forbidden",
      detail: error instanceof Error ? error.message : "unknown",
    });
  }
});
