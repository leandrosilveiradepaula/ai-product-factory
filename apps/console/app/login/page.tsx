import {signInAction} from "../auth-actions";
import {Button,PageHeader} from "../ui";

// Browser tabs and screen readers need an exact, task-specific title. The
// site identity remains visible in the suffix on the only unauthenticated route.
export const metadata={title:"Entrar na Factory — AI Product Factory"};

function safeNext(value:string|undefined){
 if(!value||!value.startsWith("/")||value.startsWith("//")||value.includes("\\"))return "/";
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
