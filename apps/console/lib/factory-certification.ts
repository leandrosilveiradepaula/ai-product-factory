import {requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";

// A historical persisted certificate is not a certificate for the current main.
// In particular, the database's is_current flag can coexist on old rows.
export type FactoryCertificate={
 state:"certified"|"not_certified"|"unavailable";
 sha:string|null;
 passed:number|null;
 total:number|null;
 persistedAt:string|null;
};
const repository="leandrosilveiradepaula/ai-product-factory";
const shaPattern=/^[a-f0-9]{40}$/;
const requiredCriteria:Record<string,readonly string[]>={
 documentation:["setup_configuration","operations","release_rollback"],
 functional_completeness:["requirements_inventory","mock_noop_demo_inventory","critical_journeys"],
 observability_operations:["health","traceability","recovery_alerting"],
 product_experience:["surface_inventory","responsive","accessibility","states"],
 security:["authn_authz","data_access_boundaries","secrets_dependencies"],
 test_strategy:["unit_integration","critical_e2e","regression_gates"],
};
const unavailable:FactoryCertificate={state:"unavailable",sha:null,passed:null,total:null,persistedAt:null};

export function classifyFactoryCertificate(mainSha:unknown,rows:unknown):FactoryCertificate{
 if(typeof mainSha!=="string"||!shaPattern.test(mainSha)||!Array.isArray(rows)||rows.length>1)
  return unavailable;
 const pending:FactoryCertificate={state:"not_certified",sha:mainSha,passed:null,total:19,persistedAt:null};
 if(rows.length===0)return pending;
 const row=rows[0];
 if(!row||typeof row!=="object"||Array.isArray(row))return pending;
 const record=row as Record<string,unknown>;
 const report=record.report;
 if(record.assessed_commit!==mainSha||record.state!=="persisted"||
    !report||typeof report!=="object"||Array.isArray(report))return pending;
 const value=report as Record<string,unknown>;
 if(value.assessed_commit!==undefined&&value.assessed_commit!==mainSha)return pending;
 const assessment=value.assessment;
 const criteria=value.criteria;
 if(!assessment||typeof assessment!=="object"||Array.isArray(assessment)||
    !criteria||typeof criteria!=="object"||Array.isArray(criteria))return pending;
 const status=assessment as Record<string,unknown>;
 const domains=criteria as Record<string,unknown>;
 if(status.ready!==true||status.status!=="passed"||
    Object.keys(domains).length!==6)return pending;
 let count=0;
 for(const [domain,required] of Object.entries(requiredCriteria)){
  const actual=domains[domain];
  if(!actual||typeof actual!=="object"||Array.isArray(actual))return pending;
  const items=actual as Record<string,unknown>;
  if(Object.keys(items).length!==required.length)return pending;
  for(const key of required){
   const item=items[key];
   if(!item||typeof item!=="object"||Array.isArray(item)||
      (item as Record<string,unknown>).status!=="passed")return pending;
   count+=1;
  }
 }
 if(count!==19)return pending;
 const persisted=record.persisted_at;
 if(typeof persisted!=="string"||!Number.isFinite(Date.parse(persisted)))return pending;
 return {state:"certified",sha:mainSha,passed:count,total:19,persistedAt:persisted};
}

export async function getCurrentFactoryCertificate():Promise<FactoryCertificate>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)return unavailable;
 try{
  const ref=await fetch("https://api.github.com/repos/"+repository+"/git/ref/heads/main",{
   headers:{"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"},
   cache:"no-store",
  });
  if(!ref.ok)return unavailable;
  const head:unknown=await ref.json();
  if(!head||typeof head!=="object"||!("object" in head))return unavailable;
  const sha=(head as {object?:{sha?:unknown}}).object?.sha;
  if(typeof sha!=="string"||!shaPattern.test(sha))return unavailable;
  const path=cfg.url+"/rest/v1/factory_product_readiness_certifications"+
   "?select=assessed_commit,state,persisted_at,report"+
   "&repository=eq."+encodeURIComponent(repository)+
   "&assessed_commit=eq."+sha+"&state=eq.persisted"+
   "&order=persisted_at.desc&limit=1";
  const result=await fetch(path,{headers:cfg.headers,cache:"no-store"});
  if(!result.ok)return unavailable;
  return classifyFactoryCertificate(sha,await result.json());
 }catch{return unavailable;}
}


// Public-only read of the repository main. An inaccessible private repo remains
// unverified here; never expose an installation token or use an arbitrary URL.
export async function getPublicProjectMainCommit(repo:string|null):Promise<string|null>{
 await requireConsoleOperator();
 if(typeof repo!=="string"||!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo))return null;
 try{
  const path=repo.split("/").map(encodeURIComponent).join("/");
  const response=await fetch("https://api.github.com/repos/"+path+"/git/ref/heads/main",{
   headers:{"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"},
   cache:"no-store",
  });
  if(!response.ok)return null;
  const row:unknown=await response.json();
  if(!row||typeof row!=="object"||!("object" in row)||!("ref" in row)||row.ref!=="refs/heads/main")return null;
  const sha=(row as {object?:{sha?:unknown}}).object?.sha;
  return typeof sha==="string"&&shaPattern.test(sha)?sha:null;
 }catch{return null;}
}
