export type AuthSession={access_token:string;refresh_token:string;expires_in:number;user:{id:string;email?:string|null}};
export type AuthUser={id:string;email:string|null};
export type ConsoleOperator={userId:string;email:string|null;role:"operator"|"admin"};
function config(){const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_PUBLISHABLE_KEY;if(!url||!key)throw new Error("Supabase Auth configuration is missing");return{url,key};}
function record(value:unknown):value is Record<string,unknown>{return typeof value==="object"&&value!==null&&!Array.isArray(value);}
function validUserId(value:unknown):value is string{return typeof value==="string"&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);}
function authUser(value:unknown):AuthUser|null{
 if(!record(value)||!validUserId(value.id))return null;
 if(value.email!==undefined&&value.email!==null&&typeof value.email!=="string")return null;
 return{id:value.id,email:typeof value.email==="string"?value.email:null};
}
function authSession(value:unknown):AuthSession|null{
 if(!record(value)||typeof value.access_token!=="string"||!value.access_token||
    typeof value.refresh_token!=="string"||!value.refresh_token||
    typeof value.expires_in!=="number"||!Number.isFinite(value.expires_in)||value.expires_in<=0)return null;
 const user=authUser(value.user);
 if(!user)return null;
 return{access_token:value.access_token,refresh_token:value.refresh_token,expires_in:value.expires_in,
        user:{id:user.id,email:user.email}};
}
export async function signInPassword(email:string,password:string):Promise<AuthSession>{
 const {url,key}=config();
 const r=await fetch(`${url}/auth/v1/token?grant_type=password`,{method:"POST",headers:{apikey:key,"Content-Type":"application/json"},body:JSON.stringify({email,password}),cache:"no-store"});
 if(!r.ok)throw new Error("invalid credentials");
 const session=authSession(await r.json());
 if(!session)throw new Error("invalid auth response");
 return session;
}
export async function refreshAuthSession(refreshToken:string):Promise<AuthSession|null>{
 const {url,key}=config();
 const r=await fetch(`${url}/auth/v1/token?grant_type=refresh_token`,{method:"POST",headers:{apikey:key,"Content-Type":"application/json"},body:JSON.stringify({refresh_token:refreshToken}),cache:"no-store"});
 if(!r.ok)return null;
 return authSession(await r.json());
}
export async function getAuthUser(accessToken:string):Promise<AuthUser|null>{
 const {url,key}=config();
 if(!accessToken)return null;
 const r=await fetch(`${url}/auth/v1/user`,{headers:{apikey:key,Authorization:`Bearer ${accessToken}`},cache:"no-store"});
 if(!r.ok)return null;
 return authUser(await r.json());
}
export async function getConsoleOperator(accessToken:string):Promise<ConsoleOperator|null>{
 const {url,key}=config();
 const user=await getAuthUser(accessToken);
 if(!user)return null;
 const opResponse=await fetch(`${url}/rest/v1/factory_console_operators?select=role,is_active&user_id=eq.${encodeURIComponent(user.id)}&is_active=eq.true&limit=1`,{headers:{apikey:key,Authorization:`Bearer ${accessToken}`},cache:"no-store"});
 if(!opResponse.ok)return null;
 const rows:unknown=await opResponse.json();
 if(!Array.isArray(rows)||rows.length!==1||!record(rows[0])||rows[0].is_active!==true||
    (rows[0].role!=="operator"&&rows[0].role!=="admin"))return null;
 return{userId:user.id,email:user.email,role:rows[0].role};
}
