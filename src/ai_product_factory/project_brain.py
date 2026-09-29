from __future__ import annotations

import re
from dataclasses import dataclass


def _slug(value:str)->str:
    return re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")


def _list(value:object)->tuple[str,...]:
    if not isinstance(value,list):return ()
    return tuple(dict.fromkeys(str(x).strip() for x in value if str(x).strip()))


@dataclass(frozen=True)
class ProjectBrainGraph:
    summary:str
    nodes:tuple[dict,...]
    edges:tuple[dict,...]


def build_project_brain_graph(*,project_key:str,engineering_plan:dict,context:dict|None=None)->ProjectBrainGraph:
    context=context or {}
    nodes:dict[str,dict]={}
    edges:dict[str,dict]={}

    def add_node(key:str,node_type:str,name:str,attributes:dict|None=None,source_refs:tuple[str,...]=())->None:
        if key in nodes:return
        nodes[key]={
            "key":key,"type":node_type,"name":name,
            "attributes":attributes or {},"source_refs":list(source_refs),
        }

    def add_edge(key:str,source:str,target:str,relation:str,attributes:dict|None=None,source_refs:tuple[str,...]=())->None:
        if source not in nodes or target not in nodes:
            return
        edges[key]={
            "key":key,"from":source,"to":target,"relation":relation,
            "attributes":attributes or {},"source_refs":list(source_refs),
        }

    project_node=f"project:{project_key}"
    add_node(project_node,"project",project_key,{"project_key":project_key},("planning",))

    tasks=[x for x in engineering_plan.get("tasks",[]) if isinstance(x,dict)] if isinstance(engineering_plan.get("tasks"),list) else []
    aliases={}
    for index,task in enumerate(tasks):
        task_key=str(task.get("task_key") or task.get("key") or f"task-{index+1}").strip()
        title=str(task.get("title") or task_key).strip()
        node_key=f"task:{task_key}"
        aliases[task_key]=node_key;aliases[title]=node_key;aliases[_slug(title)]=node_key
        add_node(node_key,"task",title,{
            "task_key":task_key,
            "preferred_agent_role":task.get("preferred_agent_role"),
            "risk":task.get("risk") if isinstance(task.get("risk"),dict) else {},
        },("planning",))
        add_edge(f"project-contains-{task_key}",project_node,node_key,"contains",source_refs=("planning",))

        for scope in _list(task.get("scope_keys")):
            scope_key=f"scope:{scope}"
            add_node(scope_key,"scope",scope,{"path":scope},("planning",))
            add_edge(f"{task_key}-modifies-{_slug(scope)}",node_key,scope_key,"may_modify",source_refs=("planning",))
        for capability in _list(task.get("required_capabilities")):
            cap_key=f"capability:{capability}"
            add_node(cap_key,"capability",capability,{},("planning",))
            add_edge(f"{task_key}-requires-{_slug(capability)}",node_key,cap_key,"requires",source_refs=("planning",))

    for index,task in enumerate(tasks):
        task_key=str(task.get("task_key") or task.get("key") or f"task-{index+1}").strip()
        source=aliases.get(task_key)
        if not source:continue
        for dep in _list(task.get("depends_on")):
            target=aliases.get(dep) or aliases.get(_slug(dep))
            if target:
                add_edge(f"{task_key}-depends-{_slug(dep)}",source,target,"depends_on",source_refs=("planning",))

    state=context.get("state_snapshot") if isinstance(context.get("state_snapshot"),dict) else {}
    source_status=state.get("source_status") if isinstance(state.get("source_status"),dict) else {}
    for source_name,value in sorted(source_status.items()):
        key=f"source:{_slug(str(source_name))}"
        add_node(key,"source",str(source_name),{"status":value},("state_snapshot",))
        add_edge(f"project-source-{_slug(str(source_name))}",project_node,key,"observed_from",source_refs=("state_snapshot",))

    evidence=state.get("evidence") if isinstance(state.get("evidence"),list) else []
    allowed_evidence_keys=("source","head_sha","commit","ref","kind","status")
    for index,row in enumerate(evidence):
        key=f"evidence:{index+1}"
        safe={}
        if isinstance(row,dict):
            for field in allowed_evidence_keys:
                value=row.get(field)
                if isinstance(value,(str,int,float,bool)) and str(value).strip():
                    safe[field]=value
        source=str(safe.get("source") or safe.get("kind") or "evidence")
        add_node(key,"evidence",f"{source} evidence {index+1}",safe,("state_snapshot",))
        add_edge(f"project-evidence-{index+1}",project_node,key,"evidenced_by",source_refs=("state_snapshot",))

    architecture=engineering_plan.get("architecture")
    if isinstance(architecture,dict):
        for name,value in architecture.items():
            key=f"component:{_slug(str(name))}"
            add_node(key,"component",str(name),{"description":value},("planning",))
            add_edge(f"project-component-{_slug(str(name))}",project_node,key,"contains",source_refs=("planning",))
    elif isinstance(architecture,list):
        for value in architecture:
            name=str(value)
            key=f"component:{_slug(name)}"
            add_node(key,"component",name,{},("planning",))
            add_edge(f"project-component-{_slug(name)}",project_node,key,"contains",source_refs=("planning",))

    summary=f"{project_key}: {len(tasks)} planned task(s), {sum(1 for n in nodes.values() if n['type']=='scope')} scope(s), {sum(1 for n in nodes.values() if n['type']=='capability')} capability node(s)"
    return ProjectBrainGraph(summary,tuple(nodes.values()),tuple(edges.values()))
