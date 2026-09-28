import {revalidatePath} from "next/cache";
import {getOperatorAdminRows,upsertConsoleOperator} from "../../../lib/control-plane";
import {Button,EmptyState,PageHeader,StatusPill} from "../../ui";

async function updateOperator(formData:FormData){"use server";const userId=String(formData.get("user_id")||"");const role=String(formData.get("role")||"");const active=String(formData.get("active")||"")==="true";if(!userId||!["operator","admin"].includes(role))throw new Error("Atualização de operador inválida");await upsertConsoleOperator(userId,role as "operator"|"admin",active);revalidatePath("/admin/operators");}

export default async function Operators(){
 const rows=await getOperatorAdminRows();
 return <>
  <PageHeader eyebrow="Segurança" title="Operadores" subtitle="Gerencie apenas usuários que já existem no Supabase Auth. Não há criação pública de contas."/>
  <section className="section">{rows.length===0?<EmptyState>Nenhum usuário existe no Supabase Auth.</EmptyState>:<div className="stack">{rows.map(row=><article className="card" key={row.userId}><div className="heading"><div><strong>{row.email||"Sem e-mail"}</strong><div className="muted">{row.userId}</div></div><StatusPill status={row.active?"active":"inactive"} label={row.role||"sem acesso"}/></div><form action={updateOperator} className="gateForm"><input type="hidden" name="user_id" value={row.userId}/><label>Perfil <select name="role" defaultValue={row.role||"operator"}><option value="operator">Operador</option><option value="admin">Admin</option></select></label><div className="actions"><Button variant="primary" name="active" value="true">Salvar e ativar</Button>{row.active?<Button variant="danger" name="active" value="false">Desativar</Button>:null}</div></form></article>)}</div>}</section>
 </>;
}