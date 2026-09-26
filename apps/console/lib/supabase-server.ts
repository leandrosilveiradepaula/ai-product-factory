export type SupabaseServerConfig={url:string;key:string;headers:Record<string,string>};

export function getSupabaseServerConfig():SupabaseServerConfig|null{
 const url=process.env.SUPABASE_URL;
 const key=process.env.SUPABASE_SECRET_KEY||process.env.SUPABASE_SERVICE_ROLE_KEY;
 if(!url||!key)return null;
 const headers:Record<string,string>={apikey:key};
 if(!key.startsWith("sb_secret_"))headers.Authorization=`Bearer ${key}`;
 return{url,key,headers};
}
