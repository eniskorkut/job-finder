"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import { CockpitHeader } from "./cockpit-header";
import { ToastNotificationContainer } from "./toast-notification";
import { KNOWN_CITIES } from "./city-coordinates";
import { mapJobToDossier } from "./job-mapper";
import { api } from "@/lib/api";
import type { CityHub, Dossier, TabId, ToastItem } from "./types";

// Dynamic imports to slash first-load JS by 40-60%
const TabGlobe = dynamic(() => import("./tab-globe").then((m) => m.TabGlobe), {
  ssr: false,
});
const TabJobs = dynamic(() => import("./tab-jobs").then((m) => m.TabJobs), {
  ssr: false,
});
const TabIntegrations = dynamic(
  () => import("./tab-integrations").then((m) => m.TabIntegrations),
  { ssr: false }
);
const TabCv = dynamic(() => import("./tab-cv").then((m) => m.TabCv), {
  ssr: false,
});
const TabSync = dynamic(() => import("./tab-sync").then((m) => m.TabSync), {
  ssr: false,
});
const JobDetailModal = dynamic(
  () => import("./job-detail-modal").then((m) => m.JobDetailModal),
  { ssr: false }
);

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

  // Fetch real jobs from backend API using 30s cache
  const fetchBackendJobs = useCallback(async () => {
    try {
      const data = await api.get<{ items?: any[] }>("/api/v1/jobs?page_size=100");
      if (data && Array.isArray(data.items)) {
        const mapped: Dossier[] = data.items
          .filter((item: any) => !item.is_mock)
          .map(mapJobToDossier);
        setBackendDossiers(mapped);
      } else {
        setBackendDossiers([]);
      }
    } catch {
      setBackendDossiers([]);
    }
  }, []);

  useEffect(() => {
    fetchBackendJobs();
  }, [fetchBackendJobs]);

  // Construct city hubs from real backend dossiers
  const mergedCities = useMemo(() => {
    const base: Record<string, CityHub> = {};
    for (const [key, city] of Object.entries(KNOWN_CITIES)) {
      base[key] = {
        name: city.name,
        lat: city.lat,
        lng: city.lng,
        count: 0,
        dossiers: [],
      };
    }

    for (const dossier of backendDossiers) {
      const cityKey = dossier.cityKey || "remote";
      if (!base[cityKey]) {
        base[cityKey] = {
          name: dossier.cityName || "UZAKTAN / GLOBAL",
          lat: 20.0,
          lng: 0.0,
          count: 0,
          dossiers: [],
        };
      }
      base[cityKey].dossiers.push(dossier);
      base[cityKey].count = base[cityKey].dossiers.length;
    }

    return base;
  }, [backendDossiers]);

  // Auto-select city with jobs if current city has 0 jobs
  useEffect(() => {
    if (backendDossiers.length > 0) {
      const currentCount = mergedCities[activeCityKey]?.count || 0;
      if (currentCount === 0) {
        const firstWithJobs = Object.keys(mergedCities).find(
          (k) => mergedCities[k].count > 0
        );
        if (firstWithJobs) {
          setActiveCityKey(firstWithJobs);
        }
      }
    }
  }, [backendDossiers, mergedCities, activeCityKey]);

  // Aggregate all dossiers for TabJobs
  const allDossiers = useMemo(() => {
    return backendDossiers;
  }, [backendDossiers]);

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

      {/* Application & Job Detail Modal - Lazy Mounted */}
      {isModalOpen && modalJob && (
        <JobDetailModal
          job={modalJob}
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          onShowToast={showToast}
        />
      )}

      {/* Floating Toast Notification Container */}
      <ToastNotificationContainer toasts={toasts} />
    </div>
  );
}

export default ExecutiveCockpit;
