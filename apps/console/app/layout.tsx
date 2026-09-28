import "./theme.css";
import "./globals.css";
import Link from "next/link";
import {Inter} from "next/font/google";
import {signOutAction} from "./auth-actions";
import {ConsoleNav} from "./nav";

const inter=Inter({subsets:["latin"],variable:"--font-inter"});
export const metadata={title:"AI Product Factory",description:"Painel de controle da fábrica autônoma de desenvolvimento de produtos"};

export default function RootLayout({children}:{children:React.ReactNode}){
 return <html lang="pt-BR">
  <body className={inter.variable}>
   <div className="consoleShell">
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
      <div className="sidebarHealth"><span className="healthDot"/><span>Factory saudável</span></div>
      <div className="sidebarFooterRow"><span className="envBadge">produção</span><form action={signOutAction}><button type="submit" className="signOut">Sair</button></form></div>
     </div>
    </aside>
    <div className="workspace">
     <header className="topbar">
      <div className="topbarTrail"><span>Control Plane</span><b>/</b><strong>Sessão ativa</strong></div>
      <div className="topbarMeta"><span className="healthDot"/><span>Online</span><span className="topbarDivider"/><span>Produção</span><Link href="/projects/new" className="topbarWork">+ Novo trabalho</Link></div>
     </header>
     <main className="main">{children}</main>
    </div>
   </div>
  </body>
 </html>;
}
