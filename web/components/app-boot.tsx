import { BrandMark } from "@/components/ui-icon";

type AppBootProps = {
  label?: string;
  detail?: string;
  compact?: boolean;
};

export function AppBoot({
  label = "Opening your workspace",
  detail = "Syncing courses, priorities, and progress",
  compact = false,
}: AppBootProps) {
  return (
    <main className={`studyos-boot${compact ? " is-compact" : ""}`} aria-live="polite" aria-busy="true">
      <div className="studyos-boot-aura" aria-hidden="true" />
      <section className="studyos-boot-core">
        <div className="studyos-boot-mark" aria-hidden="true">
          <span className="studyos-boot-orbit orbit-a" />
          <span className="studyos-boot-orbit orbit-b" />
          <span className="studyos-boot-orbit orbit-c" />
          <span className="studyos-boot-brand"><BrandMark /></span>
        </div>

        <div className="studyos-boot-copy">
          <span className="studyos-boot-kicker">StudyOS</span>
          <strong>{label}</strong>
          <small>{detail}</small>
        </div>

        <div className="studyos-boot-progress" aria-hidden="true">
          <span />
        </div>

        <div className="studyos-boot-skeleton" aria-hidden="true">
          <span className="boot-skeleton-primary" />
          <span />
          <span />
        </div>
      </section>
    </main>
  );
}
