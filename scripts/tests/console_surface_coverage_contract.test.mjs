import test from "node:test";
import assert from "node:assert/strict";
import {CONSOLE_ROUTES,verifyConsoleSurfaceCoverage} from "../console_surface_coverage_contract.mjs";

function fixture() {
  const captured=CONSOLE_ROUTES.map(route=>({
    ...route,status:200,documentSize:{width:route.width,height:900}
  }));
  const accessibilityRoutes=CONSOLE_ROUTES.map(route=>({
    route:route.name,checked:true,unnamedCount:0,
    duplicateIds:0,missingImageAlt:0,positiveTabOrder:0,
  }));
  const mobile=CONSOLE_ROUTES.map(route=>({
    name:route.name+"-mobile",path:route.path,status:200,
    layout:{innerWidth:390,scrollWidth:390},
    readability:{mainLandmark:true,keyboardSkipPresent:true},
    expandedLayout:{width:390,viewport:390},
    quickNavHrefs:["/","/projects","/gates"],
  }));
  mobile.push({name:"project-detail-mobile",verifiedWithoutMutation:true});
  return {captured,accessibilityRoutes,mobile,keyboardSkip:{
    reachedWithTab:true,visibleOnFocus:true,landedOnMain:true,
  }};
}

test("full 14-route desktop + phone + keyboard inventory stays bounded",()=>{
  const receipt=verifyConsoleSurfaceCoverage(fixture());
  assert.equal(receipt.desktopRoutes,14);
  assert.equal(receipt.mobileRoutes,14);
  assert.equal(receipt.accessibleRoutes,14);
  assert.equal(receipt.productExperienceCertified,false);
  assert.equal(receipt.fullErrorLoadingEmptyStateMatrixVerified,false);
  assert.equal(receipt.writes,0);
});

test("missing or duplicated routes cannot pass",()=>{
  const f=fixture();f.mobile.pop();
  assert.throws(()=>verifyConsoleSurfaceCoverage(f),/mobile_detail_missing/);
  const f2=fixture();f2.captured[1]={...f2.captured[0]};
  assert.throws(()=>verifyConsoleSurfaceCoverage(f2),/desktop_identity_mismatch/);
  const f3=fixture();f3.accessibilityRoutes.pop();
  assert.throws(()=>verifyConsoleSurfaceCoverage(f3),/accessibility_inventory_incomplete/);
});

test("mobile overflow and missing access names fail closed",()=>{
  const f=fixture();f.mobile[5].layout.scrollWidth=560;
  assert.throws(()=>verifyConsoleSurfaceCoverage(f),/mobile_unverified/);
  const f2=fixture();f2.accessibilityRoutes[3].unnamedCount=1;
  assert.throws(()=>verifyConsoleSurfaceCoverage(f2),/accessibility_unverified/);
});

test("wrong browser route, keyboard shortcut and failed HTTP fail closed",()=>{
  const f=fixture();f.captured[3].path="/attacker";
  assert.throws(()=>verifyConsoleSurfaceCoverage(f),/desktop_unverified/);
  const f2=fixture();f2.keyboardSkip.landedOnMain=false;
  assert.throws(()=>verifyConsoleSurfaceCoverage(f2),/keyboard_skip_invalid/);
  const f3=fixture();f3.mobile[2].status=403;
  assert.throws(()=>verifyConsoleSurfaceCoverage(f3),/mobile_unverified/);
});

test("receipts never include authentication/session/browser source values",()=>{
  const receipt=verifyConsoleSurfaceCoverage(fixture());
  const raw=JSON.stringify(receipt);
  for(const secret of ["password","access_token","email","cookie","session","screenshot"]) {
    assert.ok(!raw.includes(secret),secret);
  }
});
