import {NextRequest,NextResponse} from "next/server";import {getAuthUser,refreshAuthSession} from "./lib/auth-api";
const ACCESS="factory_access_token",REFRESH="factory_refresh_token";const cookieBase={httpOnly:true,sameSite:"lax" as const,secure:process.env.NODE_ENV==="production",path:"/"};
export async function middleware(request:NextRequest){const path=request.nextUrl.pathname;if(path==="/login"||path==="/unauthorized"||path==="/api/health"||path==="/api/integrations/github-app/webhook")return NextResponse.next();let access=request.cookies.get(ACCESS)?.value;const refresh=request.cookies.get(REFRESH)?.value;let user=access?await getAuthUser(access):null;let session=null;if(!user&&refresh){session=await refreshAuthSession(refresh);if(session){access=session.access_token;user=await getAuthUser(access);}}if(!user){const url=request.nextUrl.clone();url.pathname="/login";url.searchParams.set("next",path+request.nextUrl.search);return NextResponse.redirect(url);}// NextResponse cookies alone update the *next* browser request. Server
// Components rendered in THIS request otherwise see the expired access token
// and may redirect an already refreshed session to /unauthorized. Forward only
// the fresh Cookie header via Next's request override, without exposing tokens
// in response headers or weakening the verified getAuthUser boundary.
const headers=new Headers(request.headers);
if(session){
 const cookieHeader=headers.get("cookie")||"";
 const names=new Set([ACCESS,REFRESH]);
 const retained=cookieHeader.split(";").map(v=>v.trim()).filter(v=>{
  const name=v.split("=",1)[0]?.trim();
  return name&&!names.has(name);
 });
 retained.push(ACCESS+"="+encodeURIComponent(session.access_token));
 retained.push(REFRESH+"="+encodeURIComponent(session.refresh_token));
 headers.set("cookie",retained.join("; "));
}
const response=session?NextResponse.next({request:{headers}}):NextResponse.next();
if(session){response.cookies.set(ACCESS,session.access_token,{...cookieBase,maxAge:Math.max(60,session.expires_in)});response.cookies.set(REFRESH,session.refresh_token,cookieBase);}return response;}
export const config={matcher:["/((?!_next/static|_next/image|favicon.ico).*)"]};
