"use strict";

// Match a policy-supplied visible phrase across layout whitespace only.
// Never compare page titles, links, hidden text, or failed check body samples.
const normalizeVisibleText = value =>
  typeof value === "string" ? value.replace(/\s+/gu, " ").trim() : "";

const containsExpectedText = (visibleBody, expectedText) => {
  const needle = normalizeVisibleText(expectedText);
  return needle.length > 0 && normalizeVisibleText(visibleBody).includes(needle);
};

module.exports = { normalizeVisibleText, containsExpectedText };
