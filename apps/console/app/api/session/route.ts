import {NextResponse} from "next/server";
import {requireConsoleOperator} from "../../../lib/auth-server";

export const dynamic="force-dynamic";

// This endpoint deliberately exposes only the caller's own effective role.
// It is used by the authenticated evidence workflow to bind a browser session
// to the server-side RBAC decision before it probes an administrator route.
export async function GET(){
 const operator=await requireConsoleOperator();
 return NextResponse.json({status:"ok",role:operator.role},{headers:{"Cache-Control":"no-store"}});
}
