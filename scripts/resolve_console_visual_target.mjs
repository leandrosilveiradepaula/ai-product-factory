// Select the actual Console revision to audit. No credentials or model calls.
// A production UI merge always targets the pushed SHA, not the historical
// source-controlled target left behind by a previous incident.
import fs from "node:fs";
import {execFileSync} from "node:child_process";
import {pathToFileURL} from "node:url";
import {consoleVisualOrigin} from "./console_visual_origin.mjs";

export const PRODUCTION_URL="https://ai-product-factory-console.vercel.app";
const SHA=/^[0-9a-f]{40}$/;

function safeTarget(input,source){
 const candidate_sha=String(input?.candidate_sha||"");
 if(!SHA.test(candidate_sha))throw new Error("visual target SHA must be an exact 40-character lowercase SHA");
 // Validate ownership before putting the target in the Actions environment.
 // The provisioned operator must never authenticate to a third-party Vercel site.
 const origin=consoleVisualOrigin(String(input?.preview_url||""));
 for(const value of Object.values(input||{})){
  if(typeof value==="string"&&/(token|secret|password|apikey|authorization)/i.test(value)){
   throw new Error("secret-like visual target metadata forbidden");
  }
 }
 return {preview_url:origin,candidate_sha,source};
}

export function selectConsoleVisualTarget({eventName,headSha,dispatchUrl="",dispatchCommit="",consoleChanged=false,pinnedTarget=null}){
 if(eventName==="workflow_dispatch"){
  return safeTarget({preview_url:dispatchUrl||PRODUCTION_URL,candidate_sha:dispatchCommit||headSha},"manual_exact");
 }
 if(eventName!=="push")throw new Error("unsupported visual audit trigger");
 if(!SHA.test(String(headSha||"")))throw new Error("invalid source commit");
 if(consoleChanged){
  return safeTarget({preview_url:PRODUCTION_URL,candidate_sha:headSha},"production_console_push");
 }
 if(!pinnedTarget||typeof pinnedTarget!=="object"||Array.isArray(pinnedTarget)){
  throw new Error("no explicitly pinned visual target for non-Console push");
 }
 return safeTarget(pinnedTarget,"source_control_pinned");
}

function changedConsoleInPush(){
 // fetch-depth:2 is required; never silently infer that no app files changed.
 const changes=execFileSync("git",["diff","--name-only","HEAD^","HEAD","--","apps/console/"],{encoding:"utf8"}).trim();
 return changes.length>0;
}

function main(){
 const eventName=process.env.GITHUB_EVENT_NAME||"";
 const pinnedTarget=eventName==="push"?
  JSON.parse(fs.readFileSync(".github/authenticated-visual-target.json","utf8")):null;
 const result=selectConsoleVisualTarget({
  eventName,headSha:process.env.GITHUB_SHA,
  dispatchUrl:process.env.DISPATCH_TARGET_URL||"",
  dispatchCommit:process.env.DISPATCH_TARGET_COMMIT||"",
  consoleChanged:eventName==="push"?changedConsoleInPush():false,
  pinnedTarget,
 });
 const envFile=process.env.GITHUB_ENV;
 if(!envFile)throw new Error("GITHUB_ENV is missing");
 fs.appendFileSync(envFile,"FACTORY_CONSOLE_URL="+result.preview_url+"\n"+
  "FACTORY_VISUAL_TARGET_COMMIT="+result.candidate_sha+"\n");
 console.log("visual_target_source="+result.source);
 console.log("visual_target_host="+new URL(result.preview_url).hostname);
 console.log("visual_target_commit="+result.candidate_sha);
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)main();
