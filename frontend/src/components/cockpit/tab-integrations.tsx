"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/components/app/session-provider";
import type {
  IntegrationsResponse,
  SiteVerificationItem,
  TelegramStatus,
  VerifySitesResponse,
} from "@/lib/types";

interface TabIntegrationsProps {
  onShowToast: (msg: string) => void;
  onRefreshJobs: () => void;
}

const DEFAULT_SITES = [
  "stripe.com/jobs",
  "linear.app/careers",
  "vercel.com/careers",
  "openai.com/careers",
  "anthropic.com/careers",
];

export function TabIntegrations({
  onShowToast,
  onRefreshJobs,
}: TabIntegrationsProps) {
  const { user } = useSession();
  const [customSites, setCustomSites] = useState<string[]>(DEFAULT_SITES);
  const [newSiteInput, setNewSiteInput] = useState("");
  const [isCrawling, setIsCrawling] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationResults, setVerificationResults] = useState<Record<string, SiteVerificationItem>>({});

  // Telegram integration states
  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus | null>(null);
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [savingTelegram, setSavingTelegram] = useState(false);
  const [testingTelegram, setTestingTelegram] = useState(false);

  // Email / OAuth integration states
  const [integrationsData, setIntegrationsData] = useState<IntegrationsResponse | null>(null);

  const storageKey = `job_hunter_custom_sites:${user?.id || "anon"}`;

  // Load custom sites from user-scoped localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        setCustomSites(JSON.parse(saved));
      } else {
        setCustomSites(DEFAULT_SITES);
      }
    } catch {
      setCustomSites(DEFAULT_SITES);
    }
  }, [storageKey]);

  // Load real Telegram & OAuth integrations status
  useEffect(() => {
    api
      .get<TelegramStatus>("/api/v1/integrations/telegram/status")
      .then((data) => {
        setTelegramStatus(data);
        if (data.chat_id) setTelegramChatId(data.chat_id);
      })
      .catch(() => {});

    api
      .get<IntegrationsResponse>("/api/v1/integrations")
      .then((data) => setIntegrationsData(data))
      .catch(() => {});
  }, []);

  const saveSitesToStorage = (sites: string[]) => {
    setCustomSites(sites);
    try {
      localStorage.setItem(storageKey, JSON.stringify(sites));
    } catch {}
  };

  const handleAddCustomSite = async () => {
    let val = newSiteInput.trim().toLowerCase();
    if (!val) {
      onShowToast("Lütfen taranacak bir web sitesi veya kariyer sayfası adresi girin.");
      return;
    }
    val = val.replace(/^https?:\/\//, "").replace(/\/$/, "");
    if (customSites.includes(val)) {
      onShowToast(`'${val}' zaten tarama listesinde kayıtlı.`);
      return;
    }

    const updated = [...customSites, val];
    saveSitesToStorage(updated);
    setNewSiteInput("");
    setIsCrawling(true);
    onShowToast(`'${val}' taranıyor ve ilanlar çekiliyor...`);

    try {
      const res = await api.post<{ message?: string; job_id?: string }>(
        "/api/v1/integrations/custom-sites/crawl",
        { url: val }
      );
      onShowToast(res?.message || `'${val}' tarama kuyruğuna eklendi.`);
      onRefreshJobs();
    } catch {
      onShowToast(`'${val}' adresine bağlanılamadı.`);
    } finally {
      setIsCrawling(false);
    }
  };

  const handleRemoveSite = (siteToRemove: string) => {
    const updated = customSites.filter((s) => s !== siteToRemove);
    saveSitesToStorage(updated);
    onShowToast(`'${siteToRemove}' listeden kaldırıldı.`);
  };

  const handleVerifyAll = async () => {
    if (isVerifying || customSites.length === 0) return;
    setIsVerifying(true);
    onShowToast("Kayıtlı kariyer sayfaları doğrulanıyor...");

    try {
      // Bounded to 20 sites maximum
      const sitesToCheck = customSites.slice(0, 20);
      const res = await api.post<VerifySitesResponse>(
        "/api/v1/integrations/custom-sites/verify",
        { sites: sitesToCheck }
      );

      const mapping: Record<string, SiteVerificationItem> = {};
      for (const item of res.results) {
        mapping[item.site] = item;
      }
      setVerificationResults(mapping);
      onShowToast(`${res.active_sites}/${res.total_checked} kaynak aktif ve erişilebilir.`);
    } catch {
      onShowToast("Doğrulama işlemi sırasında hata oluştu.");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSaveTelegram = async () => {
    if (!telegramToken.trim()) {
      onShowToast("Lütfen geçerli bir Telegram Bot Token girin.");
      return;
    }
    setSavingTelegram(true);
    try {
      const res = await api.post<TelegramStatus>("/api/v1/integrations/telegram", {
        bot_token: telegramToken.trim(),
        chat_id: telegramChatId.trim() || undefined,
      });
      setTelegramStatus(res);
      setTelegramToken("");
      onShowToast("Telegram bot entegrasyonu başarıyla kaydedildi.");
    } catch {
      onShowToast("Telegram yapılandırması kaydedilemedi.");
    } finally {
      setSavingTelegram(false);
    }
  };

  const handleTestTelegram = async () => {
    setTestingTelegram(true);
    try {
      await api.post("/api/v1/integrations/telegram/test");
      onShowToast("Telegram test bildirimi başarıyla iletildi.");
    } catch {
      onShowToast("Test mesajı gönderilemedi. Token ve Chat ID'yi kontrol edin.");
    } finally {
      setTestingTelegram(false);
    }
  };

  const handleDetectTelegramChat = async () => {
    try {
      const res = await api.post<{ chat_id?: string; username?: string }>(
        "/api/v1/integrations/telegram/detect-chat"
      );
      if (res.chat_id) {
        setTelegramChatId(res.chat_id);
        onShowToast(`Chat ID tespit edildi: ${res.chat_id}`);
      } else {
        onShowToast("Yeni mesaj bulunamadı. Lütfen botunuza Telegram'da /start yazın.");
      }
    } catch {
      onShowToast("Chat ID tespiti başarısız oldu.");
    }
  };

  return (
    <div id="tab-integrations" className="tab-pane space-y-6">
      {/* Custom Sites / ATS Web Crawler */}
      <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-white/15">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-white shadow-[0_0_8px_#ffffff]" />
              <h2 className="text-xl font-bold font-mono text-white tracking-wide">
                ÖZEL WEB &amp; ATS TARAMA MOTORU
              </h2>
            </div>
            <p className="text-xs text-white/50 font-mono mt-1">
              Kariyer sayfalarını ve ATS portallarını (Greenhouse, Lever, Ashby, Workday) doğrudan tarar.
            </p>
          </div>

          <button
            type="button"
            onClick={handleVerifyAll}
            disabled={isVerifying}
            className="lux-press px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold flex items-center gap-2 self-start md:self-auto disabled:opacity-50"
          >
            <span>{isVerifying ? "Doğrulanıyor..." : "Kaynakları Doğrula (Max 4 Eşzamanlı)"}</span>
          </button>
        </div>

        {/* Input Bar */}
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={newSiteInput}
            onChange={(e) => setNewSiteInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddCustomSite()}
            placeholder="örnek: jobs.lever.co/anthropic veya stripe.com/jobs"
            className="flex-1 bg-[#040405] border border-white/20 rounded-xl px-4 py-3 text-xs font-mono text-white placeholder-white/30 focus:border-white focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddCustomSite}
            disabled={isCrawling}
            className="silver-btn lux-press px-6 py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2 text-white disabled:opacity-50"
          >
            <span>{isCrawling ? "Taranıyor..." : "Siteyi Ekle & Tara"}</span>
          </button>
        </div>

        {/* Sites List */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
          {customSites.map((site) => {
            const vResult = verificationResults[site];
            return (
              <div
                key={site}
                className="flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/25 transition-all font-mono text-xs"
              >
                <div className="min-w-0 pr-2">
                  <div className="text-white font-semibold truncate">{site}</div>
                  <div className="text-[10px] text-white/40 mt-0.5">
                    {vResult ? (
                      <span className={vResult.status === "ok" ? "text-emerald-400" : "text-amber-400"}>
                        {vResult.status === "ok" ? `Aktif (${vResult.jobs_found} ilan)` : "Erişim hatası"}
                      </span>
                    ) : (
                      "Kayıtlı Tarama Rotası"
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveSite(site)}
                  className="text-white/40 hover:text-white p-1 text-sm font-bold"
                  title="Listeden Çıkar"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Telegram VIP Notifications */}
      <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
        <div className="flex items-center justify-between pb-6 border-b border-white/15">
          <div>
            <div className="flex items-center gap-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  telegramStatus?.connected ? "bg-emerald-400" : "bg-zinc-600"
                }`}
              />
              <h2 className="text-xl font-bold font-mono text-white tracking-wide">
                TELEGRAM VIP BİLDİRİM KONSOLU
              </h2>
            </div>
            <p className="text-xs text-white/50 font-mono mt-1">
              Yüksek uyumlu iş fırsatlarını anında Telegram kanalınıza veya özel sohbetinize aktarır.
            </p>
          </div>

          <div className="font-mono text-xs">
            {telegramStatus?.connected ? (
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                BAĞLI ({telegramStatus.bot_username || "Aktif Bot"})
              </span>
            ) : (
              <span className="px-3 py-1 rounded-full bg-white/5 text-white/50 border border-white/10">
                BAĞLI DEĞİL
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
          <div>
            <label className="block text-[10px] text-white/50 uppercase mb-1">
              Telegram Bot Token (BotFather)
            </label>
            <input
              type="password"
              value={telegramToken}
              onChange={(e) => setTelegramToken(e.target.value)}
              placeholder={telegramStatus?.connected ? "•••••••••••••••••••• (Gizlendi)" : "Token girin"}
              className="w-full bg-[#040405] border border-white/20 rounded-xl px-4 py-3 text-xs text-white focus:border-white focus:outline-none"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-[10px] text-white/50 uppercase">
                Telegram Chat ID
              </label>
              <button
                type="button"
                onClick={handleDetectTelegramChat}
                className="text-emerald-400 hover:underline text-[10px] cursor-pointer"
              >
                Chat ID Tespit Et ↺
              </button>
            </div>
            <input
              type="text"
              value={telegramChatId}
              onChange={(e) => setTelegramChatId(e.target.value)}
              placeholder="Örn: 123456789 veya -100123456789"
              className="w-full bg-[#040405] border border-white/20 rounded-xl px-4 py-3 text-xs text-white focus:border-white focus:outline-none"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={handleSaveTelegram}
            disabled={savingTelegram}
            className="silver-btn lux-press px-6 py-2.5 rounded-xl text-xs font-mono uppercase tracking-wider text-white disabled:opacity-50"
          >
            <span>{savingTelegram ? "Kaydediliyor..." : "Yapılandırmayı Kaydet"}</span>
          </button>

          {telegramStatus?.connected && (
            <button
              type="button"
              onClick={handleTestTelegram}
              disabled={testingTelegram}
              className="lux-press px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold disabled:opacity-50"
            >
              <span>{testingTelegram ? "Gönderiliyor..." : "Test Bildirimi Gönder"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Email & OAuth Accounts */}
      <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
        <div className="flex items-center justify-between pb-6 border-b border-white/15">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-white" />
              <h2 className="text-xl font-bold font-mono text-white tracking-wide">
                GELEN E-POSTA &amp; OAUTH İŞ ALARMLARI
              </h2>
            </div>
            <p className="text-xs text-white/50 font-mono mt-1">
              LinkedIn iş uyarılarını ve kariyer bültenlerini otomatik ayrıştıran güvenli OAuth bağlantıları.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Gmail */}
          <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/10 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white uppercase">Google / Gmail</span>
              <span className="text-[10px] text-white/50">Resmi Google OAuth</span>
            </div>
            <p className="text-white/60 text-[11px] font-sans">
              Google Workspace veya kişisel Gmail hesabınızdaki LinkedIn iş bildirimlerini tarar.
            </p>
            <div className="pt-2">
              <a
                href="/api/v1/oauth/google/start"
                className="silver-btn lux-press inline-block px-5 py-2.5 rounded-xl text-xs uppercase tracking-wider text-white"
              >
                Gmail Hesabını Yetkilendir
              </a>
            </div>
          </div>

          {/* Microsoft Outlook */}
          <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/10 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white uppercase">Microsoft Outlook</span>
              <span className="text-[10px] text-white/50">Microsoft Graph OAuth</span>
            </div>
            <p className="text-white/60 text-[11px] font-sans">
              Outlook / Hotmail posta kutusundaki kariyer uyarılarını güvenli Graph Delta ile çeker.
            </p>
            <div className="pt-2">
              <a
                href="/api/v1/oauth/microsoft/start"
                className="silver-btn lux-press inline-block px-5 py-2.5 rounded-xl text-xs uppercase tracking-wider text-white"
              >
                Outlook Hesabını Yetkilendir
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
