import { CourseWorkspace } from "@/components/course-workspace";

export default async function CoursePage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await params;
  return <CourseWorkspace courseId={courseId} />;
}
