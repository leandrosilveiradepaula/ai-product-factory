import test from "node:test";
import assert from "node:assert/strict";
import {
  isVercelExternalTelemetryPing403,
  isCorrelatedVercelPingConsoleError,
} from "../preview_browser_integrity.mjs";

const origin="https://candidate-project.vercel.app";
const ping="https://vercel.live/ping";
const input=(requestUrl,resourceType="ping",status=403)=>({
  requestUrl,previewOrigin:origin,resourceType,status,
});

test("only exact Vercel-owned, external 403 ping responses qualify",()=>{
  assert.equal(isVercelExternalTelemetryPing403(input(ping)),true);
  assert.equal(isVercelExternalTelemetryPing403(input("https://vercel.com/feedback/ping")),true);
  for(const bad of [
    input(origin+"/api/session"),
    input(origin+"/ping"),
    input("https://api.example.test/ping"),
    input("https://vercel.live.evil.test/ping"),
    input("http://vercel.live/ping"),
    input("https://vercel.live/ping","fetch"),
    input("https://vercel.live/ping","xhr"),
    input("https://vercel.live/ping","document"),
    input("https://vercel.live/ping","ping",401),
    input("https://vercel.live/ping","ping",500),
  ]){
    assert.equal(isVercelExternalTelemetryPing403(bad),false,JSON.stringify(bad));
  }
});

test("never suppress application JS or first-party failures using an unrelated ping",()=>{
  const text="Failed to load resource: the server responded with a status of 403 ()";
  const opts={text,sourceUrl:ping,previewOrigin:origin,ignoredPingUrls:new Set([ping])};
  assert.equal(isCorrelatedVercelPingConsoleError(opts),true);
  for(const bad of [
    {...opts,sourceUrl:origin+"/api/session"},
    {...opts,sourceUrl:""},
    {...opts,ignoredPingUrls:new Set()},
    {...opts,text:"Uncaught TypeError: cannot load users"},
    {...opts,text:"Failed to load resource: the server responded with a status of 404 ()"},
  ]){
    assert.equal(isCorrelatedVercelPingConsoleError(bad),false);
  }
});
