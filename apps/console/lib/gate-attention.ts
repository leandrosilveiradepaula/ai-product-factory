/** Separate durable human decisions from optional GitHub integration setup.
 * A missing GitHub App installation requires explicit consent for that
 * project's cross-repo access; it does not become a production release gate.
 */
export function countGateAttention(
 humanDecisions:number, installationActions:number, githubAppConfigured:boolean,
):{pendingHumanGateCount:number;pendingIntegrationActionCount:number}{
 if(!Number.isSafeInteger(humanDecisions)||humanDecisions<0||
    !Number.isSafeInteger(installationActions)||installationActions<0||
    typeof githubAppConfigured!=="boolean"){
  throw new Error("Invalid gate-attention counters");
 }
 return{
  pendingHumanGateCount:humanDecisions,
  pendingIntegrationActionCount:githubAppConfigured?installationActions:1,
 };
}
