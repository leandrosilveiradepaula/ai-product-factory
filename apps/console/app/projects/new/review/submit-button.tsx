"use client";

import {useFormStatus} from "react-dom";

export function SubmitProjectButton({existing}:{existing:boolean}) {
 const {pending}=useFormStatus();
 return <button type="submit" className="primary" disabled={pending} aria-disabled={pending} aria-busy={pending}>
  {pending ? "Cadastrando projeto..." : existing ? "Cadastrar projeto existente" : "Cadastrar projeto"}
 </button>;
}
