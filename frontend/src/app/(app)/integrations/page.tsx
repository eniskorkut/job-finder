"use client";

import { PageHeader } from "@/components/app/page-header";
import { IntegrationsView } from "@/components/app/integrations-view";

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Entegrasyonlar"
        description="Gmail, Hotmail/Outlook ve Telegram bağlantıları kişiye özeldir; DeepSeek anahtarı tüm kullanıcılar için ortaktır."
      />
      <IntegrationsView />
    </>
  );
}
