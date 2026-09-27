import {IntakeForm} from "./intake-form";
import {PageHeader} from "../../ui";

export default function NewProject(){return <>
 <PageHeader eyebrow="New Work" title="Iniciar ou importar projeto" subtitle="Comece uma ideia nova ou traga um projeto em andamento. A Factory inicia Discovery ou reconcilia o estado real antes de continuar."/>
 <IntakeForm/>
</>;}