"use client";
import {useActionState,useState} from "react";
import {Button} from "../../ui";
import type {ProjectIntake} from "../../../lib/intake";
import {submitIntake,type IntakeState} from "./actions";

export type IntakeFormInitial=ProjectIntake&{draftId?:string;attachmentCount?:number};
const initialState:IntakeState={errors:{}};

export function IntakeForm({initial}:{initial?:IntakeFormInitial}){
 const [state,action,pending]=useActionState(submitIntake,initialState);
 const [mode,setMode]=useState<"greenfield"|"existing">(initial?.mode||"greenfield");
 const existing=mode==="existing";
 const references=(initial?.references||[]).map(x=>x.value).join("\n");
 const hasAdditionalContext=Boolean(initial?.knownPending||initial?.constraints||initial?.mustHave||initial?.integrations||references||initial?.attachmentCount);
 return <form action={action} className="form card intakeForm" encType="multipart/form-data">
  <div className="mode" role="group" aria-label="Tipo de projeto">
   <button type="button" className={!existing?"selected":""} aria-pressed={!existing} onClick={()=>setMode("greenfield")}>Novo produto</button>
   <button type="button" className={existing?"selected":""} aria-pressed={existing} onClick={()=>setMode("existing")}>Projeto em andamento</button>
  </div>
  <input type="hidden" name="mode" value={mode}/>
  {initial?.draftId?<input type="hidden" name="draft_id" value={initial.draftId}/>:null}

  <div className="intakePrompt">
   <label>{existing?"O que já existe e o que você quer concluir ou mudar?":"O que você quer construir?"}
    <textarea name="summary" rows={6} required defaultValue={initial?.summary||""} placeholder={existing?"Conte o que já funciona, o que falta e qual resultado você deseja alcançar.":"Descreva o problema, para quem é o produto e qual resultado você espera."}/>
   </label>
   {state.errors.summary?<small role="alert">{state.errors.summary}</small>:null}
   <p className="muted intakeHint">{existing?"A Factory vai reconciliar código, documentação e infraestrutura antes de continuar.":"Não é necessário escolher stack, agentes nem modelos para iniciar."}</p>
  </div>

  <div className="twoCol intakeEssentials">
   <div>
    <label>Nome do projeto<input name="name" required defaultValue={initial?.name||""} placeholder="Ex.: Portal de Atendimento"/></label>
    {state.errors.name?<small role="alert">{state.errors.name}</small>:null}
   </div>
   {existing?<div>
    <label>Repositório GitHub <span className="muted">(se existir)</span><input name="repository" defaultValue={initial?.repository||""} placeholder="owner/repository"/></label>
    {state.errors.repository?<small role="alert">{state.errors.repository}</small>:null}
   </div>:<div>
    <label>Quem vai usar? <span className="muted">(opcional)</span><textarea name="users" rows={2} defaultValue={initial?.users||""} placeholder="Ex.: equipe de atendimento e clientes"/></label>
   </div>}
  </div>

  {existing?<label>Em que estágio você acredita que está?<select name="reportedStage" defaultValue={initial?.reportedStage||"unknown"}>
   <option value="unknown">Não sei / quero que a Factory descubra</option>
   <option value="discovery">Descoberta</option><option value="specification">Especificação</option>
   <option value="planning">Planejamento</option><option value="implementation">Implementação</option>
   <option value="review">Revisão</option><option value="validation">Testes / Avaliações</option>
   <option value="preview">Prévia</option><option value="operations">Já está em operação</option>
  </select></label>:null}

  <details className="intakeOptional" open={hasAdditionalContext}>
   <summary>Detalhes adicionais, referências e anexos <span className="muted">(opcional)</span></summary>
   <div className="intakeOptionalBody">
    {existing?<><label>Pendências que você já conhece<textarea name="knownPending" rows={3} defaultValue={initial?.knownPending||""} placeholder="Ex.: autenticação incompleta, tela pendente, CI quebrado..."/></label>
     <label>O que não pode ser alterado?<textarea name="constraints" rows={3} defaultValue={initial?.constraints||""} placeholder="Regras de negócio, arquitetura ou integrações a preservar."/></label>
    </>:<label>O que é obrigatório?<textarea name="mustHave" rows={3} defaultValue={initial?.mustHave||""} placeholder="Funcionalidades, regras e restrições que não podem faltar."/></label>}
    <label>Integrações já conhecidas<textarea name="integrations" rows={2} defaultValue={initial?.integrations||""} placeholder="Ex.: Supabase, SAP, n8n, Vercel..."/></label>
    <label>Referências<textarea name="references" rows={3} defaultValue={references} placeholder={"Uma URL por linha. Pode incluir Figma, documentação, site de referência etc.\nhttps://www.figma.com/design/..."}/></label>
    <div className="intakeAttachments">
     <strong>Anexos</strong>
     {initial?.attachmentCount?<span className="muted">{initial.attachmentCount} arquivo(s) já preservado(s) neste rascunho.</span>:null}
     <input name="attachments" type="file" multiple accept=".pdf,.txt,.md,.csv,.json,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp"/>
     <span className="muted">Até 10 arquivos, 10 MB cada. PDF, Office, texto, CSV/JSON e imagens. Upload privado pelo servidor.</span>
     {state.errors.attachments?<small role="alert">{state.errors.attachments}</small>:null}
    </div>
   </div>
  </details>

  <div className="intakeSubmit">
   <p className="muted">Você revisará o resumo antes de criar o projeto ou solicitar qualquer execução.</p>
   <Button variant="primary" disabled={pending}>{pending?(existing?"Preparando reconciliação...":"Preparando Descoberta..."):(existing?"Revisar e importar projeto":"Revisar e iniciar Descoberta")}</Button>
  </div>
 </form>;
}
