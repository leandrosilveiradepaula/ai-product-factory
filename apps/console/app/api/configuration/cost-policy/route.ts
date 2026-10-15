import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../lib/auth-server";
import {updatePrimaryCostPolicy} from "../../../../lib/primary-cost-policy";

export async function POST(request:Request){
 await requireConsoleAdmin();
 const url=new URL(request.url);
 const origin=request.headers.get("origin");
 if(!origin||origin!==url.origin)
  return NextResponse.json({error:"invalid origin"},{status:403});
 const contentType=request.headers.get("content-type")||"";
 if(!contentType.startsWith("application/x-www-form-urlencoded"))
  return NextResponse.json({error:"invalid content type"},{status:415});
 const body=await request.formData();
 const version=String(body.get("version")||"");
 const budgetUsd=String(body.get("budget_usd")||"");
 const reserveUsd=String(body.get("reserve_usd")||"");
 const reason=String(body.get("reason")||"");
 const confirmed=body.get("confirm") === "true";
 if(!/^[1-9][0-9]{0,8}$/.test(version))
  return NextResponse.json({error:"invalid version"},{status:400});
 let status="saved";
 try{
  await updatePrimaryCostPolicy({
   version:Number(version),budgetUsd,reserveUsd,reason,confirmed,
  });
 }catch(error){
  // Do not leak backend credentials or PostgREST responses into the URL.
  status=error instanceof Error&&error.message.includes("outro administrador")
   ?"stale":"failed";
 }
 return NextResponse.redirect(
  new URL("/configuration?cost_policy="+encodeURIComponent(status)+"#orcamento",url.origin),
  303,
 );
}
