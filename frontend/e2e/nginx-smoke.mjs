// Runs only with tests/compose.browser.yaml and its disposable API database.
import assert from "node:assert/strict";
import { chromium } from "@playwright/test";

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto("http://frontend/applications");
  assert.equal(response.status(), 200);
  assert.match(
    response.headers()["content-security-policy"],
    /default-src 'self'/,
  );
  await page.getByLabel("Email or username").fill("admin");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-test-password1!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("heading", { name: "Applications", exact: true })
    .waitFor();
  assert.equal(
    (await page.request.get("http://frontend/auth/me")).status(),
    200,
  );
  assert.equal((await page.request.get("http://frontend/ready")).status(), 200);
  await page.getByRole("link", { name: "Teams", exact: true }).click();
  await page.getByRole("button", { name: "Create team", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Team name")
    .fill("Docker smoke team");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create team", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Docker smoke team members" })
    .waitFor();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.reload();
  await page.getByRole("heading", { name: "Teams", exact: true }).waitFor();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("heading", { name: "Welcome back" }).waitFor();
  assert.equal(
    (await page.request.get("http://frontend/auth/me")).status(),
    401,
  );
  assert.deepEqual(errors, []);
  console.log(
    "nginx production smoke passed: routing, CSP, login, cookie reload, authenticated write, readiness and logout",
  );
} finally {
  await browser.close();
}
