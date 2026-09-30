"use server";
import {redirect} from "next/navigation";
import {clearAuthCookies,setAuthCookies} from "../lib/auth-server";
import {signInPassword} from "../lib/auth-api";

function safeNext(value:string){
 if(!value.startsWith("/")||value.startsWith("//"))return "/";
 return value;
}

export async function signInAction(formData:FormData){
 const email=String(formData.get("email")||"").trim();
 const password=String(formData.get("password")||"");
 const next=safeNext(String(formData.get("next")||"/"));
 if(!email||!password)redirect("/login?error=missing&next="+encodeURIComponent(next));
 try{
  const session=await signInPassword(email,password);
  await setAuthCookies(session);
 }catch{
  redirect("/login?error=invalid&next="+encodeURIComponent(next));
 }
 redirect(next);
}

export async function signOutAction(){await clearAuthCookies();redirect("/login");}
