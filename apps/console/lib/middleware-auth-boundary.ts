/**
 * Browser sessions protect the Console. The GitHub App delivers signed events
 * without an operator session, so only its exact POST transport can bypass the
 * session middleware. The route itself still enforces the feature flag, HMAC,
 * payload limit, installation/repository identity and durable Control Plane gates.
 *
 * Never generalize this exception to /api/integrations or all GitHub App routes.
 */
const GITHUB_APP_WEBHOOK_PATH="/api/integrations/github-app/webhook";

export function isUnauthenticatedTransportAllowed(pathname:string,method:string):boolean{
 return pathname.startsWith("/login")
  || pathname.startsWith("/unauthorized")
  || pathname==="/api/health"
  || (pathname===GITHUB_APP_WEBHOOK_PATH && method==="POST");
}
