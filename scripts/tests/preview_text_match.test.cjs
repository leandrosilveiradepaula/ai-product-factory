const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeVisibleText, containsExpectedText } = require("../preview_text_match.cjs");

test("layout whitespace does not reject a verified visible phrase", () => {
  assert.equal(containsExpectedText("INFODIVE\nCRM\tNEXT GEN", "INFODIVE CRM"), true);
  assert.equal(containsExpectedText("Bem-vindo de volta", "Bem-vindo de volta"), true);
});
test("wrong expectation still fails; document title cannot satisfy body proof", () => {
  assert.equal(containsExpectedText("Bem-vindo de volta", "CRM IBM/Lenovo"), false);
  assert.equal(containsExpectedText("", "Bem-vindo"), false);
  assert.equal(containsExpectedText("only a page title", ""), false);
});
test("does not strip punctuation or change case to manufacture a match", () => {
  assert.equal(containsExpectedText("CRM IBM/Lenovo", "CRM IBM Lenovo"), false);
  assert.equal(containsExpectedText("INFODIVE CRM", "infodive crm"), false);
  assert.equal(normalizeVisibleText("  hello \n   world\t"), "hello world");
});
