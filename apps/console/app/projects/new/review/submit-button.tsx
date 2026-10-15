"use client";

import {useFormStatus} from "react-dom";

export function SubmitProjectButton({existing}:{existing:boolean}) {
 const {pending}=useFormStatus();
 return <button type="submit" className="primary" disabled={pending} aria-disabled={pending} aria-busy={pending}>
  {pending ? "Criando projeto e iniciando Descoberta..." : existing ? "Importar e iniciar reconciliação" : "Criar projeto e iniciar Descoberta"}
 </button>;
}
