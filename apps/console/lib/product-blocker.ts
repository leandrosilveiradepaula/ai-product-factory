/* Safe operator-facing descriptions of task failures. No raw provider errors
 * are copied into the portfolio. This is not a recovery command. */
export type ProductBlocker={
 code:"source_context"|"database_migration"|"provider_budget"|"execution";
 title:string;why:string;resolution:string;
};
export function explainRunBlocker(status:string,error:unknown):ProductBlocker|null{
 if(!["failed","blocked","failed_gate","repair_pending","dead_letter"].includes(status))return null;
 const message=typeof error==="string"?error.slice(0,4000):"";
 if(/AGENTS\.md/i.test(message)&&/(not present|missing|unavailable|not supplied|absent|could not)/i.test(message))
  return {
   code:"source_context",
   title:"Instruções do repositório não verificadas",
   why:"O executor parou porque não recebeu ou não conseguiu verificar AGENTS.md no contexto do commit usado na alteração.",
   resolution:"A Factory precisa conferir as instruções reais na revisão e no repositório de origem, corrigir o contexto da tarefa e revalidar o mesmo escopo antes de retomar. Não é uma aprovação de produção.",
  };
 if(/(migration|schema|postgres|rls)/i.test(message))
  return {
   code:"database_migration",
   title:"Alteração de banco não validada",
   why:"A tentativa foi bloqueada durante uma etapa relacionada ao schema ou à migração. Não há prova de aplicação no banco de destino.",
   resolution:"Conferir ambiente, versão do SQL, permissões, backup e resultado de teste independente antes de solicitar qualquer migration que exija aprovação.",
  };
 if(/(quota|billing|credit|budget|insufficient)/i.test(message))
  return {
   code:"provider_budget",
   title:"Limite ou disponibilidade do provedor",
   why:"A execução reportou um problema de custo, saldo ou quota. Isso não comprova o saldo atual.",
   resolution:"Verificar o ledger e a situação do provedor antes de reexecutar. Nunca adicionar créditos ou repetir uma chamada paga sem aprovação.",
  };
 return {
  code:"execution",
  title:"Trabalho técnico interrompido",
  why:"A tarefa terminou com falha ou bloqueio e não existe conclusão confirmada dessa tentativa.",
  resolution:"A Factory deve investigar o log e corrigir a causa antes de repetir o trabalho. A publicação não está autorizada por este erro.",
 };
}
