import "./theme.css";
import "./globals.css";
import {Inter} from "next/font/google";
import {ConsoleShell} from "./shell";

const inter=Inter({subsets:["latin"],variable:"--font-inter"});
export const metadata={title:"AI Product Factory",description:"Painel de controle da fábrica autônoma de desenvolvimento de produtos"};
// Every application route is rendered against the authenticated Control Plane.
// Do not let Next attempt a build-time snapshot of a user-specific console.
export const dynamic="force-dynamic";

export default function RootLayout({children}:{children:React.ReactNode}){
 const environmentLabel=process.env.VERCEL_ENV==="production"?"Produção":process.env.VERCEL_ENV==="preview"?"Preview":"Desenvolvimento";
 return <html lang="pt-BR">
  <body className={inter.variable}><ConsoleShell environmentLabel={environmentLabel}>{children}</ConsoleShell></body>
 </html>;
}
