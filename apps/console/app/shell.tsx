"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import type {ReactNode} from "react";
import {signOutAction} from "./auth-actions";
import {ConsoleNav} from "./nav";

export function ConsoleShell({children}:{children:ReactNode}){
 const pathname=usePathname();
 const authOnly=pathname==="/login"||pathname==="/unauthorized";
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
   <ConsoleNav/>
   <div className="sidebarFooter">
    <div className="sidebarHealth"><span>AI Product Factory</span></div>
    <div className="sidebarFooterRow"><span className="envBadge">produção</span><form action={signOutAction}><button type="submit" className="signOut">Sair</button></form></div>
   </div>
  </aside>
  <div className="workspace">
   <header className="topbar">
    <div className="topbarTrail"><span>Control Plane</span><b>/</b><strong>Sessão ativa</strong></div>
    <div className="topbarMeta"><span>Console</span><span className="topbarDivider"/><span>Produção</span><Link href="/projects/new" className="topbarWork">+ Novo trabalho</Link></div>
   </header>
   <main className="main">{children}</main>
  </div>
 </div>;
}
