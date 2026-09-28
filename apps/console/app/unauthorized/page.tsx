import {signOutAction} from "../auth-actions";
import {Button,PageHeader} from "../ui";

export default function Unauthorized(){
 return <>
  <PageHeader eyebrow="Acesso negado" title="Usuário sem permissão" subtitle="Sua sessão é válida, mas este usuário não está cadastrado como operador da Factory."/>
  <form action={signOutAction}><Button type="submit">Sair</Button></form>
 </>;
}