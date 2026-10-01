"use client";

import type {ButtonHTMLAttributes,MouseEvent} from "react";

type Props=ButtonHTMLAttributes<HTMLButtonElement>&{confirmMessage:string};

export function ConfirmSubmit({confirmMessage,onClick,...props}:Props){
 function handleClick(event:MouseEvent<HTMLButtonElement>){
  onClick?.(event);
  if(event.defaultPrevented)return;
  if(!window.confirm(confirmMessage))event.preventDefault();
 }
 return <button {...props} onClick={handleClick}/>;
}
