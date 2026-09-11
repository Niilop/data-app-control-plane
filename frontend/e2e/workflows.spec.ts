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

test("template catalogue, bundle download, revision snapshot and offline validation", async ({
  page,
}) => {
  await login(page, "developer");
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Bundles", exact: true }).click();
  await expect(page.getByText("Python batch application 1.0.0")).toBeVisible();
  const artifacts = (
    await request(page, `/api/v1/applications/${app.id}/artifacts`)
  ).items;
  const bundle = artifacts.find(
    (item: { kind: string }) => item.kind === "generated_bundle",
  );
  const report = artifacts.find(
    (item: { kind: string }) => item.kind === "validation_report",
  );
  expect(bundle.media_type).toBe("application/zip");
  expect(bundle.provenance.template_name).toBe("python-batch");

  // The download is the stored bytes and matches the recorded digest.
  const download = await page.request.fetch(
    `/api/v1/artifacts/${bundle.digest}`,
    {
      headers,
    },
  );
  expect(download.ok(), await download.text()).toBeTruthy();
  expect(download.headers()["x-artifact-digest"]).toBe(bundle.digest);
  const body = await download.body();
  const digest = await page.evaluate(
    async (bytes) => {
      const hash = await crypto.subtle.digest("SHA-256", new Uint8Array(bytes));
      return [...new Uint8Array(hash)]
        .map((value) => value.toString(16).padStart(2, "0"))
        .join("");
    },
    [...body],
  );
  expect(digest).toBe(bundle.digest);
  expect(body.subarray(0, 2).toString()).toBe("PK");

  // Generation is real local work and must never be labelled simulated.
  const started = await page.request.fetch(
    `/api/v1/applications/${app.id}/generations`,
    {
      method: "POST",
      headers: { ...headers, "Idempotency-Key": "browser-second-generation" },
      data: {
        template_name: "python-batch",
        template_version: "1.0.0",
        binding_id: bundle.provenance.parameters.bundle_target
          ? (
              await request(page, `/api/v1/applications/${app.id}/bindings`)
            ).items.find(
              (item: { bundle_target: string }) =>
                item.bundle_target ===
                bundle.provenance.parameters.bundle_target,
            ).id
          : undefined,
        package_name: "second_package",
      },
    },
  );
  expect(started.status(), await started.text()).toBe(202);
  const accepted = await started.json();
  expect(accepted.execution_mode).toBe("local");
  const queued = await request(
    page,
    `/api/v1/operations/${accepted.operation_id}`,
  );
  expect(queued.kind).toBe("bundle_generation");
  expect(queued.execution_mode).toBe("local");
  await page.getByRole("tab", { name: "Operations", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: /bundle generation/i }).first(),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Revisions", exact: true }).click();
  const revision = (
    await request(page, `/api/v1/applications/${app.id}/revisions`)
  ).items[0];
  await page
    .getByRole("button", { name: `View revision ${revision.id}` })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(revision.scope_digest)).toBeVisible();
  await expect(dialog.getByText(revision.artifact_digest)).toBeVisible();
  await expect(dialog.getByText("simulated://browser-dev")).toBeVisible();
  await expect(
    dialog.getByText("Offline checks", { exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText("passed", { exact: true })).toBeVisible();
  await expect(
    dialog.getByText("not evidence of workspace validity"),
  ).toBeVisible();
  // The scope is recorded and shown as offline, with an explicit disclaimer.
  await expect(dialog.getByText("are not workspace validation")).toBeVisible();
  const validations = (
    await request(page, `/api/v1/revisions/${revision.id}/validations`)
  ).items;
  expect(validations.map((item: { scope: string }) => item.scope)).toEqual([
    "offline",
  ]);
  expect(validations[0].result).toBe("passed");

  // The captured snapshot is immutable: no edit route exists for it.
  const patch = await page.request.fetch(`/api/v1/revisions/${revision.id}`, {
    method: "PATCH",
    headers,
    data: { bundle_target: "qa" },
  });
  expect(patch.status()).toBe(405);
  expect(report.provenance.scope).toBe("offline");
  await dialog.getByRole("button", { name: "Close dialog" }).click();
  await expect(dialog).not.toBeVisible();
});

test("viewer sees delivery records but cannot generate or capture", async ({
  page,
}) => {
  await login(page, "viewer");
  const app = await existing(page);
  await page.goto(`/applications/${app.id}`);
  await page.getByRole("tab", { name: "Bundles", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Generate bundle" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: /generated bundle/i }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Revisions", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Capture revision" }),
  ).toHaveCount(0);
  const revision = (
    await request(page, `/api/v1/applications/${app.id}/revisions`)
  ).items[0];
  // Hidden controls are usability; the API is the authority.
  const denied = await page.request.fetch(
    `/api/v1/revisions/${revision.id}/validations`,
    {
      method: "POST",
      headers: { ...headers, "Idempotency-Key": "viewer-validation" },
      data: { scope: "offline" },
    },
  );
  expect(denied.status()).toBe(403);
  const outsider = await page.request.fetch(
    `/api/v1/applications/${app.id}/generations`,
    {
      method: "POST",
      headers: { ...headers, "Idempotency-Key": "viewer-generation" },
      data: {
        template_name: "python-batch",
        template_version: "1.0.0",
        binding_id: revision.binding_id,
        package_name: "viewer_attempt",
      },
    },
  );
  expect(outsider.status()).toBe(403);
});
