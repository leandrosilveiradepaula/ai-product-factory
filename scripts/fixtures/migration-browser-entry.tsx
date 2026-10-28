/* Local-only interactive proof, NOT a Next route or migration executor.
 * Imports the real production React components without production credentials. */
import React,{useState} from "react";
import {createRoot} from "react-dom/client";
import {GateDecisionPending} from "../../apps/console/app/gates/gate-decision-form";
import {GateActionSuccessBanner} from "../../apps/console/app/gates/gate-action-success-banner";
import {GateActionErrorBanner} from "../../apps/console/app/gates/gate-action-error-banner";
import {ConfirmSubmit} from "../../apps/console/app/confirm-submit";

type Completion="verified"|"already_applied"|"missing_evidence"|"failed";
const GATE="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa";
const MIGRATION="20261026010101_controlled_offline_only";
let submissions=0;
let resolver:((result:Completion)=>void)|null=null;

declare global {
 interface Window {
  __factoryMigrationProof?:{
   complete:(result:Completion)=>void;
   submissions:()=>number;
   hasPending:()=>boolean;
  };
 }
}
window.__factoryMigrationProof={
 complete(result) {
  if(!resolver)throw new Error("No pending local-only action");
  const finish=resolver;resolver=null;finish(result);
 },
 submissions:()=>submissions,
 hasPending:()=>resolver!==null,
};
function App(){
 const [success,setSuccess]=useState<null|{migrationName:string;alreadyApplied:boolean}>(null);
 const [error,setError]=useState<null|string>(null);
 async function applyMigrationOffline(){
  submissions++;
  setSuccess(null);
  setError(null);
  const result=await new Promise<Completion>(resolve=>{resolver=resolve;});
  if(result==="verified"||result==="already_applied"){
   // Simulate ONLY the post-authorization redirect once a verified result is
   // supplied by the controlled server fixture. No Supabase API is called.
   window.history.pushState(window.history.state,"",
     "/gates?migration_result="+GATE+"&tab=controlled#focus");
   setSuccess({migrationName:MIGRATION,alreadyApplied:result==="already_applied"});
  }else{
   setError(result==="missing_evidence"
    ?"Nenhuma evidência durável foi verificada. O gate permanece pendente."
    :"Falha controlada na operação. Nenhuma migration foi executada.");
  }
 }
 return <main className="main" id="main-content">
  <h1>Decisão administrativa — ambiente isolado</h1>
  <section className="gateLayout">
   <article className="card gateCard pending">
    <h2>Aplicação de migration — prova de interface sem banco</h2>
    <form action={applyMigrationOffline}>
     <GateDecisionPending pendingMessage="Aplicando a migration e verificando o histórico no Supabase. Não envie a operação novamente.">
      <div className="gatePendingStatus" role="status">A aplicação real exigiria um gate humano autorizado. Este formulário é um teste local controlado.</div>
      <div className="gateActionBar">
       <ConfirmSubmit className="primary" confirmMessage="Confirmar a operação de teste isolado? Nenhum banco será alterado.">
        Aplicar migration em produção
       </ConfirmSubmit>
      </div>
     </GateDecisionPending>
    </form>
    {success?<GateActionSuccessBanner migrationName={success.migrationName} alreadyApplied={success.alreadyApplied}/>:null}
    {error?<GateActionErrorBanner message={error}/>:null}
   </article>
  </section>
 </main>;
}
const container=document.getElementById("root");
if(!container)throw new Error("Missing isolated fixture mount");
createRoot(container).render(<App/>);
