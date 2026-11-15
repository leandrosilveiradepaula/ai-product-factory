import {NextResponse} from "next/server";
import {requireConsoleOperator} from "../../../../lib/auth-server";
import {getRunExistenceForOperator} from "../../../../lib/control-plane";

export const dynamic="force-dynamic";
// This endpoint exposes status only, never run contents or tenant data.
const RUN_ID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const noStore={"Cache-Control":"no-store"};

export async function GET(_request:Request,{params}:{params:Promise<{id:string}>}){
 await requireConsoleOperator();
 const {id}=await params;
 if(!RUN_ID.test(id))
  return NextResponse.json({status:"not_found"},{status:404,headers:noStore});
 try{
  const exists=await getRunExistenceForOperator(id);
  return NextResponse.json({status:exists?"ok":"not_found"},{status:exists?200:404,headers:noStore});
 }catch{
  // Backend failure is not evidence that a run does not exist.
  return NextResponse.json({status:"unavailable"},{status:503,headers:noStore});
 }
}
