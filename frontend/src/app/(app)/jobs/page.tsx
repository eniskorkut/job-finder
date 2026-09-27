"use client";

import { JobList } from "@/components/app/job-list";
import { MockNotice } from "@/components/app/mock-notice";
import { PageHeader } from "@/components/app/page-header";

export default function JobsPage() {
  return (
    <>
      <PageHeader
        title="İş İlanlarım"
        description="Yalnızca sizin hesabınıza ait ilanlar ve eşleşme puanları listelenir."
      />
      <div className="mb-4">
        <MockNotice />
      </div>
      <JobList />
    </>
  );
}
