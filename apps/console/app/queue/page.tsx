import Link from "next/link";
import {getWorkQueue} from "../../lib/control-plane";
import {ActionLink,EmptyState,PageHeader,StatusPill} from "../ui";

export default async function Queue(){
 const items=await getWorkQueue();
 return <>
  <PageHeader eyebrow="Execução" title="Fila de trabalho" subtitle="Trabalho executável atualmente aguardando distribuição, execução ou autoridade humana." actions={<ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink>}/>
  <div className="table"><div className="tableRow tableHeader"><span>Tarefa / Projeto</span><span>Complexidade</span><span>Estado</span><span>Atualizada em</span></div>{items.length===0?<EmptyState>Fila vazia. Nenhum trabalho pendente.</EmptyState>:items.map(x=><div className="tableRow" key={x.id}><div><strong>{x.title}</strong><div><Link className="muted" href={"/projects/"+x.projectKey}>{x.projectName}</Link></div></div><StatusPill status={x.complexity}/><StatusPill status={x.status}/><span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span></div>)}</div>
 </>;
}