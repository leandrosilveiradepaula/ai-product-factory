import {ConfirmSubmit} from "../confirm-submit";
import {StatusPill} from "../ui";
import type {PrimaryCostPolicyView} from "../../lib/primary-cost-policy";

const money=(value:number)=>new Intl.NumberFormat("pt-BR",{
 style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:4,
}).format(value);

export function PrimaryCostPolicyPanel({
 policy,admin,feedback,
}:{policy:PrimaryCostPolicyView|null;admin:boolean;feedback?:string}){
 if(!policy)return <section className="card primaryCostPanel" id="orcamento"
  aria-labelledby="cost-heading">
  <header className="primaryCostHeader">
   <div><span className="primaryCostKicker">CONTROLE FINANCEIRO</span>
    <h2 id="cost-heading">Orçamento e custos</h2></div>
   <StatusPill status="blocked" label="Indisponível"/>
  </header>
  <p role="alert" className="primaryCostAlert">Não foi possível consultar a política financeira atual.
   O uso pago permanece bloqueado até a verificação do Control Plane.</p>
 </section>;

 const spent=policy.knownSpendUsd;
 const remaining=spent===null?null:policy.budgetUsd-spent;
 const unknown=policy.unknownPaidCostEvents;
 const unverifiable=remaining===null||unknown===null;
 const unknownPaid=!unverifiable&&unknown>0;
 const shortfall=!unverifiable&&!unknownPaid&&remaining<policy.reserveUsd
   ?Math.max(0,policy.reserveUsd-remaining):0;
 const blocked=unverifiable||unknownPaid||shortfall>0;
 const statusLabel=unverifiable?"Custo não verificável"
   :unknownPaid?"Custo desconhecido"
   :shortfall>0?"Reserva insuficiente":"Dentro do limite";

 return <section className="card primaryCostPanel" id="orcamento"
  aria-labelledby="cost-heading">
  <header className="primaryCostHeader">
   <div><span className="primaryCostKicker">CONTROLE FINANCEIRO</span>
    <h2 id="cost-heading">Orçamento e custos</h2>
    <p>Defina quanto a Factory pode consumir nas execuções pagas.</p></div>
   <StatusPill status={blocked?"blocked":"healthy"} label={statusLabel}/>
  </header>

  {shortfall>0?<div className="primaryCostAlert" role="status">
   <strong>Execuções pagas interrompidas por limite financeiro</strong>
   <p>O saldo interno é menor que a reserva exigida. Faltam <strong>{money(shortfall)}</strong> para atender
    à reserva atual. Isso não comprova disponibilidade de créditos ou quota no provedor.</p>
  </div>:unverifiable||unknownPaid?<div className="primaryCostAlert" role="alert">
   <strong>Não é seguro iniciar chamadas pagas</strong>
   <p>{unverifiable?"O consumo ou a política não puderam ser verificados integralmente."
     :"Existem eventos pagos sem custo conhecido."} Confira os registros antes de alterar limites.</p>
  </div>:<p className="primaryCostHealthy" role="status">
   O saldo interno cobre a reserva configurada. A quota do provedor é verificada separadamente.
  </p>}

  {feedback==="saved"?<p className="primaryCostFeedback" role="status">
   Limite salvo com auditoria. Novas execuções usarão a política atual.</p>:null}
  {feedback==="stale"?<p className="primaryCostFeedback primaryCostFeedbackError" role="alert">
   Outro administrador alterou a política. Atualize a página antes de salvar.</p>:null}
  {feedback==="failed"?<p className="primaryCostFeedback primaryCostFeedbackError" role="alert">
   A alteração foi recusada. Verifique os valores, a justificativa e a permissão de administrador.</p>:null}

  <div className="primaryCostBody">
   <div className="primaryCostSnapshot">
    <h3>Situação atual</h3>
    <dl className="primaryCostMetrics">
     <div><dt>Teto total da Factory</dt><dd>{money(policy.budgetUsd)}</dd></div>
     <div><dt>Consumido</dt><dd>{spent===null?"Indisponível":money(spent)}</dd></div>
     <div><dt>Saldo do teto interno</dt><dd>{remaining===null?"Indisponível":money(Math.max(0,remaining))}</dd></div>
     <div><dt>Reserva por execução paga</dt><dd>{money(policy.reserveUsd)}</dd></div>
    </dl>
    <p className="primaryCostNote">Este é um limite interno acumulado, não o saldo de créditos
     disponíveis na OpenAI. Alterar o teto não compra créditos nem autoriza produção.</p>
    {unknown!==null&&unknown>0?<p className="primaryCostNote" role="alert">
     Eventos pagos com custo desconhecido: {unknown}. O controle continua fechado.</p>:null}
   </div>

   <div className="primaryCostEditor">
    <h3>{admin?"Alterar limite interno":"Atualização financeira"}</h3>
    {admin?<form method="POST" action="/api/configuration/cost-policy"
       className="gateForm primaryCostForm">
     <input type="hidden" name="version" value={policy.version}/>
     <label>Novo teto total (US$)
      <input name="budget_usd" type="number" min="0.01" max="100000"
       step="0.0001" required defaultValue={policy.budgetUsd.toFixed(2)}/>
     </label>
     <label>Reserva por execução (US$)
      <input name="reserve_usd" type="number" min="0.0001" step="0.0001"
       required defaultValue={policy.reserveUsd.toFixed(2)}/>
     </label>
     <label>Justificativa
      <textarea name="reason" required minLength={12} maxLength={300} rows={3}
       placeholder="Explique o motivo e o limite financeiro autorizado"/>
     </label>
     <label className="primaryCostConfirm">
      <input type="checkbox" name="confirm" value="true" required/>
      <span>Confirmo expressamente esta alteração de limite financeiro interno.
       Sei que ela não compra créditos na OpenAI e não autoriza merge automático.</span>
     </label>
     <ConfirmSubmit className="primaryCostSave primary" type="submit"
      confirmMessage="Confirma atualizar a política financeira da Factory? A nova configuração passará a valer para as próximas execuções pagas, com auditoria da decisão.">
      Salvar limite
     </ConfirmSubmit>
    </form>:<p className="primaryCostNote">Somente administradores autorizados podem alterar
      o limite. Esta consulta não muda o orçamento.</p>}
   </div>
  </div>

  <details className="primaryCostHistory">
   <summary>Histórico de alterações (últimas 20)</summary>
   <p className="primaryCostNote">Política v{policy.version} · Atualizada em {
    new Date(policy.updatedAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"})}</p>
   {policy.history===null?<p className="primaryCostNote" role="status">
    Histórico indisponível. Não é possível confirmar as alterações anteriores.</p>
   :policy.history.length===0?<p className="primaryCostNote">
    Nenhuma alteração administrativa após a configuração inicial.</p>
   :<div className="tableWrap"><table>
    <thead><tr><th>Data</th><th>Administrador</th><th>Teto</th>
     <th>Reserva</th><th>Justificativa</th></tr></thead>
    <tbody>{policy.history.map(entry=><tr key={entry.version}>
     <td>{new Date(entry.createdAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"})}</td>
     <td><code>{entry.actorRef}</code></td>
     <td>{money(entry.previousBudgetUsd)} → {money(entry.newBudgetUsd)}</td>
     <td>{money(entry.previousReserveUsd)} → {money(entry.newReserveUsd)}</td>
     <td>{entry.reason}</td>
    </tr>)}</tbody>
   </table></div>}
  </details>
 </section>;
}
