import {ActionLink,PageHeader} from "./ui";

export default function NotFound(){
 return <>
  <PageHeader eyebrow="Página não encontrada" title="Não encontramos esta página" subtitle="Verifique o endereço ou volte para a visão geral da Factory."/>
  <ActionLink href="/">Voltar para a visão geral</ActionLink>
 </>;
}
