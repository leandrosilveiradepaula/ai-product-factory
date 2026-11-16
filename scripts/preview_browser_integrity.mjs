/**
 * Strictly classify Vercel-owned telemetry, not general HTTP errors.
 * An ignored telemetry ping is never evidence that an app is ready.
 */
export function isVercelExternalTelemetryPing403({requestUrl,previewOrigin,resourceType,status}){
  if(status!==403||resourceType!=="ping")return false;
  try{
    const origin=new URL(previewOrigin),url=new URL(requestUrl);
    return origin.protocol==="https:" && origin.hostname.endsWith(".vercel.app")
      && url.protocol==="https:" && url.origin!==origin.origin
      && url.port==="" && (url.hostname==="vercel.live"||url.hostname==="vercel.com");
  }catch{return false;}
}

/** Suppress Chrome's exact error only if the originating request was this ping. */
export function isCorrelatedVercelPingConsoleError({text,sourceUrl,previewOrigin,ignoredPingUrls}){
  return typeof text==="string"
    && /Failed to load resource: the server responded with a status of 403/.test(text)
    && typeof sourceUrl==="string" && ignoredPingUrls instanceof Set
    && ignoredPingUrls.has(sourceUrl)
    && isVercelExternalTelemetryPing403({
      requestUrl:sourceUrl,previewOrigin,resourceType:"ping",status:403,
    });
}
