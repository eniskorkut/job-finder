"use client";

import { TeamView } from "@/components/app/team-view";
import { useSession } from "@/components/app/session-provider";
import { PageHeader } from "@/components/app/page-header";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ShieldAlert } from "lucide-react";

export default function TeamPage() {
  const { user, loading } = useSession();

  return (
    <>
      <PageHeader
        title="Davetler"
        description="İkinci kullanıcıyı süreli ve tek kullanımlık bağlantı ile davet edin."
      />
      {!loading && user && user.role !== "owner" ? (
        <Card>
          <EmptyState
            icon={ShieldAlert}
            title="Bu sayfa yalnızca owner kullanıcı içindir"
            description="Davet oluşturma yetkisi ilk (owner) kullanıcıya aittir."
          />
        </Card>
      ) : (
        <TeamView />
      )}
    </>
  );
}
