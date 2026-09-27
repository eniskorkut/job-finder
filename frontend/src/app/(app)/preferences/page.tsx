"use client";

import { CVManager } from "@/components/app/cv-manager";
import { PageHeader } from "@/components/app/page-header";
import { PasswordChangeForm } from "@/components/app/password-change-form";
import { PreferencesForm } from "@/components/app/preferences-form";

export default function PreferencesPage() {
  return (
    <>
      <PageHeader
        title="CV ve Tercihler"
        description="CV'niz ve pozisyon tercihleriniz yalnızca sizin hesabınızda saklanır."
      />
      <div className="flex flex-col gap-5">
        <CVManager />
        <PreferencesForm />
        <PasswordChangeForm />
      </div>
    </>
  );
}
