/** Safe first-party Vercel Preview evidence headers. Never mock responses. */
export function firstPartyPreviewHeaders({
  requestUrl,previewOrigin,trustedOidcToken="",currentHeaders={},
}){
  const trusted=new URL(previewOrigin),request=new URL(requestUrl);
  if(trusted.protocol!=="https:"||!trusted.hostname.endsWith(".vercel.app")||
     trusted.username||trusted.password||trusted.port||trusted.search||trusted.hash||
     trusted.pathname!=="/"||request.origin!==trusted.origin)
    throw new Error("preview_header_scope_mismatch");
  // Do not preserve any incoming copies of these sensitive/privileged headers.
  const headers=Object.fromEntries(Object.entries(currentHeaders).filter(([name])=>
    !["x-vercel-trusted-oidc-idp-token","x-vercel-skip-toolbar"].includes(name.toLowerCase())));
  headers["x-vercel-skip-toolbar"]="1";
  if(trustedOidcToken)headers["x-vercel-trusted-oidc-idp-token"]=trustedOidcToken;
  return headers;
}
