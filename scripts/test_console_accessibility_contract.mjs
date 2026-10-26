import test from "node:test";
import assert from "node:assert/strict";
import {verifyAccessibilitySnapshot} from "./console_accessibility_contract.mjs";

const good = Object.freeze({
  language:"pt-BR",hasTitle:true,mainCount:1,mainTarget:true,
  skipCount:1,skipHasName:true,h1Count:1,interactiveCount:7,
  unnamedCount:0,missingImageAlt:0,duplicateIds:0,positiveTabOrder:0,
});
test("a complete accessibility snapshot emits only safe counts",()=>{
  const result=verifyAccessibilitySnapshot({...good,secret:"do-not-record"},"overview");
  assert.deepEqual(result,{
    checked:true,landmarkCount:1,headingCount:1,interactiveCount:7,
    unnamedCount:0,missingImageAlt:0,duplicateIds:0,positiveTabOrder:0,
  });
  assert.equal(JSON.stringify(result).includes("do-not-record"),false);
});
test("fail closed on missing structure, unnamed controls and invalid keyboard order",()=>{
  const invalid={
    language:["en","document_language"],
    hasTitle:[false,"document_title"],
    mainCount:[0,"main_landmark"],
    mainTarget:[false,"main_landmark"],
    skipCount:[0,"skip_link"],
    skipHasName:[false,"skip_link"],
    h1Count:[0,"page_heading"],
    interactiveCount:[0,"interactive_inventory"],
    unnamedCount:[2,"interactive_names"],
    missingImageAlt:[1,"image_alternatives"],
    duplicateIds:[2,"unique_ids"],
    positiveTabOrder:[1,"tab_order"],
  };
  for(const [field,[value,code]] of Object.entries(invalid)){
    assert.throws(()=>verifyAccessibilitySnapshot({...good,[field]:value},"projects"),
      error => error.message.includes("accessibility:projects:") && error.message.includes(code),field);
  }
});
test("reject malformed or ambiguous browser data",()=>{
  for(const snapshot of [null,[],{}, {...good,interactiveCount:NaN},
    {...good,unnamedCount:-1},{...good,skipCount:"1"},{...good,mainTarget:"true"}]){
    assert.throws(()=>verifyAccessibilitySnapshot(snapshot,"overview"),/accessibility:/);
  }
  assert.throws(()=>verifyAccessibilitySnapshot(good,"../../secret"),/invalid_route/);
});
