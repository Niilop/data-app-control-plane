import { test, expect, type Page } from "@playwright/test";

const headers = {
  Origin: "http://127.0.0.1:5174",
  "X-Control-Plane": "browser",
};
async function login(page: Page, username = "admin") {
  await page.goto("/applications");
  await page.getByLabel("Email or username").fill(username);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-test-password1!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Applications", exact: true }),
  ).toBeVisible();
}
async function request(
  page: Page,
  path: string,
  method = "GET",
  data?: object,
) {
  const response = await page.request.fetch(path, { method, data, headers });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.status() === 204 ? undefined : response.json();
}
async function existing(page: Page) {
  const result = await request(page, "/api/v1/applications");
  return result.items.find(
    (app: { slug: string }) => app.slug === "customer-analytics",
  );
}

test("existing login, HTTP-only session, reload, profile and logout", async ({
  page,
  context,
}) => {
  await login(page);
  const cookies = await context.cookies();
  expect(
    cookies.find((cookie) => cookie.name === "control_plane_session"),
  ).toMatchObject({ httpOnly: true, sameSite: "Strict" });
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "control_plane_session",
  );
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Applications", exact: true }),
  ).toBeVisible();
  await page.goto("/account");
  await expect(
    page.getByText("admin@example.test", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
});

test("registration, validation and empty application list", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page
    .getByLabel("Email", { exact: true })
    .fill("new-member@example.com");
  await page.getByLabel("Username", { exact: true }).fill("new-member");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-test-password1!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByText("Account created. Sign in to continue."),
  ).toBeVisible();
  await login(page, "new-member");
  await expect(
    page.getByRole("heading", { name: "Your first application starts here" }),
  ).toBeVisible();
});

test("application registration, stale edit, successful edit, ownership and audit", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("button", { name: "Register application", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Slug", { exact: false }).fill("sales-browser");
  await dialog.getByLabel("Application name").fill("Sales reporting");
  await dialog
    .getByLabel("GitHub repository URL")
    .fill("https://example.com/invalid");
  await dialog.getByLabel("Owning team").selectOption({ label: "Engineering" });
  await dialog
    .getByRole("button", { name: "Register application", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("repository_url");
  await dialog
    .getByLabel("GitHub repository URL")
    .fill("https://github.com/example/sales");
  await dialog
    .getByRole("button", { name: "Register application", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sales reporting", exact: true }),
  ).toBeVisible();
  const appPath = "/api/v1/applications/" + page.url().split("/").pop();
  await page
    .getByRole("button", { name: "Edit application", exact: true })
    .click();
  await request(page, appPath, "PATCH", {
    expected_version: 1,
    name: "Concurrent sales edit",
  });
  await dialog.getByLabel("Application name").fill("Stale sales edit");
  await dialog
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "changed since you opened",
  );
  expect((await request(page, appPath)).name).toBe("Concurrent sales edit");
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Concurrent sales edit" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit application", exact: true })
    .click();
  await dialog.getByLabel("Application name").fill("Sales reporting");
  await dialog
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sales reporting", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Manage ownership" }).click();
  await dialog.getByLabel("Data owner user ID").fill("2");
  await dialog
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  expect((await request(page, appPath)).data_owner_user_id).toBe(2);
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(
    page.getByText("application · registered", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/application-desktop.png",
    fullPage: true,
  });
});

