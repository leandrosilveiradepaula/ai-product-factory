import {signInAction} from "../auth-actions";
import {Button,PageHeader} from "../ui";

function safeNext(value:string|undefined){
 if(!value||!value.startsWith("/")||value.startsWith("//"))return "/";
 return value;
}

export default async function Login({searchParams}:{searchParams:Promise<{error?:string;next?:string}>}){
 const p=await searchParams;const next=safeNext(p.next);
 return <>
  <PageHeader eyebrow="Acesso seguro" title="Entrar na Factory" subtitle="Apenas operadores autorizados no Painel de Controle podem acessar o Console."/>
  <form className="form card authForm" action={signInAction}>
   <input type="hidden" name="next" value={next}/>
   <label>E-mail<input name="email" type="email" autoComplete="email" required/></label>
   <label>Senha<input name="password" type="password" autoComplete="current-password" required/></label>
   {p.error?<small>{p.error==="missing"?"Preencha e-mail e senha.":"Credenciais inválidas."}</small>:null}
   <Button variant="primary" type="submit">Entrar</Button>
  </form>
 </>;
}
