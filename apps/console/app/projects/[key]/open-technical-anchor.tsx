"use client";
import {useEffect} from "react";
/** Preserve deep-link access to readonly technical evidence without leaving
 * thousands of technical rows expanded in the ordinary product experience. */
const keys=new Set(["project-control","product-readiness","databases","github-access","preview-policy","latest-request","repository-setup"]);
export function OpenProjectTechnicalAnchor(){
 useEffect(()=>{
  const reveal=()=>{
   const key=window.location.hash.slice(1);
   if(!keys.has(key))return;
   const node=document.getElementById(key);
   const root=node?.closest("details.projectDetailTechnicalDisclosure");
   if(root instanceof HTMLDetailsElement){
    root.open=true;
    const inner=node?.closest("details.projectIntegrations");
    if(inner instanceof HTMLDetailsElement)inner.open=true;
   }
  };
  reveal();
  window.addEventListener("hashchange",reveal);
  return()=>window.removeEventListener("hashchange",reveal);
 },[]);
 return null;
}
