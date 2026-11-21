"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {requirePreviewTitleAndHeading}=require("../preview_application_identity.cjs");

const input={
  title:"AI Product Factory",
  heading:"Entrar na Factory",
  expectedText:"Entrar na Factory",
  expectedTitle:"AI Product Factory",
};

test("real Factory login heading and branded document title are independent identity proofs",()=>{
  assert.equal(requirePreviewTitleAndHeading(input),null);
  assert.equal(requirePreviewTitleAndHeading({
    ...input,heading:"  Entrar\n na Factory  ",title:"  AI Product Factory  "
  }),null);
});

test("SSO or generic login must not impersonate application identity",()=>{
  for(const title of ["Sign in to Vercel","Vercel Authentication",
                      "Authentication required","",null,
                      "Another Product","x".repeat(161)]){
    assert.equal(requirePreviewTitleAndHeading({...input,title}),
                 "preview_application_title_unverified",String(title));
  }
});

test("branded title alone cannot substitute missing page heading",()=>{
  for(const heading of ["Entrar","Sign in to Vercel","",null,
                        "Not your Studio", "Entrar na outra Factory"]){
    assert.equal(requirePreviewTitleAndHeading({...input,heading}),
                 "preview_application_heading_unverified",String(heading));
  }
});

test("a separate optional title policy works for unrelated client apps",()=>{
  assert.equal(requirePreviewTitleAndHeading({
    title:"Dark Channel Studio — Login",heading:"Dark Channel Studio",
    expectedText:"Dark Channel Studio",
  }),null);
  assert.equal(requirePreviewTitleAndHeading({
    title:"Dark Channel Studio — Login",heading:"Dark Channel Studio",
    expectedText:"Dark Channel Studio",expectedTitle:"Infodive CRM",
  }),"preview_application_title_unverified");
  assert.equal(requirePreviewTitleAndHeading({
    title:"Wrong App",heading:"Expected Studio",
    expectedText:"Expected Studio",
  }),null);
  // Without a separate title marker, the trusted review relies on verified
  // app main + h1; never manufacture a branded-title assertion.
});
