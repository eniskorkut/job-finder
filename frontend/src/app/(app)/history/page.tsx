"use client";

import { HistoryView } from "@/components/app/history-view";
import { PageHeader } from "@/components/app/page-header";

export default function HistoryPage() {
  return (
    <>
      <PageHeader
        title="Tarama Geçmişi"
        description="Kendi hesabınıza ait tarama ve bildirim kayıtları."
      />
      <HistoryView />
    </>
  );
}
