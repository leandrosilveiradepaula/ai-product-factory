import Link from "next/link";
import {getDashboard} from "../../lib/control-plane";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?8:Math.round(((i+1)/stages.length)*100)}

export default async function Projects(){
 const d=await getDashboard();
 return <>
  <div className="pageHeader"><div><div className="eyebrow">Projects</div><h1 className="title">Product portfolio</h1><p className="subtitle">Produtos greenfield e repositórios existentes conduzidos pela Factory.</p></div><Link className="primary linkButton" href="/projects/new">+ New Work</Link></div>
  <div className="projectCards">
   {d.projects.length===0?<div className="emptyState">Nenhum projeto registrado.</div>:d.projects.map(p=><Link className="card projectCard" href={`/projects/${p.key}`} key={p.key}>
    <div className="cardTop"><div><h2 className="cardTitle">{p.name}</h2><p className="cardMeta mono">{p.key}</p></div><span className="pill accent">{p.stage}</span></div>
    <div className="progressTrack"><div className="progressFill" style={{width:`${progress(p.stage)}%`}}/></div>
    <div className="valueRow"><span className="muted">Lifecycle progress</span><strong>{progress(p.stage)}%</strong></div>
    <div className="badgeLine"><span className="status"><i className="statusDot"/>{p.status}</span><span className="muted">updated {new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div>
   </Link>)}
  </div>
 </>;
}