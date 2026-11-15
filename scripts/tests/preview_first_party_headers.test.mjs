import test from "node:test";
import assert from "node:assert/strict";
import {firstPartyPreviewHeaders} from "../preview_first_party_headers.mjs";

const origin="https://example-branch-team.vercel.app";
test("first-party requests suppress toolbar and carry only owned trusted OIDC",()=>{
 const h=firstPartyPreviewHeaders({requestUrl:origin+"/app?page=1",previewOrigin:origin,
   trustedOidcToken:"fixture-token",currentHeaders:{"accept":"text/html"}});
 assert.equal(h["x-vercel-skip-toolbar"],"1");
 assert.equal(h["x-vercel-trusted-oidc-idp-token"],"fixture-token");
 assert.equal(h.accept,"text/html");
});
test("cross-origin and protocol redirects cannot receive OIDC",()=>{
 for(const url of ["https://vercel.live/ping","https://assets.vercel.com/script.js",
   "https://example-branch-team.vercel.app.evil.invalid/","http://example-branch-team.vercel.app/"])
  assert.throws(()=>firstPartyPreviewHeaders({requestUrl:url,previewOrigin:origin,
    trustedOidcToken:"fixture-token"}),/preview_header_scope_mismatch/);
});
test("invalid preview origins rejected and inherited credentials stripped",()=>{
 for(const host of ["http://example.vercel.app","https://evil.example","https://test.vercel.app/path"])
  assert.throws(()=>firstPartyPreviewHeaders({requestUrl:origin,previewOrigin:host}),/preview_header_scope_mismatch/);
 const h=firstPartyPreviewHeaders({requestUrl:origin+"/",previewOrigin:origin,
   currentHeaders:{"X-Vercel-Trusted-OIDC-IdP-Token":"old","X-Vercel-Skip-Toolbar":"0"}});
 assert.equal(h["x-vercel-skip-toolbar"],"1");
 assert.ok(!Object.hasOwn(h,"X-Vercel-Trusted-OIDC-IdP-Token"));
 assert.ok(!Object.hasOwn(h,"x-vercel-trusted-oidc-idp-token"));
});
