import {ConfirmSubmit} from "../confirm-submit";
import {StatusPill} from "../ui";
import type {PrimaryCostPolicyView} from "../../lib/primary-cost-policy";

const money=(value:number)=>new Intl.NumberFormat("pt-BR",{
 style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:4,
}).format(value);

export function PrimaryCostPolicyPanel({
 policy,admin,feedback,
}:{policy:PrimaryCostPolicyView|null;admin:boolean;feedback?:string}){
 if(!policy)return <div className="card" id="orcamento">
  <div className="panelHeading"><strong>Orçamento e custos</strong><StatusPill status="blocked" label="configuração indisponível"/></div>
  <p className="muted">A política financeira ainda não está disponível no Control Plane.
  A aplicação não assume valores fixos nem autoriza uso pago sem uma política válida.
  Aguarde a migração administrativa e a verificação do banco.</p>
 </div>;
 const spent=policy.knownSpendUsd;
 const remaining=spent==null?null:policy.budgetUsd-spent;
 const unknown=policy.unknownPaidCostEvents;
 const blocked=remaining==null||unknown==null||unknown>0||remaining<policy.reserveUsd;
 return <div className="card" id="orcamento">
  <div className="panelHeading"><strong>Orçamento e custos · modelo principal</strong>
   <StatusPill status={blocked?"blocked":"healthy"} label={blocked?"uso pago bloqueado ou não verificável":"dentro do limite interno"}/></div>
  <div className="configRows">
   <div><span>Teto total da Factory</span><strong>{money(policy.budgetUsd)}</strong>
    <small>limite interno acumulado; não representa créditos disponíveis na OpenAI</small></div>
   <div><span>Reserva por chamada</span><strong>{money(policy.reserveUsd)}</strong></div>
   <div><span>Consumo conhecido no Control Plane</span><strong>{spent===null?"indisponível":money(spent)}</strong></div>
   <div><span>Saldo do teto interno</span><strong>{remaining===null?"indisponível":money(remaining)}</strong>
    <small>o provedor aplica separadamente seus limites, cobranças e quotas</small></div>
   <div><span>Custos pagos desconhecidos</span><strong>{unknown===null?"indisponível":unknown}</strong>
    <small>qualquer evento não mensurável bloqueia novas chamadas</small></div>
   <div><span>Versão da política</span><strong>v{policy.version}</strong>
    <small>última atualização: {new Date(policy.updatedAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"})}</small></div>
  </div>
  {feedback==="saved"?<p role="status">Orçamento salvo com auditoria. Próximos workers lerão a política atual.</p>:null}
  {feedback==="stale"?<p role="alert">A versão mudou. Recarregue a tela antes de tentar novamente.</p>:null}
  {feedback==="failed"?<p role="alert">Alteração recusada. Confira os valores, a justificativa e seu acesso de administrador.</p>:null}
  <section aria-label="Últimas alterações financeiras">
   <h3>Histórico de alterações (últimas 20)</h3>
   {policy.history===null?<p className="muted" role="status">Histórico indisponível. Não é possível confirmar as alterações anteriores.</p>
    :policy.history.length===0?<p className="muted">Nenhuma alteração administrativa após a configuração inicial.</p>
    :<div className="tableWrap"><table>
      <thead><tr><th>Data</th><th>Administrador</th><th>Teto</th><th>Reserva</th><th>Justificativa</th></tr></thead>
      <tbody>{policy.history.map(entry=><tr key={entry.version}>
       <td>{new Date(entry.createdAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"})}</td>
       <td><code>{entry.actorRef}</code></td>
       <td>{money(entry.previousBudgetUsd)} → {money(entry.newBudgetUsd)}</td>
       <td>{money(entry.previousReserveUsd)} → {money(entry.newReserveUsd)}</td>
       <td>{entry.reason}</td>
      </tr>)}</tbody>
     </table></div>}
  </section>
  {admin?<form method="POST" action="/api/configuration/cost-policy" className="gateForm">
   <input type="hidden" name="version" value={policy.version}/>
   <label>Teto total interno (US$)
    <input name="budget_usd" type="number" min="0.01" max="100000" step="0.0001" required defaultValue={policy.budgetUsd.toFixed(2)}/>
   </label>
   <label>Reserva por execução paga (US$)
    <input name="reserve_usd" type="number" min="0.0001" step="0.0001" required defaultValue={policy.reserveUsd.toFixed(2)}/>
   </label>
   <label>Justificativa da alteração
    <textarea name="reason" required minLength={12} maxLength={300} rows={3}
     placeholder="Explique a decisão de custo e seu objetivo operacional"/>
   </label>
   <label>
    <input type="checkbox" name="confirm" value="true" required/>
    Confirmo expressamente esta alteração de limite financeiro interno.
    Sei que ela não compra créditos na OpenAI e não autoriza merge automático.
   </label>
   <div className="actions">
    <ConfirmSubmit className="primary" type="submit"
     confirmMessage="Confirma atualizar a política financeira da Factory? A nova configuração passará a valer para as próximas execuções pagas, com auditoria da decisão.">
     Salvar política financeira
    </ConfirmSubmit>
   </div>
  </form>:<p className="muted">Somente administradores podem alterar estes limites. A consulta é somente leitura.</p>}
 </div>;
}
