// Read-only, numeric accessibility checks for the existing authenticated
// Console capture. No DOM text, field values or operator/session data leave
// the browser; on failure emit only a fixed code and vetted route name.
export function collectAccessibilitySnapshot() {
  const doc = document;
  const visible = element => {
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" &&
      element.getClientRects().length > 0;
  };
  const hasName = element => {
    const attr = name => (element.getAttribute(name) || "").trim();
    if (attr("aria-label")) return true;
    const labelledBy = attr("aria-labelledby");
    if (labelledBy && labelledBy.split(/\s+/).some(id =>
      Boolean(doc.getElementById(id)?.textContent?.trim()))) return true;
    if (element.labels?.length && [...element.labels].some(label =>
      Boolean(label.textContent?.trim()))) return true;
    if (["submit", "button", "reset"].includes((element.getAttribute("type") || "").toLowerCase())
        && element.getAttribute("value")?.trim()) return true;
    if (element.querySelector?.("img[alt]")?.getAttribute("alt")?.trim()) return true;
    if (element.textContent?.trim()) return true;
    return Boolean(attr("title"));
  };
  const controls = [...doc.querySelectorAll(
    'button,a[href],input:not([type="hidden"]),select,textarea,summary,[role="button"],[role="link"]'
  )].filter(visible);
  const unnamed = controls.filter(element => !hasName(element));
  const ids = [...doc.querySelectorAll("[id]")].map(element => element.id);
  const skip = doc.querySelector('a.skipToMain[href="#main-content"]');
  const main = doc.querySelector("main#main-content");
  return {
    language: doc.documentElement.getAttribute("lang") || "",
    hasTitle: Boolean(doc.title?.trim()),
    mainCount: doc.querySelectorAll("main").length,
    mainTarget: Boolean(main && main.tabIndex === -1),
    skipCount: doc.querySelectorAll('a.skipToMain[href="#main-content"]').length,
    skipHasName: Boolean(skip && hasName(skip)),
    h1Count: doc.querySelectorAll("h1").length,
    interactiveCount: controls.length,
    unnamedCount: unnamed.length,
    missingImageAlt: doc.querySelectorAll("img:not([alt])").length,
    duplicateIds: ids.length - new Set(ids).size,
    positiveTabOrder: [...doc.querySelectorAll("[tabindex]")].filter(
      element => element.tabIndex > 0 && visible(element)).length,
  };
}

const METRIC_FIELDS = [
  "mainCount", "skipCount", "h1Count", "interactiveCount", "unnamedCount",
  "missingImageAlt", "duplicateIds", "positiveTabOrder",
];
export function verifyAccessibilitySnapshot(snapshot, routeName) {
  if (typeof routeName !== "string" || !/^[a-z0-9-]{1,36}$/.test(routeName))
    throw new Error("accessibility:invalid_route");
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot))
    throw new Error("accessibility:malformed_snapshot:" + routeName);
  if (METRIC_FIELDS.some(key => !Number.isSafeInteger(snapshot[key]) || snapshot[key] < 0) ||
      typeof snapshot.language !== "string" ||
      typeof snapshot.hasTitle !== "boolean" ||
      typeof snapshot.mainTarget !== "boolean" ||
      typeof snapshot.skipHasName !== "boolean")
    throw new Error("accessibility:malformed_metrics:" + routeName);
  const failures = [];
  if (snapshot.language.toLowerCase() !== "pt-br") failures.push("document_language");
  if (!snapshot.hasTitle) failures.push("document_title");
  if (snapshot.mainCount !== 1 || !snapshot.mainTarget) failures.push("main_landmark");
  if (snapshot.skipCount !== 1 || !snapshot.skipHasName) failures.push("skip_link");
  if (snapshot.h1Count < 1) failures.push("page_heading");
  if (snapshot.interactiveCount < 1) failures.push("interactive_inventory");
  if (snapshot.unnamedCount !== 0) failures.push("interactive_names");
  if (snapshot.missingImageAlt !== 0) failures.push("image_alternatives");
  if (snapshot.duplicateIds !== 0) failures.push("unique_ids");
  if (snapshot.positiveTabOrder !== 0) failures.push("tab_order");
  if (failures.length)
    throw new Error("accessibility:" + routeName + ":" + failures.join(","));
  // Whitelist only numeric/Boolean values. Never persist DOM text, URLs,
  // labels, input contents, accessible names, tokens or screenshots here.
  return {
    checked:true, landmarkCount:snapshot.mainCount, headingCount:snapshot.h1Count,
    interactiveCount:snapshot.interactiveCount, unnamedCount:0,
    missingImageAlt:0, duplicateIds:0, positiveTabOrder:0,
  };
}
