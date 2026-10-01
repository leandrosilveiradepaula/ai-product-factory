"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import type {ReactNode} from "react";
import {signOutAction} from "./auth-actions";
import {ConsoleNav} from "./nav";

type RouteContext={area:string;screen:string;purpose:string;advanced?:boolean};
function routeContext(pathname:string):RouteContext{
 if(pathname==="/")return{area:"Operação",screen:"Visão geral",purpose:"Comece aqui. Veja se existe alguma ação sua e acompanhe o estado geral da Factory."};
 if(pathname.startsWith("/projects/new"))return{area:"Projetos",screen:"Novo projeto",purpose:"Use para criar um produto novo ou importar um projeto que já está em andamento."};
 if(/^\/projects\/[^/]+/.test(pathname))return{area:"Projetos",screen:"Detalhes do projeto",purpose:"Esta é a tela principal de acompanhamento de um projeto. Veja a etapa atual e a próxima ação."};
 if(pathname==="/projects")return{area:"Projetos",screen:"Portfólio",purpose:"Use para escolher qual projeto acompanhar ou para iniciar um novo projeto."};
 if(pathname.startsWith("/gates"))return{area:"Operação",screen:"Aprovações humanas",purpose:"Caixa de entrada das decisões que realmente precisam de você. Se estiver vazia, não há ação humana pendente."};
 if(pathname.startsWith("/runs"))return{area:"Diagnóstico",screen:"Execuções",purpose:"Tela avançada para inspecionar como uma tarefa foi executada. Não é uma etapa obrigatória do fluxo.",advanced:true};
 if(pathname.startsWith("/queue"))return{area:"Diagnóstico",screen:"Fila de trabalho",purpose:"Tela avançada para observar backlog, despacho e trabalhos em execução. A Factory gerencia esta fila automaticamente.",advanced:true};
 if(pathname.startsWith("/agents"))return{area:"Diagnóstico",screen:"Agentes da Factory",purpose:"Tela avançada para entender quais especialistas existem, sua capacidade e quais trabalhos estão executando.",advanced:true};
 if(pathname.startsWith("/orchestration"))return{area:"Diagnóstico",screen:"Orquestração",purpose:"Tela avançada do motor da Factory: prioridades, incidentes, reparos e prontidão de liberação.",advanced:true};
 if(pathname.startsWith("/evals"))return{area:"Qualidade",screen:"Avaliações e testes",purpose:"Evidências automáticas de qualidade. Normalmente você consulta esta tela para diagnóstico ou validação de um candidato.",advanced:true};
 if(pathname.startsWith("/deployments"))return{area:"Qualidade",screen:"Implantações",purpose:"Histórico de Preview e produção. Use para confirmar o que foi implantado e seu estado.",advanced:true};
 if(pathname.startsWith("/usage"))return{area:"Governança",screen:"Modelos e uso",purpose:"Observabilidade de custos, limites e uso de modelos. Não faz parte do fluxo diário normal.",advanced:true};
 if(pathname.startsWith("/audit"))return{area:"Governança",screen:"Log de auditoria",purpose:"Trilha técnica durável para investigação e compliance. Não exige acompanhamento diário.",advanced:true};
 if(pathname.startsWith("/configuration"))return{area:"Governança",screen:"Configuração",purpose:"Mostra políticas e estado operacional. Use para administração e diagnóstico, não para conduzir um projeto.",advanced:true};
 if(pathname.startsWith("/admin/operators"))return{area:"Governança",screen:"Operadores",purpose:"Administração de quem pode acessar e operar a Factory.",advanced:true};
 return{area:"Console",screen:"Factory",purpose:"Acompanhe projetos e intervenha apenas quando a Factory solicitar uma decisão."};
}
export function ConsoleShell({children,environmentLabel}:{children:ReactNode;environmentLabel:string}){
 const pathname=usePathname();
 const authOnly=pathname==="/login"||pathname==="/unauthorized";
 const context=routeContext(pathname);
 if(authOnly){
  return <div className="authShell">
   <main className="authMain">{children}</main>
  </div>;
 }
 return <div className="consoleShell">
  <aside className="sidebar">
   <div className="brandRow">
    <Link href="/" className="brandBlock">
     <img className="brandMark" src="/ai-product-factory-logo.png" alt=""/>
     <div className="brandText"><strong>AI Product Factory</strong><span>PAINEL DE CONTROLE</span></div>
    </Link>
   </div>
   <div className="workspacePicker"><span className="workspaceGlyph">▦</span><span>Infodive / Autônomos</span></div>
   <div className="desktopSidebarContent">
    <ConsoleNav/>
    <div className="sidebarFooter">
     <div className="sidebarHealth"><span>AI Product Factory</span></div>
     <div className="sidebarFooterRow"><span className="envBadge">{environmentLabel}</span><form action={signOutAction}><button type="submit" className="signOut">Sair</button></form></div>
    </div>
   </div>
   <details className="mobileNav">
    <summary><span>Menu</span><span className="mobileNavHint">{context.area} / {context.screen}</span></summary>
    <div className="mobileNavBody">
     <Link href="/projects/new" className="mobileNewProject">+ Novo projeto</Link>
     <ConsoleNav/>
     <div className="mobileNavFooter"><span className="envBadge">{environmentLabel}</span><form action={signOutAction}><button type="submit" className="signOut">Sair</button></form></div>
    </div>
   </details>
  </aside>
  <div className="workspace">
   <header className="topbar">
    <div className="topbarTrail"><span>{context.area}</span><b>/</b><strong>{context.screen}</strong></div>
    <div className="topbarMeta"><span>Console</span><span className="topbarDivider"/><span>{environmentLabel}</span><Link href="/projects/new" className="topbarWork">+ Novo projeto</Link></div>
   </header>
   <main className="main">
    <div className={context.advanced?"screenGuide advanced":"screenGuide"}>
     <div><strong>{context.advanced?"Tela de inspeção":"Como usar esta tela"}</strong><span>{context.purpose}</span></div>
     {context.advanced?<Link href="/" className="screenGuideLink">Voltar à visão geral</Link>:null}
    </div>
    {children}
   </main>
  </div>
 </div>;
}
