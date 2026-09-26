import {NextResponse} from "next/server";

export function GET(){
 const commit=process.env.VERCEL_GIT_COMMIT_SHA?.slice(0,12)||null;
 return NextResponse.json({status:"ok",service:"ai-product-factory-console",commit});
}
