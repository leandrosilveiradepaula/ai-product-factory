"use strict";
// The visible project-bound marker belongs to <main> AND its H1.
// The document title is a separate first-party application identity, not
// necessarily the same phrase as the route's visible heading.
const {normalizeVisibleText,containsExpectedText}=require("./preview_text_match.cjs");

const providerTitles = new Set([
  "sign in to vercel",
  "log in to vercel",
  "vercel authentication",
  "deployment protection",
  "authentication required",
]);

function requirePreviewTitleAndHeading({title,heading,expectedText,expectedTitle=""}={}){
  if(!containsExpectedText(normalizeVisibleText(heading),expectedText))
    return "preview_application_heading_unverified";
  const documentTitle=normalizeVisibleText(title);
  if(!documentTitle || documentTitle.length>160 || providerTitles.has(documentTitle.toLowerCase()))
    return "preview_application_title_unverified";
  if(expectedTitle && !containsExpectedText(documentTitle,expectedTitle))
    return "preview_application_title_unverified";
  return null;
}

module.exports={requirePreviewTitleAndHeading};
