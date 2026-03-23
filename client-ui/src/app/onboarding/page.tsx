import { PageHeader } from "@/components/dashboard-ui";
import { ProjectOnboardingConsole } from "@/components/project-onboarding-console";

export const dynamic = "force-dynamic";

export default function OnboardingPage() {
  return (
    <main className="space-y-6">
      <PageHeader
        eyebrow="Project onboarding"
        title="Connect a project, store secrets securely, and prepare sandbox execution"
        description="Use this guided flow to bootstrap a project, connect GitHub or GitLab, sync repositories, store runtime secrets in AWS Secrets Manager, and create the repo profile that powers sandbox verification."
      />
      <ProjectOnboardingConsole />
    </main>
  );
}
