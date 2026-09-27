import Link from "next/link";
import {redirect} from "next/navigation";
import type {ProjectIntake} from "../../../../lib/intake";
import {createProjectIntake,enqueueProjectBootstrap} from "../../../../lib/control-plane";

function decode(raw:string|undefined):ProjectIntake|null{if(!raw)return null;try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8"))}catch{return null}}
async function start(formData:FormData){"use server";const intake=decode(String(formData.get("intake")||""));if(!intake)throw new Error("Intake inválido");const result=await createProjectIntake(intake);await enqueueProjectBootstrap(result.projectKey);redirect(`/projects/${result.projectKey}`)}

export default async function Review({searchParams}:{searchParams:Promise<{intake?:string}>}){
 const p=await searchParams;const intake=decode(p.intake);
 if(!intake)return <><div className="pageHeader"><div><div className="eyebrow">New Work</div><h1 className="title">Invalid intake</h1></div></div><Link className="secondary linkButton" href="/projects/new">Back</Link></>;
 return <>
  <div className="pageHeader"><div><div className="eyebrow">Review Intake</div><h1 className="title">{intake.name}</h1><p className="subtitle">Ao iniciar, a Factory persiste o produto, cria o bootstrap e abre o estágio de discovery no Control Plane.</p></div></div>
  <div className="card" style={{maxWidth:860}}>
   <div className="detailGrid">
    <div className="detailItem"><span className="detailLabel">Mode</span><strong>{intake.mode==="greenfield"?"New product":"Import repository"}</strong></div>
    <div className="detailItem"><span className="detailLabel">Repository</span><strong>{intake.repository||"Will be created later"}</strong></div>
   </div>
   <div className="section"><span className="detailLabel">Objective</span><p>{intake.summary}</p></div>
   <div className="twoCol">
    <div><span className="detailLabel">Users</span><p className="muted">{intake.users||"Not informed"}</p></div>
    <div><span className="detailLabel">Must have</span><p className="muted">{intake.mustHave||"Not informed"}</p></div>
   </div>
   <div><span className="detailLabel">Known integrations</span><p className="muted">{intake.integrations||"Not informed"}</p></div>
  </div>
  <div className="actions"><Link className="secondary" href="/projects/new">Edit</Link><form action={start}><input type="hidden" name="intake" value={p.intake}/><button className="primary">Start Factory</button></form></div>
 </>;
}