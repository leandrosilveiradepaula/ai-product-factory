import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {isUnauthenticatedTransportAllowed} from "../lib/middleware-auth-boundary.ts";

const WEBHOOK="/api/integrations/github-app/webhook";

test("only exact signed GitHub App POST transport bypasses Console login",()=>{
 assert.equal(isUnauthenticatedTransportAllowed(WEBHOOK,"POST"),true);
 for(const [pathname,method] of [
  [WEBHOOK,"GET"],[WEBHOOK,"HEAD"],[WEBHOOK,"PUT"],[WEBHOOK,"DELETE"],
  [WEBHOOK,"post"],[WEBHOOK+"/","POST"],[WEBHOOK+"/another","POST"],
  ["/api/integrations/github-app/verify","POST"],
  ["/api/integrations/github-app/register","GET"],
  ["/api/integrations/github-app/callback","GET"],
  ["/api/projects","GET"],["/api/projects","POST"],
  ["/api/health/unsafe","POST"],["/api/integrations","POST"],
  ["/api/integrations/github-app/webhook-forged","POST"],
 ])assert.equal(isUnauthenticatedTransportAllowed(pathname,method),false,`${method} ${pathname}`);
});
test("existing anonymous UI and health paths remain available",()=>{
 for(const [pathname,method] of [
  ["/login","GET"],["/login","POST"],["/unauthorized","GET"],["/api/health","GET"],
 ])assert.equal(isUnauthenticatedTransportAllowed(pathname,method),true);
});
test("middleware checks transport exception before reading cookies or auth",()=>{
 const source=readFileSync(new URL("../middleware.ts",import.meta.url),"utf8");
 assert.match(source,/import\s*\{isUnauthenticatedTransportAllowed\}\s*from\s*"\.\/lib\/middleware-auth-boundary"/);
 const bypass=source.indexOf("isUnauthenticatedTransportAllowed(path,request.method)");
 const cookies=source.indexOf("request.cookies.get(ACCESS)");
 const auth=source.indexOf("getAuthUser(access)");
 assert.ok(bypass>=0&&cookies>bypass&&auth>cookies);
 assert.match(source,/return NextResponse\.redirect\(url\)/);
});
test("webhook remains fail-closed: flag then HMAC then claim then worker wake",()=>{
 const route=readFileSync(new URL("../app/api/integrations/github-app/webhook/route.ts",import.meta.url),"utf8");
 const markers=[
  'process.env.FACTORY_GITHUB_WEBHOOK_ENABLED!=="true"',
  "getGitHubWebhookVerificationConfig()",
  "authenticateGitHubWebhook(bytes,request.headers,verifier.webhookSecret)",
  "claimExternalWebhookWake(event)",
  "requestIntakeWorkerWake()",
 ];
 const locations=markers.map(value=>route.indexOf(value));
 assert.ok(locations.every(x=>x>=0),JSON.stringify(locations));
 assert.deepEqual(locations,[...locations].sort((a,b)=>a-b));
 assert.match(route,/MAX_WEBHOOK_BYTES/);
 assert.match(route,/acknowledgeExternalWebhookWake\(/);
});
