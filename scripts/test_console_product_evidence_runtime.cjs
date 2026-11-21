/* Real TypeScript evidence classifier, isolated from network and mutations. */
"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,".."),ts=require(path.join(root,"apps/console/node_modules/typescript"));
const input=fs.readFileSync(path.join(root,"apps/console/lib/product-evidence.ts"),"utf8");
const js=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(js,context,{timeout:10000});
const assess=context.exports.assessProductProof;
const sha="a".repeat(40);
test("Dark-like observed merge is never product ready when report explicitly says incomplete",()=>{
 const proof=assess({releaseStatus:"released",productComplete:false,productReadinessReady:false,definitionReady:false,mergeSha:sha,releaseCandidateSha:sha,hasPreviewRecord:true,hasProductionDeployment:true});
 assert.equal(proof.hasHumanMerge,true);assert.equal(proof.hasPreviewRecord,true);
 assert.equal(proof.productReady,false);assert.equal(proof.productComplete,false);
 assert.match(proof.headline,/não comprovado/);assert.match(proof.explanation,/integração de código/);
});
test("a successful preview, release report or technical merge alone cannot certify product",()=>{
 for(const i of [
  {releaseStatus:"released",mergeSha:sha},
  {releaseStatus:"released",productComplete:true,productReadinessReady:true,definitionReady:true,mergeSha:sha},
  {releaseStatus:"released",productComplete:true,productReadinessReady:true,definitionReady:true,mergeSha:sha,hasProductionDeployment:true,certificationSha:"b".repeat(40),releaseCandidateSha:sha},
  {hasPreviewRecord:true},
  {hasProductionDeployment:true}
 ])assert.equal(assess(i).productReady,false);
});
test("only strong same-candidate evidence qualifies as recorded completeness",()=>{
 const proof=assess({releaseStatus:"released",productComplete:true,productReadinessReady:true,definitionReady:true,mergeSha:sha,hasProductionDeployment:true,certificationSha:sha,releaseCandidateSha:sha});
 assert.equal(proof.productReady,true);
});
test("historical certification for a different SHA cannot be reused",()=>{
 const proof=assess({releaseStatus:"released",productComplete:true,productReadinessReady:true,definitionReady:true,certificationSha:"b".repeat(40),releaseCandidateSha:sha,hasProductionDeployment:true});
 assert.equal(proof.productReady,false);
});
test("preview-only, absent release and blocked release remain distinguishable",()=>{
 assert.match(assess({hasPreviewRecord:true}).headline,/Prévia registrada/);
 assert.match(assess({}).headline,/Sem entrega comprovada/);
 assert.match(assess({releaseStatus:"blocked"}).headline,/bloqueada/);
});
test("malformed SHA, missing status and optimistic inputs fail closed",()=>{
 assert.equal(assess({mergeSha:"not_sha",productComplete:"true",productReadinessReady:"true"}).productReady,false);
 assert.equal(assess({}).productComplete,null);
});
