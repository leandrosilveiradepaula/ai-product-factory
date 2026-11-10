/** Safe pre-provisioning reconciliation: main SHA may advance without a Console build. */
import fs from "node:fs";
import {pathToFileURL} from "node:url";
import {CONSOLE_PRODUCTION_HOST,consoleVisualOrigin,consoleVercelDeploymentStatus} from "./console_visual_origin.mjs";
const REPO="/repos/leandrosilveiradepaula/ai-product-factory",SHA=/^[0-9a-f]{40}$/,SHORT=/^[0-9a-f]{12}$/;
function entry(tree,path,type,mode){
 if(tree?.truncated!==false||!Array.isArray(tree.tree)||tree.tree.length>1000)throw Error("console_git_tree_incomplete");
 const hits=tree.tree.filter(x=>x?.path===path);
 if(hits.length!==1||hits[0].type!==type||hits[0].mode!==mode||!SHA.test(hits[0].sha))
   throw Error("console_git_tree_entry_invalid");
 return hits[0].sha;
}
async function identity(get,sha){
 const c=await get(REPO+"/commits/"+sha);
 if(c?.sha!==sha||!SHA.test(c.commit?.tree?.sha))throw Error("console_git_commit_unverified");
 const root=await get(REPO+"/git/trees/"+c.commit.tree.sha);
 const [apps,config]=await Promise.all([
  get(REPO+"/git/trees/"+entry(root,"apps","tree","040000")),
  get(REPO+"/git/trees/"+entry(root,"config","tree","040000")),
 ]);
 return {
  console:entry(apps,"console","tree","040000"),
  policy:entry(config,"factory.release-policy.v1.json","blob","100644"),
 };
}
async function health(request,url,token){
 const r=await request(url,{
  headers:{"Accept":"application/json","Cache-Control":"no-store",
   "x-vercel-trusted-oidc-idp-token":token},
  redirect:"error",signal:AbortSignal.timeout(12000),
 });
 if(r?.status!==200)throw Error("console_live_health_unavailable");
 let payload;try{payload=await r.json();}catch{throw Error("console_live_health_unreadable");}
 if(payload?.status!=="ok"||payload.service!=="ai-product-factory-console"||
    !SHORT.test(payload.commit))throw Error("console_live_identity_invalid");
 return payload.commit;
}
export async function reconcileServedConsole({sourceCommit,consoleUrl,oidcToken,githubGet,request}){
 if(!SHA.test(sourceCommit)||typeof githubGet!=="function"||typeof request!=="function"||
    typeof oidcToken!=="string"||!oidcToken)throw Error("console_reconciliation_input_invalid");
 const origin=consoleVisualOrigin(consoleUrl);
 if(new URL(origin).hostname!==CONSOLE_PRODUCTION_HOST)throw Error("console_auto_resolution_production_only");
 const api=REPO;
 if((await githubGet(api+"/git/ref/heads/main"))?.object?.sha!==sourceCommit)
  throw Error("console_source_head_changed");
 const target=new URL("/api/health",origin).toString();
 const prefix=await health(request,target,oidcToken);
 const servedCandidate=await githubGet(api+"/commits/"+prefix);
 const servedCommit=servedCandidate?.sha;
 if(!SHA.test(servedCommit)||servedCommit.slice(0,12)!==prefix)throw Error("console_served_commit_ambiguous");
 const ancestry=await githubGet(api+"/compare/"+servedCommit+"..."+sourceCommit);
 if(!["ahead","identical"].includes(ancestry?.status)||ancestry.behind_by!==0||
    ancestry.base_commit?.sha!==servedCommit||ancestry.merge_base_commit?.sha!==servedCommit)
  throw Error("console_served_commit_not_ancestor");
 const [expected,observed,status]=await Promise.all([
  identity(githubGet,sourceCommit),identity(githubGet,servedCommit),
  githubGet(api+"/commits/"+servedCommit+"/status"),
 ]);
 if(expected.console!==observed.console||expected.policy!==observed.policy)
  throw Error("console_source_tree_changed_since_deployment");
 if(!Array.isArray(status?.statuses)||status.statuses.length>100)
  throw Error("console_served_vercel_status_unavailable");
 const matches=status.statuses.filter(s=>String(s?.context||"").toLowerCase()==="vercel");
 if(matches.length!==1)throw Error("console_served_vercel_status_ambiguous");
 const owner=consoleVercelDeploymentStatus({...matches[0],context:"Vercel"});
 const [headAgain,prefixAgain]=await Promise.all([
  githubGet(api+"/git/ref/heads/main"),health(request,target,oidcToken),
 ]);
 if(headAgain?.object?.sha!==sourceCommit||prefixAgain!==prefix)
  throw Error("console_live_identity_moved");
 return {
  schema:"factory-console-served-commit-reconciliation-v1",
  sourceCommit,servedCommit,consoleTreeSha:expected.console,
  releasePolicyBlobSha:expected.policy,origin,
  vercelDeploymentId:owner.deploymentId,
  proof:"canonical_live_health_git_ancestry_identical_console_tree_policy_and_owned_vercel_status",
  sourceEqualsServed:sourceCommit===servedCommit,
  authenticatedUxCertified:false,securityCertified:false,productReadyCertified:false,
  credentialOrPersonalDataRetained:false,writes:0,paidCalls:0,
 };
}
async function githubGet(path){
 const token=process.env.GITHUB_TOKEN;
 if(!token)throw Error("console_github_read_token_unavailable");
 const r=await fetch("https://api.github.com"+path,{
  headers:{"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,
   "X-GitHub-Api-Version":"2022-11-28"},
  redirect:"error",signal:AbortSignal.timeout(12000),
 });
 if(r.status!==200)throw Error("console_github_evidence_unavailable");
 return r.json();
}
async function main(){
 const result=await reconcileServedConsole({
  sourceCommit:process.env.GITHUB_SHA,consoleUrl:process.env.FACTORY_CONSOLE_URL,
  oidcToken:process.env.FACTORY_VERCEL_TRUSTED_OIDC_TOKEN,githubGet,request:fetch,
 });
 if(!process.env.GITHUB_ENV)throw Error("console_actions_environment_unavailable");
 fs.appendFileSync(process.env.GITHUB_ENV,"FACTORY_VISUAL_TARGET_COMMIT="+result.servedCommit+"\n"+
  "FACTORY_VISUAL_SOURCE_COMMIT="+result.sourceCommit+"\n");
 fs.writeFileSync("block1-console-commit-reconciliation.json",JSON.stringify(result,null,2)+"\n",
  {flag:"wx",mode:0o600});
 console.log(JSON.stringify({status:"served_console_revision_verified",sourceCommit:result.sourceCommit,
  servedCommit:result.servedCommit,consoleTreeSha:result.consoleTreeSha,
  deployment:result.vercelDeploymentId,productReadyCertified:false,writes:0,paidCalls:0}));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)
 main().catch(err=>{
  const code=err?.message;
  console.error("::error::"+(typeof code==="string"&&code.startsWith("console_")?
   code:"console_reconciliation_unverified"));
  process.exitCode=1;
 });
