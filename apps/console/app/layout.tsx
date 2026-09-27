import "./globals.css";
import Link from "next/link";
import {signOutAction} from "./auth-actions";

export const metadata={title:"AI Product Factory",description:"Autonomous product development control plane"};

const nav=[
 {group:"OPERATIONS",items:[["Overview","/"],["Projects","/projects"],["Runs","/runs"],["Work Queue","/work-queue"],["Human Gates","/decisions"]]},
 {group:"QUALITY & RELEASE",items:[["Evals & Tests","/evals"],["Deployments","/deployments"]]},
 {group:"GOVERNANCE & OBSERVE",items:[["Models & Usage","/models"],["Audit Log","/audit"],["Configuration","/configuration"],["Operators","/admin/operators"]]}
] as const;

export default function RootLayout({children}:{children:React.ReactNode}){
 return <html lang="pt-BR"><body>
  <div className="factory-shell">
   <aside className="factory-sidebar">
    <Link href="/" className="factory-brand">
     <span className="brand-mark"><span/><span/><span/><span/><i/></span>
     <span><b>AI Product Factory</b><small>CONTROL PLANE</small></span>
    </Link>
    <div className="environment-chip"><i/> Production control plane</div>
    <nav className="factory-nav">
     {nav.map(section=><div className="nav-section" key={section.group}>
      <div className="nav-label">{section.group}</div>
      {section.items.map(([label,href])=><Link href={href} key={href}>{label}</Link>)}
     </div>)}
    </nav>
    <div className="sidebar-footer">
     <div className="factory-health"><span><i/> Factory online</span><b>Human-gated prod</b></div>
     <form action={signOutAction}><button type="submit" className="nav-signout">Sair</button></form>
    </div>
   </aside>
   <div className="factory-workspace">
    <header className="factory-topbar">
     <div><span className="topbar-kicker">Infodive</span><strong>Development Control Plane</strong></div>
     <div className="topbar-status"><span><i/> Live</span><span>Production merge: human only</span></div>
    </header>
    <main className="factory-main">{children}</main>
   </div>
  </div>
 </body></html>
}