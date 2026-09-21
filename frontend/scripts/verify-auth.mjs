// Dev utility: verify the Phase 3 auth wiring against the running dev server.
// Usage: node scripts/verify-auth.mjs [baseUrl]
import { chromium } from "playwright";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text());
});
page.on("pageerror", (err) => errors.push(String(err)));

// 1. Guard: unauthenticated /track must bounce to the landing page.
await page.goto(`${baseUrl}/track`, { waitUntil: "networkidle" });
await page.waitForTimeout(600);
const guardUrl = page.url();
const onLanding = await page
  .getByRole("heading", { level: 1, name: /your financial command center/i })
  .isVisible();
console.log(`guard: /track -> ${guardUrl} (landing visible: ${onLanding})`);

// 2. Real failed login: wrong credentials against the live Supabase project.
await page.getByRole("button", { name: "Enter FinGuru" }).first().click();
await page.getByLabel("Email").fill("phase3-verify@finguru.invalid");
await page.getByLabel("Password").fill("definitely-not-the-password");
await page.screenshot({ path: "screenshots/auth-modal-filled.png" });
await page.getByRole("button", { name: "Log in to FinGuru" }).click();
try {
  await page.waitForSelector('[role="alert"]', { timeout: 30000 });
  const alertText = (await page.locator('[role="alert"]').textContent())?.trim();
  console.log(`failed-login inline error shown: ${/wrong email or password|too many attempts/i.test(alertText ?? "")} ("${alertText}")`);
} catch {
  console.log("failed-login inline error shown: false (no alert within 30s)");
}
await page.screenshot({ path: "screenshots/auth-modal-error.png" });

// 3. Reset flow view.
await page.getByRole("button", { name: "Forgot password?" }).click();
await page.screenshot({ path: "screenshots/auth-modal-reset.png" });
const resetVisible = await page
  .getByRole("button", { name: "Send reset link" })
  .isVisible();
console.log(`reset view reachable: ${resetVisible}`);

if (errors.length) {
  console.log("console/page errors:");
  for (const err of errors) console.log(`  ${err}`);
  process.exitCode = 1;
} else {
  console.log("no console errors");
}

await browser.close();
