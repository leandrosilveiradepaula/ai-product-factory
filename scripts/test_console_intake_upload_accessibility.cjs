/* Real TSX intake semantics with React hooks stubbed, no browser credentials,
 * uploads, network, project creation, paid model or Supabase operations. */
"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const jsx=(type,props,key)=>({type,props:props||{},key});
const inputFile="apps/console/app/projects/new/intake-form.tsx";
const source=fs.readFileSync(path.join(root,inputFile),"utf8");
const output=ts.transpileModule(source,{fileName:inputFile,reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
    jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}});
assert.equal((output.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const mod={};
vm.runInNewContext(output.outputText,{exports:mod,require(name){
  if(name==="react/jsx-runtime")return{jsx,jsxs:jsx,Fragment:"fragment"};
  if(name==="react")return{
    useState:initial=>[initial,()=>{}],
    useActionState:(_fn,initial)=>[initial,()=>{},false],
  };
  if(name==="../../ui")return{Button:()=>null};
  if(name==="./actions")return{submitIntake:()=>{throw Error("must never submit")}};
  throw Error("unexpected import "+name);
}},{filename:inputFile,timeout:10000});
assert.equal(typeof mod.IntakeForm,"function");

function traverse(value,cb,ancestors=[]){
  if(Array.isArray(value)){for(const item of value)traverse(item,cb,ancestors);return;}
  if(!value||typeof value!=="object"||!("type" in value))return;
  cb(value,ancestors);
  traverse(value.props?.children,cb,[...ancestors,value]);
}
function findAll(tree,pred){
  const result=[];
  traverse(tree,(n,ancestors)=>{if(pred(n))result.push({node:n,ancestors});});
  return result;
}
function textOf(value){
  if(Array.isArray(value))return value.map(textOf).join(" ");
  if(typeof value==="string"||typeof value==="number")return String(value);
  if(!value||typeof value!=="object")return "";
  return textOf(value.props?.children);
}
const modes=["greenfield","existing"];

test("actual TSX associates upload control with a visible accessible label in both modes",()=>{
  for(const mode of modes){
    const tree=mod.IntakeForm({initial:{mode}});
    assert.equal(tree.type,"form");
    assert.equal(tree.props.encType,"multipart/form-data");
    const upload=findAll(tree,n=>n.type==="input"&&n.props.name==="attachments");
    assert.equal(upload.length,1,mode);
    const {node:input}=upload[0];
    assert.equal(input.props.id,"intake-attachments",mode);
    assert.equal(input.props.type,"file",mode);
    assert.equal(input.props.multiple,true,mode);
    assert.equal(input.props.accept,".pdf,.txt,.md,.csv,.json,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp",mode);
    const labels=findAll(tree,n=>n.type==="label"&&n.props.htmlFor===input.props.id);
    assert.equal(labels.length,1,"no matching label for "+mode);
    assert.equal(textOf(labels[0].node).trim(),"Selecionar arquivos para anexar",mode);
    const details=findAll(tree,n=>n.type==="details"&&n.props.className==="intakeOptional");
    assert.equal(details.length,1);
    assert.equal(Boolean(details[0].node.props.open),false);
    const hiddenInputs=findAll(tree,n=>n.type==="input"&&n.props.type==="hidden");
    assert.ok(hiddenInputs.some(x=>x.node.props.name==="mode"));
  }
});

test("draft attachments expand disclosure without losing the file label",()=>{
  const tree=mod.IntakeForm({initial:{mode:"greenfield",attachmentCount:2}});
  const details=findAll(tree,n=>n.type==="details"&&n.props.className==="intakeOptional");
  assert.equal(details.length,1);
  assert.equal(details[0].node.props.open,true);
  assert.equal(findAll(tree,n=>n.type==="input"&&n.props.name==="attachments").length,1);
  assert.equal(findAll(tree,n=>n.type==="label"&&n.props.htmlFor==="intake-attachments").length,1);
});

test("closed disclosure hides optional controls without hiding the summary or main form",()=>{
  const css=fs.readFileSync(path.join(root,"apps/console/app/globals.css"),"utf8");
  assert.ok(css.includes(".intakeOptionalBody{display:grid;gap:16px;padding:18px}"));
  assert.ok(css.includes(".intakeOptional:not([open])>.intakeOptionalBody{display:none}"));
  assert.ok(!css.includes(".intakeOptional:not([open])>summary{display:none}"));
});
