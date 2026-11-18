import type {ProductSituation} from "./product-status";
export type ProductFinding={label:string;value:string;kind:"confirmed"|"pending"|"missing"};
export type ProductStep={title:string;detail:string;owner:"Factory"|"Equipe técnica"|"Operador, se houver gate";href:string;cta:string};
export type ProductDiagnosis={
 status:"assessed"|"blocked"|"unverified"|"stopped";
 headline:string;summary:string;
 findings:ProductFinding[];steps:ProductStep[];
};
export function diagnoseProduct(item:ProductSituation):ProductDiagnosis{
 const ready=item.proof?.productReady===true;
 const stopped=!item.isActive||["stopped","paused","pausing","stopping"].includes(item.controlState);
 const blocked=item.state==="investigate"&&Boolean(item.blocker);
 const db=item.databaseEvidence;
 const base="/projects/"+encodeURIComponent(item.key);
 const findings:ProductFinding[]=[
  {
   label:"Código e integração",
   value:item.proof?.hasHumanMerge?"Merge humano registrado":"Sem integração comprovada neste relatório",
   kind:item.proof?.hasHumanMerge?"confirmed":"pending",
  },
  {
   label:"Banco no inventário da Factory",
   value:db?.state==="verified"?"Vínculo somente leitura verificado":db?.state==="pending"?"Vínculo aguardando verificação":"Nenhum vínculo registrado (não significa ausência de banco)",
   kind:db?.state==="verified"?"confirmed":"pending",
  },
  {
   label:"Uso real do produto",
   value:ready?"Completude avaliada para a versão registrada":"Ainda sem aceite funcional completo",
   kind:ready?"confirmed":"missing",
  },
 ];
 if(item.requirementCount>0)findings.push({
  label:"Requisitos rastreáveis",
  value:item.requirementCount+" cadastrados; evidência de código não substitui uso real",
  kind:"confirmed",
 });
 const steps:ProductStep[]=[];
 if(item.state==="decision")steps.push({
  title:"Revisar uma decisão que depende de você",
  detail:"Há um gate humano real. Consulte a solicitação, impacto e evidências antes de autorizar o próximo passo.",
  owner:"Operador, se houver gate",href:"/gates",cta:"Revisar decisão",
 });
 if(!ready&&!stopped&&item.projectKind==="greenfield"&&db?.state!=="verified")
  steps.push({
   title:"Conferir o banco dedicado e a conexão",
   detail:"Verificar o banco que já exista, seu schema, permissões e vínculo com a Factory. Falta de vínculo neste inventário não significa que o banco não tenha sido criado.",
   owner:"Equipe técnica",href:base+"#databases",cta:"Ver situação do banco",
  });
 if(blocked&&item.blocker&&item.lastRun)
  steps.push({
   title:item.blocker.title,
   detail:item.blocker.resolution,
   owner:"Factory",href:"/runs/"+item.lastRun.id,cta:"Ver causa da interrupção",
  });
 if(!ready&&!stopped)
  steps.push({
   title:"Validar o fluxo com usuários autenticados",
   detail:"Comprovar na aplicação hospedada o caminho principal, incluindo criação, revisão, persistência e resultado final exigidos no escopo. Testes isolados e a tela de login não bastam.",
   owner:"Equipe técnica",href:base+"#product-readiness",cta:"Consultar evidências",
  });
 if(!ready&&!stopped&&item.specStatus&&item.specStatus!=="approved")
  steps.push({
   title:"Conferir escopo e aceite do produto",
   detail:"A especificação mais recente ainda não está aprovada. Reconciliar o pedido original e os requisitos cadastrados antes de declarar entrega concluída.",
   owner:"Factory",href:item.sourceIssueUrl||base+"#product-readiness",cta:"Ver escopo de origem",
  });
 if(stopped)steps.push({
  title:"Projeto fora de execução",
  detail:"O cadastro não autoriza novas tarefas. Retomar exige comando legítimo e não significa que os resultados antigos estejam prontos.",
  owner:"Operador, se houver gate",href:base+"#project-control",cta:"Ver controle",
 });
 if(ready)steps.push({
  title:"Acompanhar a versão avaliada",
  detail:"O relatório de prontidão cobre uma versão específica; novos commits exigem verificação própria.",
  owner:"Factory",href:base+"#product-readiness",cta:"Consultar auditoria",
 });
 const status=ready?"assessed":stopped?"stopped":blocked?"blocked":"unverified";
 const headline=ready?"Entrega avaliada na versão registrada":stopped?"Projeto sem execução autorizada":blocked?"Produto ainda não entregue; trabalho bloqueado":item.proof?.hasHumanMerge?"Código integrado, produto não validado":"Entrega do produto ainda não comprovada";
 const summary=ready?"Existe uma avaliação registrada para o candidato indicado. Isso não aprova futuras alterações.":stopped?"Este projeto não está executando novos trabalhos. O histórico permanece disponível.":blocked?
  "A integração anterior não concluiu a jornada do usuário e a correção mais recente foi interrompida. A Factory precisa resolver pendências reais antes de chamar o produto de pronto.":
  "Há registros de trabalho, mas ainda falta comprovar a operação de ponta a ponta. A próxima ação não é publicar apenas porque o build passou.";
 return {status,headline,summary,findings,steps};
}
