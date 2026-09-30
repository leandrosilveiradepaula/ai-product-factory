import "./theme.css";
import "./globals.css";
import {Inter} from "next/font/google";
import {ConsoleShell} from "./shell";

const inter=Inter({subsets:["latin"],variable:"--font-inter"});
export const metadata={title:"AI Product Factory",description:"Painel de controle da fábrica autônoma de desenvolvimento de produtos"};

export default function RootLayout({children}:{children:React.ReactNode}){
 const environmentLabel=process.env.VERCEL_ENV==="production"?"Produção":process.env.VERCEL_ENV==="preview"?"Preview":"Desenvolvimento";
 return <html lang="pt-BR">
  <body className={inter.variable}><ConsoleShell environmentLabel={environmentLabel}>{children}</ConsoleShell></body>
 </html>;
}
