import "./globals.css";
import Link from "next/link";
import {signOutAction} from "./auth-actions";
import {ConsoleNav} from "./nav";

export const metadata={title:"AI Product Factory",description:"Autonomous product development control plane"};

export default function RootLayout({children}:{children:React.ReactNode}){
 return <html lang="pt-BR">
  <body>
   <div className="consoleShell">
    <aside className="sidebar">
     <Link href="/" className="brandBlock">
      <div className="brandMark">AI</div>
      <div><strong>Product Factory</strong><span>CONTROL PLANE</span></div>
     </Link>
     <ConsoleNav/>
     <div className="sidebarFooter">
      <div className="envBadge"><i/>Production</div>
      <form action={signOutAction}><button type="submit" className="signOut">Sair</button></form>
     </div>
    </aside>
    <div className="workspace">
     <header className="topbar">
      <div><span className="topbarKicker">AI PRODUCT FACTORY</span><strong>Operational Console</strong></div>
      <div className="topbarMeta"><span className="healthDot"/>Control Plane online</div>
     </header>
     <main className="main">{children}</main>
    </div>
   </div>
  </body>
 </html>;
}
