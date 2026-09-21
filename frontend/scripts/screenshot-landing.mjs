// Dev utility: capture the landing page and the auth modal for visual review.
// Usage (dev server must be running): node scripts/screenshot-landing.mjs [baseUrl]
import { chromium } from "playwright";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text());
});
page.on("pageerror", (err) => errors.push(String(err)));

await page.goto(baseUrl, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
await page.screenshot({ path: "screenshots/landing-full.png", fullPage: true });
console.log("captured: screenshots/landing-full.png");

await page.getByRole("button", { name: "Enter FinGuru" }).first().click();
await page.waitForTimeout(400);
await page.screenshot({ path: "screenshots/landing-modal.png" });
console.log("captured: screenshots/landing-modal.png");

if (errors.length) {
  console.log("console/page errors:");
  for (const err of errors) console.log(`  ${err}`);
  process.exitCode = 1;
} else {
  console.log("no console errors");
}

await browser.close();
