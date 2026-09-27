import {IntakeForm} from "./intake-form";
import {PageHeader} from "../../ui";

export default function NewProject(){return <>
 <PageHeader eyebrow="New Work" title="Start a product" subtitle="Descreva o problema e o contexto. A Factory transforma o intake em discovery, especificação e plano executável."/>
 <IntakeForm/>
</>;}