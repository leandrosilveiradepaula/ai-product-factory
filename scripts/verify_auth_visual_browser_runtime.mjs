// Safe pre-credential runner smoke: actual pinned Playwright Chromium, no
// network, no Supabase user, no console session and no external URL.
import {chromium} from "playwright";

const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();
  await page.goto("data:text/html,%3Ctitle%3Eauthenticated-visual-runtime%3C%2Ftitle%3E",
                  {waitUntil:"load",timeout:10000});
  const title=await page.title();
  if(title!=="authenticated-visual-runtime"){
    throw new Error("pinned Chromium did not render a local document");
  }
  console.log("authenticated_visual_browser_runtime=verified_offline");
} finally {
  await browser.close();
}
