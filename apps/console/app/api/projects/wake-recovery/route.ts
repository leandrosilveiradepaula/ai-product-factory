import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../lib/auth-server";
import {recoverPendingProjectWake} from "../../../../lib/intake-worker-recovery";

export async function POST(request:Request){
 const admin=await requireConsoleAdmin();
 const url=new URL(request.url);
 const origin=request.headers.get("origin");
 if(!origin||origin!==url.origin)return NextResponse.json({error:"invalid origin"},{status:403});
 const type=request.headers.get("content-type")||"";
 if(!type.startsWith("application/x-www-form-urlencoded"))return NextResponse.json({error:"invalid content type"},{status:415});
 const form=await request.formData();
 const project=String(form.get("project_key")||"");
 if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(project))return NextResponse.json({error:"invalid project"},{status:400});
 let status="unavailable";
 try{status=(await recoverPendingProjectWake(project,admin.userId)).status;}
 catch{status="unavailable";}
 return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(project)+"?wake_recovery="+encodeURIComponent(status),url.origin),303);
}
