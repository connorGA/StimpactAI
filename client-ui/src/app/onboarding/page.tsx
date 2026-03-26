import { PageHeader } from "@/components/dashboard-ui";
import { ProjectOnboardingConsole } from "@/components/project-onboarding-console";

export const dynamic = "force-dynamic";

export default function OnboardingPage() {
  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Project onboarding"
        title="Create a protected project, then connect repositories and sandbox verification"
        description="Use this authenticated onboarding flow to create the first project in your workspace, connect GitHub or GitLab, store runtime secrets securely, and define the repo profile that powers sandbox execution."
      />
      <ProjectOnboardingConsole />
    </main>
  );
}
