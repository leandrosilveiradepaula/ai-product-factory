import {signInAction} from "../auth-actions";
import {Button,PageHeader} from "../ui";

export default async function Login({searchParams}:{searchParams:Promise<{error?:string}>}){
 const p=await searchParams;
 return <>
  <PageHeader eyebrow="Acesso seguro" title="Entrar na Factory" subtitle="Apenas operadores autorizados no Control Plane podem acessar o Console."/>
  <form className="form card authForm" action={signInAction}><label>E-mail<input name="email" type="email" autoComplete="email" required/></label><label>Senha<input name="password" type="password" autoComplete="current-password" required/></label>{p.error?<small>{p.error==="missing"?"Preencha e-mail e senha.":"Credenciais inválidas."}</small>:null}<Button variant="primary" type="submit">Entrar</Button></form>
 </>;
}