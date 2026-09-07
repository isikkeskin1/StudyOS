import { expect, test } from "@playwright/test";

// Exercise the new timer against real session endpoints, including a reload and
// a client clock that reaches zero without mutating the server-owned session.
test("focus countdown survives reload and never auto-completes", async ({ page }, testInfo) => {
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email: `focus-${testInfo.project.name}-${Date.now()}@studyos.local`, password: "studyos-focus-test-password" },
  });
  expect(registered.status()).toBe(201);
  const created = await page.request.post("/api/v1/courses", {
    data: { name: "Physics I", target_grade: 25, max_grade: 30 },
  });
  expect(created.status()).toBe(201);
  const course = await created.json() as { id: string };
  for (const [name, text] of [
    ["notes.txt", "Mechanics\nForce mass acceleration dynamics Newton law.\n\nMomentum\nMomentum conservation collisions impulse.\n\nOscillations\nPeriod frequency spring amplitude."],
    ["exam.txt", "Written Exam\nQuestion 1 (12 marks)\nMomentum and impulse.\n\nQuestion 2 (8 marks)\nForce and acceleration.\n\nQuestion 3 (2 marks)\nOscillator period."],
  ]) {
    const uploaded = await page.request.post(`/api/v1/courses/${course.id}/documents`, {
      multipart: { file: { name, mimeType: "text/plain", buffer: Buffer.from(text) } },
    });
    expect(uploaded.status()).toBe(201);
    const document = await uploaded.json() as { id: string };
    expect((await page.request.post(`/api/v1/courses/${course.id}/documents/${document.id}/process`)).ok()).toBeTruthy();
  }
  expect((await page.request.post(`/api/v1/courses/${course.id}/analyze`)).ok()).toBeTruthy();
  expect((await page.request.post(`/api/v1/courses/${course.id}/exam-intelligence/analyze`)).ok()).toBeTruthy();
  const queueResponse = await page.request.post("/api/v1/semester-queues", {
    data: { available_hours: 2, block_minutes: 30, courses: [{ course_id: course.id, baseline_mastery: 0.35 }] },
  });
  expect(queueResponse.status()).toBe(201);
  const queue = await queueResponse.json() as { id: string };

  await page.clock.install();
  await page.goto("/");
  await page.getByRole("button", { name: "Start focus block" }).click();
  await expect(page.getByText("Time remaining", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Time remaining", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete", exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
  await page.screenshot({ path: testInfo.outputPath("focus-active.png"), fullPage: true, animations: "disabled" });

  await page.clock.fastForward(31 * 60 * 1000);
  await expect(page.getByRole("timer")).toHaveText("00:00");
  await expect(page.getByText("Ready to complete", { exact: true })).toBeVisible();
  const sessionsResponse = await page.request.get(`/api/v1/semester-queues/${queue.id}/focus-sessions`);
  expect(sessionsResponse.ok()).toBeTruthy();
  const sessions = await sessionsResponse.json() as Array<{ id: string; status: string }>;
  const active = sessions.find((session) => session.status === "active");
  expect(active).toBeDefined();

  await page.getByRole("button", { name: "Skip", exact: true }).click();
  await expect(page.getByText("Time remaining", { exact: true })).toHaveCount(0);
  const after = await page.request.get(`/api/v1/semester-queues/${queue.id}/focus-sessions`);
  expect((await after.json() as Array<{ id: string; status: string }>).find((session) => session.id === active?.id)?.status).toBe("skipped");
});
