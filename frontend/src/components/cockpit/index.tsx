"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { CockpitHeader } from "./cockpit-header";
import { TabGlobe } from "./tab-globe";
import { TabJobs } from "./tab-jobs";
import { TabIntegrations } from "./tab-integrations";
import { TabCv } from "./tab-cv";
import { TabSync } from "./tab-sync";
import { JobDetailModal } from "./job-detail-modal";
import { ToastNotificationContainer } from "./toast-notification";
import { CITY_DATABASE } from "./mock-data";
import type { CityHub, Dossier, TabId, ToastItem } from "./types";

export function ExecutiveCockpit() {
  const [activeTab, setActiveTab] = useState<TabId>("tab-globe");
  const [activeCityKey, setActiveCityKey] = useState("london");
  const [activeDossierIdx, setActiveDossierIdx] = useState(0);
  const [selectedSkill, setSelectedSkill] = useState("");
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [modalJob, setModalJob] = useState<Dossier | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [triggerScanToken, setTriggerScanToken] = useState(0);

  // Backend real jobs state
  const [backendDossiers, setBackendDossiers] = useState<Dossier[]>([]);

  const showToast = useCallback((message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3500);
  }, []);

  // Fetch real jobs from backend API
  const fetchBackendJobs = useCallback(async () => {
    try {
      const resp = await fetch("/api/v1/jobs?page_size=100");
      if (resp.ok) {
        const data = await resp.json();
        if (data && Array.isArray(data.items) && data.items.length > 0) {
          const mapped: Dossier[] = data.items
            .filter((item: any) => !item.is_mock)
            .map((item: any) => ({
              id: item.id,
              title: item.title,
              company: item.company,
              location: item.location || "Remote",
              salary: item.salary_text || "$180,000 - $240,000",
              score: `${item.score || 94}% CV FIT`,
              ref: `JOB-${item.id.slice(0, 6).toUpperCase()}`,
              freshness: "YENİ EKLENDİ",
              analysis:
                item.description ||
                "Özel kariyer kaynağından canlı olarak çekilen güncel pozisyon.",
              skills: [
                "Distributed Systems",
                "Python FastAPI",
                "Cloud Architecture",
                "Next.js",
              ],
              tier: "Staff / Lead",
              source: "Özel ATS Tarayıcısı",
              telegram: "Kişisel VIP Kanalına Aktarıldı",
              cityKey: "london",
              cityName: "Londra",
              application_url: item.application_url || "https://www.linkedin.com/jobs",
            }));
          setBackendDossiers(mapped);
        }
      }
    } catch {
      // Backend not running or offline, fallback cleanly to mock
    }
  }, []);

  useEffect(() => {
    fetchBackendJobs();
  }, [fetchBackendJobs]);

  // Merge database with any live backend dossiers
  const mergedCities = useMemo(() => {
    const base: Record<string, CityHub> = JSON.parse(JSON.stringify(CITY_DATABASE));
    if (backendDossiers.length > 0 && base.london) {
      base.london.dossiers = [...backendDossiers, ...base.london.dossiers];
      base.london.count = base.london.dossiers.length;
    }
    return base;
  }, [backendDossiers]);

  // Aggregate all dossiers for TabJobs
  const allDossiers = useMemo(() => {
    const list: Dossier[] = [];
    Object.entries(mergedCities).forEach(([cKey, hub]) => {
      hub.dossiers.forEach((d) => {
        list.push({
          ...d,
          cityKey: cKey,
          cityName: hub.name,
        });
      });
    });
    return list;
  }, [mergedCities]);

  const handleOpenModal = (dossier: Dossier) => {
    setModalJob(dossier);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setModalJob(null);
  };

  const handleSelectSkill = (skill: string) => {
    setSelectedSkill(skill);
    setActiveTab("tab-jobs");
    showToast(`'${skill}' yeteneğine göre filtrelendi.`);
  };

  const handleQuickSync = () => {
    setActiveTab("tab-sync");
    setTriggerScanToken((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-[#020203] text-white selection:bg-white selection:text-black">
      {/* Top Header & Navigation */}
      <CockpitHeader
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onQuickSync={handleQuickSync}
        totalJobCount={allDossiers.length}
      />

      {/* Main Workspace Tabs */}
      <main className="max-w-7xl mx-auto px-3 sm:px-6 md:px-8 mt-4 sm:mt-6 pb-12">
        {activeTab === "tab-globe" && (
          <TabGlobe
            cities={mergedCities}
            activeCityKey={activeCityKey}
            onSelectCity={(key) => {
              setActiveCityKey(key);
              setActiveDossierIdx(0);
            }}
            activeDossierIdx={activeDossierIdx}
            onSelectDossier={setActiveDossierIdx}
            onOpenModal={handleOpenModal}
            onSelectSkill={handleSelectSkill}
          />
        )}

        {activeTab === "tab-jobs" && (
          <TabJobs
            cities={mergedCities}
            allDossiers={allDossiers}
            selectedSkill={selectedSkill}
            onSelectSkill={setSelectedSkill}
            onOpenModal={handleOpenModal}
          />
        )}

        {activeTab === "tab-integrations" && (
          <TabIntegrations
            onShowToast={showToast}
            onRefreshJobs={fetchBackendJobs}
          />
        )}

        {activeTab === "tab-cv" && <TabCv onShowToast={showToast} />}

        {activeTab === "tab-sync" && (
          <TabSync
            onShowToast={showToast}
            triggerScanToken={triggerScanToken}
          />
        )}
      </main>

      {/* Application & AI Cover Letter Modal */}
      <JobDetailModal
        job={modalJob}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onShowToast={showToast}
      />

      {/* Floating Toast Notification Container */}
      <ToastNotificationContainer toasts={toasts} />
    </div>
  );
}

export default ExecutiveCockpit;