test("team create, membership add and remove", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Teams", exact: true }).click();
  await page.getByRole("button", { name: "Create team", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Team name").fill("Quality assurance");
  await dialog
    .getByRole("button", { name: "Create team", exact: true })
    .click();
  await expect(
    dialog.getByRole("heading", { name: "Quality assurance members" }),
  ).toBeVisible();
  await dialog.getByLabel("User ID").fill("4");
  await dialog.getByRole("button", { name: "Add member" }).click();
  await expect(dialog.getByText("User #4", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Remove user 4" }).click();
  await expect(dialog.getByText("User #4", { exact: true })).not.toBeVisible();
});

test("environment policy, binding, and stale binding version", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Environments", exact: true }).click();
  await page
    .getByRole("button", { name: "Create environment", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Environment name").fill("Browser sandbox");
  await dialog
    .getByLabel("Workspace reference")
    .fill("simulated://browser-new");
  await dialog.getByLabel("Allow local self-approval").check();
  await dialog
    .getByRole("button", { name: "Create environment", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Browser sandbox" }),
  ).toBeVisible();
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Environments", exact: true }).click();
  await page.getByRole("button", { name: "Bind environment" }).click();
  await dialog
    .getByRole("combobox", { name: "Environment", exact: true })
    .selectOption({ label: "Browser sandbox" });
  await dialog.getByLabel("Bundle target").selectOption("sandbox");
  await dialog.getByRole("button", { name: "Create binding" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser sandbox" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit binding for Browser sandbox" })
    .click();
  const env = (await request(page, "/api/v1/environments")).items.find(
    (e: { name: string }) => e.name === "Browser sandbox",
  );
  await request(page, `/api/v1/environments/${env.id}`, "PATCH", {
    expected_version: env.version,
    allow_self_approval: false,
  });
  await dialog.getByLabel("Synthetic row count").fill("200");
  await dialog.getByRole("button", { name: "Save binding" }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "changed since you opened",
  );
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  // Hold the real refreshed list response: old snapshots must not be editable.
  let releaseRefresh!: () => void;
  const refreshed = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const bindingsURL = `**/api/v1/applications/${app.id}/bindings?*`;
  await page.route(bindingsURL, async (route) => {
    await refreshed;
    await route.continue();
  });
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  const editBinding = page.getByRole("button", {
    name: "Edit binding for Browser sandbox",
  });
  await expect(editBinding).toBeDisabled();
  await expect(
    page.getByText("Refreshing records…", { exact: true }),
  ).toBeVisible();
  releaseRefresh();
  await expect(editBinding).toBeEnabled();
  await page.unroute(bindingsURL);
  await page
    .getByRole("button", { name: "Edit binding for Browser sandbox" })
    .click();
  await expect(dialog.getByText("Editing binding version 2.")).toBeVisible();
  await dialog.getByLabel("Synthetic row count").fill("200");
  await dialog.getByRole("button", { name: "Save binding" }).click();
  await expect(dialog).not.toBeVisible();
  await page.goto("/environments");
  await page
    .getByRole("button", { name: "Edit Browser sandbox", exact: true })
    .click();
  await dialog.getByLabel("Environment enabled").uncheck();
  await dialog.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByText("Disabled", { exact: true }).first(),
  ).toBeVisible();
});

test("direct and team role administration and revoked editor policy", async ({
  page,
  browser,
}) => {
  await login(page);
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Access", exact: true }).click();
  await page.getByRole("button", { name: "Assign role", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("User ID").fill("4");
  await dialog
    .getByRole("combobox", { name: "Role", exact: true })
    .selectOption("developer");
  await dialog
    .getByRole("button", { name: "Assign role", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  const other = await browser.newContext();
  const editor = await other.newPage();
  await login(editor, "outsider");
  await editor.goto(`/applications/${app.id}`);
  await editor
    .getByRole("button", { name: "Edit application", exact: true })
    .click();
  await page.getByRole("button", { name: "Remove developer for 4" }).click();
  await dialog.getByRole("button", { name: "Remove assignment" }).click();
  await expect(dialog).not.toBeVisible();
  await editor
    .getByRole("dialog")
    .getByLabel("Application name")
    .fill("Unauthorized change");
  await editor
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(editor.getByRole("alert")).toContainText(
    "Application not found",
  );
  expect((await request(page, `/api/v1/applications/${app.id}`)).name).toBe(
    "Customer analytics",
  );
  await other.close();
  await page.getByRole("button", { name: "Assign role", exact: true }).click();
  await dialog.getByLabel("Subject type").selectOption("team");
  await dialog
    .getByRole("combobox", { name: "Team", exact: true })
    .selectOption({ label: "Engineering" });
  await dialog
    .getByRole("combobox", { name: "Role", exact: true })
    .selectOption("approver");
  await dialog
    .getByRole("button", { name: "Assign role", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText("approver", { exact: true })).toBeVisible();
});

test("viewer controls and API denial remain authoritative", async ({
  page,
}) => {
  await login(page, "viewer");
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await expect(
    page.getByRole("button", { name: "Edit application", exact: true }),
  ).not.toBeVisible();
  await page.getByRole("tab", { name: "Environments", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Bind environment" }),
  ).not.toBeVisible();
  const denied = await page.request.patch(`/api/v1/applications/${app.id}`, {
    headers,
    data: { expected_version: app.version, name: "Denied" },
  });
  expect(denied.status()).toBe(403);
  await page.goto("/environments");
  await expect(
    page.getByRole("heading", { name: "Environments", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create environment" }),
  ).not.toBeVisible();
});

test("operation attempts, cancellation, transport retry deduplication and reconciliation", async ({
  page,
}) => {
  await login(page);
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Operations", exact: true }).click();
  const operations = (
    await request(page, `/api/v1/applications/${app.id}/operations`)
  ).items;
  const queued = operations.find(
    (o: { status: string }) => o.status === "queued",
  );
  const failed = operations.find(
    (o: { status: string }) => o.status === "failed",
  );
  const unknown = operations.find(
    (o: { status: string }) => o.status === "needs_attention",
  );
  const dialog = page.getByRole("dialog");
  await page
    .getByRole("button", { name: `View operation ${queued.id}` })
    .click();
  await dialog.getByRole("button", { name: "Request cancellation" }).click();
  await expect(dialog).not.toBeVisible();
  expect((await request(page, `/api/v1/operations/${queued.id}`)).status).toBe(
    "cancelled",
  );
  await page
    .getByRole("button", { name: `View operation ${failed.id}` })
    .click();
  await expect(dialog.getByText("failed", { exact: true })).toHaveCount(2); // status and actual attempt outcome
  const keys: string[] = [];
  await page.route(`**/api/v1/operations/${failed.id}/retry`, async (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    const response = await route.fetch(); // commit the command before simulating a lost response
    if (keys.length === 1) await route.abort("failed");
    else await route.fulfill({ response });
  });
  await dialog
    .getByRole("button", { name: "Retry operation", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Unable to reach the API",
  );
  await dialog
    .getByRole("button", { name: "Retry operation", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const after = (
    await request(page, `/api/v1/applications/${app.id}/operations`)
  ).items;
  expect(
    after.filter((o: { retry_of: string }) => o.retry_of === failed.id),
  ).toHaveLength(1);
  await page
    .getByRole("button", { name: `View operation ${unknown.id}` })
    .click();
  await dialog
    .getByLabel("Reason to reconcile")
    .fill("Inspect the latest simulated observation");
  await dialog.getByRole("button", { name: "Request reconciliation" }).click();
  await expect(dialog).not.toBeVisible();
  expect((await request(page, `/api/v1/operations/${unknown.id}`)).status).toBe(
    "reconciling",
  );
});

test("pagination, network failure, expired session and narrow keyboard navigation", async ({
  page,
  context,
}) => {
  await login(page);
  for (let index = 0; index < 21; index++)
    await request(page, "/api/v1/teams", "POST", {
      name: `Pagination team ${index}`,
    });
  await page.goto("/teams");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Page 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(page.getByText("Page 1", { exact: true })).toBeVisible();
  await page.route("**/api/v1/teams?*", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Unable to reach the API",
  );
  await page.unroute("**/api/v1/teams?*");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/applications");
  await page.getByRole("button", { name: "Toggle navigation" }).click();
  await page.getByRole("link", { name: "Teams", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Teams", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create team", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create team", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/teams-mobile.png",
    fullPage: true,
  });
  await context.clearCookies();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await expect(
    page.getByText("Your session has ended. Sign in to continue."),
  ).toBeVisible();
});

test("generate, download, capture and validate an immutable revision offline", async ({
  page,
}) => {
  await login(page);
  const app = await existing(page);
  const environment = await request(page, "/api/v1/environments", "POST", {
    name: "Preparation browser",
    workspace_ref: "simulated://preparation",
    allowed_executor: "simulated",
    allowed_bundle_targets: ["prepare"],
  });
  await request(page, `/api/v1/applications/${app.id}/bindings`, "POST", {
    environment_id: environment.id,
    bundle_target: "prepare",
  });
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Preparation", exact: true }).click();
  const binding = page
    .getByRole("listitem")
    .filter({ hasText: "Preparation browser / prepare" });
  await binding.getByRole("button", { name: "Generate bundle" }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Python package name")
    .fill("batch_browser");
  await page.getByRole("button", { name: "Queue generation" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect
    .poll(async () => {
      const rows = await request(
        page,
        `/api/v1/applications/${app.id}/generations`,
      );
      return rows.items.some(
        (g: { artifact_digest: string | null }) => g.artifact_digest,
      );
    })
    .toBeTruthy();
  await page.reload();
  await page.getByRole("tab", { name: "Preparation", exact: true }).click();
  const generation = page
    .getByRole("listitem")
    .filter({ hasText: "batch_browser / prepare" });
  const download = page.waitForEvent("download");
  await generation.getByRole("link", { name: "Download bundle" }).click();
  expect((await download).suggestedFilename()).toMatch(/^[a-f0-9]{64}\.zip$/);
  await generation.getByRole("button", { name: "Capture revision" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Capture revision" })
    .click();
  await page.getByRole("button", { name: "View revision" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("Config SHA-256:", { exact: false }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Validate offline" }).click();
  await expect
    .poll(async () => {
      const rows = await request(
        page,
        `/api/v1/applications/${app.id}/revisions`,
      );
      const reports = await request(
        page,
        `/api/v1/revisions/${rows.items[0].id}/validations`,
      );
      return reports.items[0]?.result;
    })
    .toBe("passed");
  await page.reload();
  await page.getByRole("tab", { name: "Preparation", exact: true }).click();
  await page.getByRole("button", { name: "View revision" }).first().click();
  await expect(
    page.getByText("Offline checks passed", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download offline report" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/preparation-desktop.png",
    fullPage: false,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/preparation-mobile.png",
    fullPage: false,
  });
});

test("approve exact scope, simulate deployment and retain last success after partial failure", async ({
  page,
}) => {
  await login(page);
  const app = await existing(page);
  await request(page, `/api/v1/applications/${app.id}/roles`, "POST", {
    user_id: 1,
    role: "approver",
  });
  const environment = await request(page, "/api/v1/environments", "POST", {
    name: "Deployment browser",
    workspace_ref: "simulated://deployment-browser",
    allowed_executor: "simulated",
    allowed_bundle_targets: ["deploy"],
    allow_self_approval: true,
  });
  const bound = await request(
    page,
    `/api/v1/applications/${app.id}/bindings`,
    "POST",
    {
      environment_id: environment.id,
      bundle_target: "deploy",
    },
  );
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Preparation", exact: true }).click();
  await page
    .getByRole("listitem")
    .filter({ hasText: "Deployment browser / deploy" })
    .getByRole("button", { name: "Generate bundle" })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Python package name")
    .fill("batch_deployment");
  await page.getByRole("button", { name: "Queue generation" }).click();
  await expect
    .poll(
      async () =>
        (
          await request(page, `/api/v1/applications/${app.id}/generations`)
        ).items.find(
          (g: { parameters: { package_name: string } }) =>
            g.parameters.package_name === "batch_deployment",
        )?.artifact_digest,
    )
    .toBeTruthy();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page
    .getByRole("listitem")
    .filter({ hasText: "batch_deployment / deploy" })
    .getByRole("button", { name: "Capture revision" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Capture revision" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const revision = (
    await request(page, `/api/v1/applications/${app.id}/revisions`)
  ).items.find((r: { binding_id: string }) => r.binding_id === bound.id);
  await page
    .getByRole("listitem")
    .filter({ hasText: revision.id })
    .getByRole("button", { name: "View revision" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Validate offline" }).click();
  await expect
    .poll(
      async () =>
        (await request(page, `/api/v1/revisions/${revision.id}/validations`))
          .items[0]?.result,
    )
    .toBe("passed");
  await page.reload();
  await page.getByRole("tab", { name: "Preparation", exact: true }).click();
  await page
    .getByRole("listitem")
    .filter({ hasText: revision.id })
    .getByRole("button", { name: "View revision" })
    .click();
  await expect(
    dialog.getByText("Scope SHA-256:", { exact: false }),
  ).toBeVisible();
  await dialog
    .getByText(
      "Review source, template, configuration, target, policy and report",
    )
    .click();
  await expect(dialog.locator("pre")).toContainText(revision.artifact_digest);
  await dialog
    .getByLabel("Decision reason")
    .fill("Review exact synthetic revision for local simulation");
  await dialog.getByRole("button", { name: "Record decision" }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Local self-approval requires",
  );
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Record decision" }).click();
  await expect(
    dialog.getByText("Local self-approval acknowledged", { exact: false }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/approval-desktop.png" });
  // Commit once then lose the response; UI retries the same command key.
  const keys: string[] = [];
  await page.route(
    `**/api/v1/applications/${app.id}/deployments`,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      keys.push(route.request().headers()["idempotency-key"]);
      const response = await route.fetch();
      if (keys.length === 1) await route.abort("failed");
      else await route.fulfill({ response });
    },
  );
  await dialog
    .getByRole("button", { name: "Submit simulated deployment" })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Unable to reach the API",
  );
  await dialog
    .getByRole("button", { name: "Submit simulated deployment" })
    .click();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await expect
    .poll(
      async () =>
        (
          await request(
            page,
            `/api/v1/applications/${app.id}/bindings/${bound.id}/last-success`,
          )
        )?.status,
    )
    .toBe("succeeded");
  const success = await request(
    page,
    `/api/v1/applications/${app.id}/bindings/${bound.id}/last-success`,
  );
  await page.unroute(`**/api/v1/applications/${app.id}/deployments`);
  await dialog
    .getByLabel("Simulation scenario")
    .selectOption("partial_failure");
  await dialog
    .getByRole("button", { name: "Submit simulated deployment" })
    .click();
  await expect
    .poll(async () =>
      (
        await request(page, `/api/v1/applications/${app.id}/deployments`)
      ).items.some((d: { status: string }) => d.status === "failed"),
    )
    .toBeTruthy();
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("tab", { name: "Deployments", exact: true }).click();
  await page.getByLabel("Last-success binding").selectOption(bound.id);
  await expect(
    page.getByText(`Deployment: ${success.id}`, { exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByText("synthetic_job: created", { exact: false }),
  ).toBeVisible();
  expect(
    (await request(page, `/api/v1/applications/${app.id}/deployments`)).items,
  ).toHaveLength(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/deployments-mobile.png",
    fullPage: true,
  });
});

test("simulated job success, failure, lost response and recorded dashboard", async ({
  page,
}) => {
  await login(page);
  const seed = await existing(page);
  const app = await request(page, "/api/v1/applications", "POST", {
    slug: "job-run-browser",
    name: "Job run browser",
    description: "Run simulation checks",
    owning_team_id: seed.owning_team_id,
    owner_user_id: 1,
    data_owner_user_id: 1,
    repository_url: "https://github.com/example/job-run-browser",
    bundle_root: ".",
  });
  for (const role of ["operator", "approver"]) {
    await request(page, `/api/v1/applications/${app.id}/roles`, "POST", {
      user_id: 1,
      role,
    });
  }
  const env = await request(page, "/api/v1/environments", "POST", {
    name: "Job run browser",
    workspace_ref: "simulated://job-run-browser",
    allowed_executor: "simulated",
    allowed_bundle_targets: ["sandbox"],
    allow_self_approval: true,
  });
  const binding = await request(
    page,
    `/api/v1/applications/${app.id}/bindings`,
    "POST",
    { environment_id: env.id, bundle_target: "sandbox" },
  );
  async function command(path: string, data: object) {
    const response = await page.request.post(path, {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data,
    });
    expect(response.status(), await response.text()).toBe(202);
    const operation = await response.json();
    await expect
      .poll(
        async () =>
          (await request(page, `/api/v1/operations/${operation.operation_id}`))
            .status,
      )
      .toBe("succeeded");
  }
  await command(`/api/v1/applications/${app.id}/generations`, {
    binding_id: binding.id,
    expected_binding_version: 1,
  });
  const generation = (
    await request(page, `/api/v1/applications/${app.id}/generations`)
  ).items[0];
  const revision = await request(
    page,
    `/api/v1/applications/${app.id}/revisions`,
    "POST",
    {
      generation_id: generation.id,
      binding_id: binding.id,
      expected_binding_version: 1,
    },
  );
  await command(`/api/v1/revisions/${revision.id}/validations`, {
    scope: "offline",
  });
  const report = (
    await request(page, `/api/v1/revisions/${revision.id}/validations`)
  ).items[0];
  const scope = await request(
    page,
    `/api/v1/revisions/${revision.id}/approval-scope?validation_id=${report.id}`,
  );
  const approval = await request(
    page,
    `/api/v1/revisions/${revision.id}/approvals`,
    "POST",
    {
      validation_id: report.id,
      scope_digest: scope.scope_digest,
      decision: "approved",
      reason: "Local run test",
      acknowledge_local_self_approval: true,
    },
  );
  await command(`/api/v1/applications/${app.id}/deployments`, {
    revision_id: revision.id,
    approval_id: approval.id,
    binding_id: binding.id,
    execution_mode: "simulated",
  });
  const deployment = (
    await request(page, `/api/v1/applications/${app.id}/deployments`)
  ).items[0];
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Deployments", exact: true }).click();
  await page
    .getByRole("button", { name: "Run simulated job", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Synthetic row count").fill("7");
  const keys: string[] = [];
  await page.route(
    `**/api/v1/deployments/${deployment.id}/runs`,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      keys.push(route.request().headers()["idempotency-key"]);
      const response = await route.fetch();
      if (keys.length <= 2) await route.abort("failed");
      else await route.fulfill({ response });
    },
  );
  await dialog.getByRole("button", { name: "Queue simulated run" }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Unable to reach the API",
  );
  await dialog.getByRole("button", { name: "Queue simulated run" }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Unable to reach the API",
  );
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const runsPath = `/api/v1/deployments/${deployment.id}/runs`;
  await expect
    .poll(async () => (await request(page, runsPath)).items[0]?.status)
    .toBe("succeeded");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  // Hold the capability refresh so the controls definitely unmount before retry.
  let releaseCapabilities!: () => void;
  const capabilitiesHeld = new Promise<void>((resolve) => {
    releaseCapabilities = resolve;
  });
  const capabilitiesPath = `**/api/v1/applications/${app.id}/capabilities`;
  await page.route(capabilitiesPath, async (route) => {
    const response = await route.fetch();
    await capabilitiesHeld;
    await route.fulfill({ response });
  });
  const capabilitiesReloaded = page.waitForResponse((response) =>
    response.url().endsWith(`/applications/${app.id}/capabilities`),
  );
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run simulated job", exact: true }),
  ).toHaveCount(0);
  releaseCapabilities();
  await capabilitiesReloaded;
  await page.unroute(capabilitiesPath);
  await page
    .getByRole("button", { name: "Run simulated job", exact: true })
    .click();
  await dialog.getByLabel("Synthetic row count").fill("7");
  await dialog.getByRole("button", { name: "Queue simulated run" }).click();
  await expect(dialog).not.toBeVisible();
  expect(keys).toHaveLength(3);
  expect(new Set(keys).size).toBe(1);
  expect((await request(page, runsPath)).items).toHaveLength(1);
  // An acknowledged command permits another deliberate run with identical input.
  await page
    .getByRole("button", { name: "Run simulated job", exact: true })
    .click();
  await dialog.getByLabel("Synthetic row count").fill("7");
  await dialog.getByRole("button", { name: "Queue simulated run" }).click();
  await expect(dialog).not.toBeVisible();
  expect(keys).toHaveLength(4);
  expect(keys[3]).not.toBe(keys[0]);
  await page.unroute(`**/api/v1/deployments/${deployment.id}/runs`);
  await expect
    .poll(async () => (await request(page, runsPath)).items[1]?.status)
    .toBe("succeeded");
  expect((await request(page, runsPath)).items).toHaveLength(2);
  await page
    .getByRole("button", { name: "Run simulated job", exact: true })
    .click();
  await dialog.getByLabel("Run simulation scenario").selectOption("failure");
  await dialog.getByRole("button", { name: "Queue simulated run" }).click();
  await expect(dialog).not.toBeVisible();
  await expect
    .poll(async () => (await request(page, runsPath)).items[2]?.status)
    .toBe("failed");
  expect(
    (await request(page, `/api/v1/deployments/${deployment.id}`)).status,
  ).toBe("succeeded");
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Simulated output: 7 rows, total 21.", { exact: false }),
  ).toHaveCount(2);
  await expect(
    page.getByText("The simulated job failed. Deployment status is unchanged."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Operation history", exact: true }),
  ).toBeVisible();
  await page.getByText("Approval history for this revision").click();
  await expect(
    page.getByText(`Scope SHA-256: ${scope.scope_digest}`),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/runs-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/runs-mobile.png",
    fullPage: true,
  });
  const roles = (await request(page, `/api/v1/applications/${app.id}/roles`))
    .items;
  const operator = roles.find(
    (r: { user_id: number; role: string }) =>
      r.user_id === 1 && r.role === "operator",
  );
  await request(
    page,
    `/api/v1/applications/${app.id}/roles/${operator.id}`,
    "DELETE",
  );
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("tab", { name: "Deployments", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run simulated job", exact: true }),
  ).toHaveCount(0);
  await page.getByText("Job run history", { exact: true }).click();
  await expect(
    page
      .getByText("Simulated output: 7 rows, total 21.", { exact: false })
      .first(),
  ).toBeVisible();
});
