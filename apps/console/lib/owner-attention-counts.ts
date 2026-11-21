// Product approval and GitHub installation are distinct owner responsibilities.
// Without a registered App, install candidates are not yet actionable.
export type OwnerAttentionCounts={pendingHumanGateCount:number;pendingIntegrationActionCount:number;count:number};
export function ownerAttentionCounts(input:{
 pendingHumanGateCount:number;githubAppConfigured:boolean;pendingInstallCount:number;
}):OwnerAttentionCounts{
 const {pendingHumanGateCount,githubAppConfigured,pendingInstallCount}=input;
 if(!Number.isSafeInteger(pendingHumanGateCount)||pendingHumanGateCount<0||
    typeof githubAppConfigured!=="boolean"||
    !Number.isSafeInteger(pendingInstallCount)||pendingInstallCount<0)
   throw new Error("owner_attention_unverifiable");
 const pendingIntegrationActionCount=githubAppConfigured?pendingInstallCount:1;
 const count=pendingHumanGateCount+pendingIntegrationActionCount;
 if(!Number.isSafeInteger(count))throw new Error("owner_attention_unverifiable");
 return {pendingHumanGateCount,pendingIntegrationActionCount,count};
}
