/** Exact, read-only Console surface coverage contract for future authenticated browser captures.
 * It checks evidence produced by running actual browser routes. It cannot turn
 * a captured screenshot into complete UX/Auth/E2E certification by itself.
 */
export const CONSOLE_ROUTES = Object.freeze([
  {name:"overview",path:"/",width:1296},
  {name:"projects",path:"/projects",width:1296},
  {name:"runs",path:"/runs",width:1296},
  {name:"new-project",path:"/projects/new",width:1296},
  {name:"human-gates",path:"/gates",width:1980},
  {name:"run-detail",path:"/runs/93fd8cdc-f000-4a01-978e-463798628e4e",width:1296},
  {name:"work-queue",path:"/queue",width:1296},
  {name:"agents",path:"/agents",width:1296},
  {name:"orchestration",path:"/orchestration",width:1296},
  {name:"evals",path:"/evals",width:1296},
  {name:"deployments",path:"/deployments",width:1296},
  {name:"models-usage",path:"/usage",width:1296},
  {name:"audit-log",path:"/audit",width:1308},
  {name:"configuration",path:"/configuration",width:1296},
]);

function exact(rows, names, kind) {
  if (!Array.isArray(rows) || rows.length !== names.length ||
      rows.some(row => !row || typeof row !== "object")) {
    throw new Error("console_surface_"+kind+"_inventory_incomplete");
  }
  const observed=rows.map(row=>row.name || row.route);
  if (new Set(observed).size!==names.length ||
      [...observed].sort().join("|")!==[...names].sort().join("|")) {
    throw new Error("console_surface_"+kind+"_identity_mismatch");
  }
}

export function verifyConsoleSurfaceCoverage({captured, accessibilityRoutes,
                                               mobile, keyboardSkip}) {
  const names=CONSOLE_ROUTES.map(r=>r.name);
  exact(captured,names,"desktop");
  exact(accessibilityRoutes,names,"accessibility");
  const mobileRows=mobile?.filter(row=>row?.name?.endsWith("-mobile")&&row.name!=="project-detail-mobile");
  exact(mobileRows,names.map(x=>x+"-mobile"),"mobile");
  if (mobile.length!==names.length+1 ||
      mobile.find(row=>row.name==="project-detail-mobile")?.verifiedWithoutMutation!==true) {
    throw new Error("console_surface_mobile_detail_missing");
  }
  if (!keyboardSkip || keyboardSkip.reachedWithTab!==true ||
      keyboardSkip.visibleOnFocus!==true || keyboardSkip.landedOnMain!==true) {
    throw new Error("console_surface_keyboard_skip_invalid");
  }
  for (const reference of CONSOLE_ROUTES) {
    const desktop=captured.find(row=>row.name===reference.name);
    const a11y=accessibilityRoutes.find(row=>row.route===reference.name);
    const phone=mobileRows.find(row=>row.name===reference.name+"-mobile");
    if (desktop.path!==reference.path || desktop.width!==reference.width ||
        !Number.isInteger(desktop.status) || desktop.status<200 || desktop.status>=300 ||
        !desktop.documentSize || desktop.documentSize.width<1) {
      throw new Error("console_surface_desktop_unverified:"+reference.name);
    }
    if (a11y.checked!==true || a11y.unnamedCount!==0 ||
        a11y.duplicateIds!==0 || a11y.missingImageAlt!==0 ||
        a11y.positiveTabOrder!==0) {
      throw new Error("console_surface_accessibility_unverified:"+reference.name);
    }
    if (!phone.accessibility || phone.accessibility.checked!==true ||
        phone.accessibility.unnamedCount!==0 ||
        phone.accessibility.missingImageAlt!==0 ||
        phone.accessibility.duplicateIds!==0 ||
        phone.accessibility.positiveTabOrder!==0) {
      throw new Error("console_surface_mobile_accessibility_unverified:"+reference.name);
    }
    if (phone.path!==reference.path ||
        !Number.isInteger(phone.status) || phone.status<200 || phone.status>=300 ||
        !phone.layout || phone.layout.innerWidth!==390 ||
        !Number.isFinite(phone.layout.scrollWidth) ||
        phone.layout.scrollWidth>phone.layout.innerWidth+2 ||
        !phone.readability || phone.readability.mainLandmark!==true ||
        phone.readability.keyboardSkipPresent!==true ||
        !phone.expandedLayout ||
        phone.expandedLayout.width>phone.expandedLayout.viewport+2 ||
        JSON.stringify(phone.quickNavHrefs)!==JSON.stringify(["/","/projects","/gates"])) {
      throw new Error("console_surface_mobile_unverified:"+reference.name);
    }
  }
  return {
    schema:"factory-console-executed-surface-coverage-v1",
    desktopRoutes:names.length,
    mobileRoutes:names.length,
    accessibleRoutes:names.length,
    verifiedRealProjectDetailOnMobile:true,
    keyboardSkipTested:true,
    routeNames:names,
    requiresIndependentAuthenticatedArtifactReview:true,
    fullErrorLoadingEmptyStateMatrixVerified:false,
    productExperienceCertified:false,
    writes:0,
    paidCalls:0,
  };
}
