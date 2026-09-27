"use client";
import {useActionState,useState} from "react";
import {Button} from "../../ui";
import {submitIntake,type IntakeState} from "./actions";

const initial:IntakeState={errors:{}};

export function IntakeForm(){
 const[state,action,pending]=useActionState(submitIntake,initial);
 const[mode,setMode]=useState<"greenfield"|"import">("greenfield");
 return <form action={action} className="form card intakeForm">
  <div className="mode"><button type="button" className={mode==="greenfield"?"selected":""} onClick={()=>setMode("greenfield")}>Novo produto</button><button type="button" className={mode==="import"?"selected":""} onClick={()=>setMode("import")}>Projeto existente</button></div>
  <input type="hidden" name="mode" value={mode}/>

  <div className="intakePrompt">
   <label>O que você quer construir?
    <textarea name="summary" rows={9} autoFocus placeholder="Conte para a Factory como você contaria para uma equipe: qual problema quer resolver, para quem, o resultado esperado e qualquer contexto importante."/>
   </label>
   {state.errors.summary&&<small>{state.errors.summary}</small>}
   <p className="muted intakeHint">Você não precisa escolher stack, agentes ou modelos. A Factory usa este pedido como origem do Discovery.</p>
  </div>

  <div className="twoCol">
   <div><label>Nome do projeto<input name="name" placeholder="Ex.: Portal de Atendimento"/></label>{state.errors.name&&<small>{state.errors.name}</small>}</div>
   {mode==="import"?<div><label>Repositório GitHub<input name="repository" placeholder="owner/repository"/></label>{state.errors.repository&&<small>{state.errors.repository}</small>}</div>:<div><label>Quem vai usar?<input name="users" placeholder="Ex.: equipe comercial e clientes"/></label></div>}
  </div>

  {mode==="greenfield"?<label>Quem vai usar? <span className="muted">(opcional)</span><textarea name="users" rows={2}/></label>:null}
  <label>O que é obrigatório? <span className="muted">(opcional)</span><textarea name="mustHave" rows={3} placeholder="Regras, funcionalidades ou restrições que não podem faltar."/></label>
  <label>Integrações já conhecidas <span className="muted">(opcional)</span><textarea name="integrations" rows={2} placeholder="Ex.: Supabase, SAP, n8n, Vercel..."/></label>
  <label>Referências <span className="muted">(opcional)</span><textarea name="references" rows={3} placeholder={"Uma URL por linha. Pode incluir Figma, documentação, site de referência etc.\nhttps://www.figma.com/design/..."}/></label>
  <div className="intakeAttachments">
   <strong>Anexos</strong>
   <span className="muted">Arquivos serão adicionados na próxima etapa desta implementação. URLs e Figma já podem seguir com o intake sem expor credenciais ao navegador.</span>
  </div>
  <Button variant="primary" disabled={pending}>{pending?"Preparando Discovery...":"Revisar e iniciar Discovery"}</Button>
 </form>;
}