import { expect, test } from "@playwright/test";

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(overflow.document).toBeLessThanOrEqual(overflow.viewport + 1);
  expect(overflow.body).toBeLessThanOrEqual(overflow.viewport + 1);
}

test("account, setup, dashboard, workspace, and search stay usable", async ({
  page,
}, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  const email = `e2e-${suffix}@studyos.local`;
  const courseName = `E2E Physics ${suffix}`;

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Continue your semester." })).toBeVisible();

  await page.getByRole("button", { name: "New to StudyOS? Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("studyos-e2e-password");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(
    page.getByRole("heading", { name: "Build your first study command center." }),
  ).toBeVisible();

  await page.getByLabel("Course name").fill(courseName);
  const createResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/courses") &&
      response.request().method() === "POST" &&
      response.status() === 201,
  );
  await page.getByRole("button", { name: "Create course" }).click();
  const course = (await (await createResponse).json()) as { id: string; name: string };
  expect(course.name).toBe(courseName);

  await expect(page.getByRole("heading", { name: new RegExp(`Import ${courseName}`) })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Semester command center" })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  const search = page.getByPlaceholder(
    "Search courses, topics, sources, mistakes, practice…",
  );
  await expect(search).toBeVisible();
  await search.fill(courseName);
  await expect(page.getByText(courseName, { exact: true }).first()).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto(`/courses/${course.id}`);
  await expect(page.getByText("Current course", { exact: true })).toBeVisible();
  await expect(page.getByText(courseName, { exact: true }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole("button", { name: "Search" }).first().click();
  await search.fill(courseName);
  await expect(page.getByText(courseName, { exact: true }).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("mobile interactive controls keep touch-sized targets", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile"));

  const email = `touch-${Date.now()}@studyos.local`;
  await page.goto("/");
  await page.getByRole("button", { name: "New to StudyOS? Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("studyos-touch-password");
  await page.getByRole("button", { name: "Create account" }).click();

  await expectNoHorizontalOverflow(page);

  const controls = page.locator(
    'button:visible, input:visible, select:visible, a:visible',
  );
  const count = Math.min(await controls.count(), 20);
  for (let index = 0; index < count; index += 1) {
    const box = await controls.nth(index).boundingBox();
    if (!box) continue;
    expect(
      Math.max(box.width, box.height),
      `control ${index} should expose a usable touch target`,
    ).toBeGreaterThanOrEqual(36);
  }
});
