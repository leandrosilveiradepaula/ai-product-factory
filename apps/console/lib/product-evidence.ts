/** Read-only, source-bound claims about delivered product vs integrated code.
 * NEVER use lifecycle_stage, a successful build, merge or Vercel READY as proof
 * of product completeness. Missing evidence remains missing.
 */
export type ProductProof={
 releaseStatus:string|null;
 productComplete:boolean|null;
 productReady:boolean|null;
 hasHumanMerge:boolean;
 hasPreviewRecord:boolean;
 hasProductionDeployment:boolean;
 certificationSha:string|null;
 releaseCandidateSha:string|null;
 headline:string;
 explanation:string;
};
export type ProductProofInput={
 releaseStatus?:string|null;
 productComplete?:unknown;
 productReadinessReady?:unknown;
 definitionReady?:unknown;
 mergeSha?:unknown;
 hasPreviewRecord?:boolean;
 hasProductionDeployment?:boolean;
 certificationSha?:string|null;
 releaseCandidateSha?:string|null;
};
export function assessProductProof(input:ProductProofInput):ProductProof{
 const complete=typeof input.productComplete==="boolean"?input.productComplete:null;
 const ready=typeof input.productReadinessReady==="boolean"?input.productReadinessReady:null;
 const hasHumanMerge=typeof input.mergeSha==="string"&&/^[0-9a-f]{40}$/.test(input.mergeSha);
 const preview=Boolean(input.hasPreviewRecord);
 const production=Boolean(input.hasProductionDeployment);
 // Even explicit claims to both fields need matching, independent,
 // current candidate certification; a historical 19/19 is not transferable.
 const matchingCert=Boolean(input.certificationSha&&input.releaseCandidateSha&&input.certificationSha===input.releaseCandidateSha);
 const independentlyReady=complete===true&&ready===true&&input.definitionReady===true&&matchingCert&&production;
 let headline:string,explanation:string;
 if(independentlyReady){
  headline="Evidências de produto completo registradas";
  explanation="Existe certificação associada à versão do relatório e implantação de produção. Confira o produto antes de considerar uma nova alteração.";
 }else if(complete===false||ready===false){
  headline="Produto completo não comprovado";
  explanation=(hasHumanMerge?"Houve integração de código, mas ":"")+
   "o relatório da Factory informa que a entrega completa não foi comprovada. Não trate essa etapa como produto terminado.";
 }else if(input.releaseStatus==="released"||hasHumanMerge){
  headline="Integração registrada; produto não certificado";
  explanation="A integração/merge foi registrada, mas faltam evidências atuais que comprovem os requisitos, a experiência funcional e a entrega completa.";
 }else if(input.releaseStatus==="blocked"){
  headline="Publicação bloqueada ou não concluída";
  explanation="Existe um relatório de liberação bloqueado. Um Preview ou testes anteriores não autorizam interpretar o produto como publicado.";
 }else if(preview){
  headline="Prévia registrada, entrega não comprovada";
  explanation="Existe registro de Preview, mas isso não prova funcionamento da aplicação, publicação ou conclusão do produto.";
 }else{
  headline="Sem entrega comprovada no Control Plane";
  explanation="Não há relatório suficiente de entrega funcional deste projeto. Isso não significa que nenhum trabalho tenha sido realizado.";
 }
 return {
  releaseStatus:input.releaseStatus||null,productComplete:complete,productReady:independentlyReady,
  hasHumanMerge,hasPreviewRecord:preview,hasProductionDeployment:production,
  certificationSha:input.certificationSha||null,releaseCandidateSha:input.releaseCandidateSha||null,
  headline,explanation,
 };
}
