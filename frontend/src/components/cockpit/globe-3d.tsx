"use client";

import { useEffect, useRef } from "react";
import type { CityHub } from "./types";

interface Globe3DProps {
  activeCityKey: string;
  onSelectCity: (cityKey: string) => void;
  textureMode: "topo" | "blue-marble" | "carbon-matrix";
  isAutoRotating: boolean;
  cities: Record<string, CityHub>;
}

// Singleton script loader for Globe.gl
let globeScriptPromise: Promise<void> | null = null;

function loadGlobeLibrary(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if ((window as any).Globe) return Promise.resolve();
  if (!globeScriptPromise) {
    globeScriptPromise = new Promise<void>((resolve, reject) => {
      const existing = document.querySelector('script[src="/assets/globe/globe.gl.min.js"]');
      if (existing) {
        existing.addEventListener("load", () => resolve());
        existing.addEventListener("error", (e) => reject(e));
        return;
      }
      const script = document.createElement("script");
      script.src = "/assets/globe/globe.gl.min.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = (e) => reject(e);
      document.head.appendChild(script);
    });
  }
  return globeScriptPromise;
}

// Cached Procedural Carbon texture generator
let cachedCarbonTextureUrl: string | null = null;

function getProceduralCarbonTexture(): string {
  if (cachedCarbonTextureUrl) return cachedCarbonTextureUrl;
  if (typeof document === "undefined") return "";

  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";

  ctx.fillStyle = "#040406";
  ctx.fillRect(0, 0, 1024, 512);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;

  for (let lat = 0; lat <= 512; lat += 32) {
    ctx.beginPath();
    ctx.moveTo(0, lat);
    ctx.lineTo(1024, lat);
    ctx.stroke();
  }

  for (let lon = 0; lon <= 1024; lon += 32) {
    ctx.beginPath();
    ctx.moveTo(lon, 0);
    ctx.lineTo(lon, 512);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255, 255, 255, 0.16)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, 256);
  ctx.lineTo(1024, 256);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(512, 0);
  ctx.lineTo(512, 512);
  ctx.stroke();

  cachedCarbonTextureUrl = canvas.toDataURL();
  return cachedCarbonTextureUrl;
}

export function Globe3D({
  activeCityKey,
  onSelectCity,
  textureMode,
  isAutoRotating,
  cities,
}: Globe3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const globeInstanceRef = useRef<any>(null);

  const getArcsData = () => {
    const istanbul = cities.istanbul;
    if (!istanbul) return [];
    const arcs: any[] = [];

    Object.entries(cities).forEach(([key, city]) => {
      if (key === "istanbul") return;
      const isActive = key === activeCityKey;
      arcs.push({
        startLat: istanbul.lat,
        startLng: istanbul.lng,
        endLat: city.lat,
        endLng: city.lng,
        color: isActive
          ? ["rgba(255, 255, 255, 0.2)", "#ffffff", "rgba(255, 255, 255, 0.2)"]
          : [
              "rgba(255, 255, 255, 0.05)",
              "rgba(255, 255, 255, 0.5)",
              "rgba(255, 255, 255, 0.05)",
            ],
        stroke: isActive ? 1.6 : 0.8,
        altitude: isActive ? 0.35 : 0.25,
        speed: isActive ? 2000 : 3800,
      });
    });

    return arcs;
  };

  const getRingsData = () => {
    const rings: any[] = [];
    Object.entries(cities).forEach(([key, city]) => {
      const isActive = key === activeCityKey;
      rings.push({
        lat: city.lat,
        lng: city.lng,
        maxR: isActive ? 6 : 3,
        propagationSpeed: isActive ? 2.5 : 1,
        repeatPeriod: isActive ? 1200 : 2500,
        color: () =>
          isActive
            ? (t: number) => `rgba(255, 255, 255, ${1 - t})`
            : (t: number) => `rgba(255, 255, 255, ${0.4 * (1 - t)})`,
      });
    });
    return rings;
  };

  const getMarkerNodesData = () => {
    return Object.entries(cities).map(([key, city]) => ({
      key,
      name: city.name.split(",")[0],
      count: city.count,
      lat: city.lat,
      lng: city.lng,
      isActive: key === activeCityKey,
    }));
  };

  // Initialize globe once with singleton loader and full resource cleanup
  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    let isCancelled = false;
    let resizeObserver: ResizeObserver | null = null;
    let handleResizeFn: (() => void) | null = null;

    const loadAndInit = async () => {
      try {
        await loadGlobeLibrary();
      } catch (err) {
        console.warn("Globe library load failed:", err);
        return;
      }

      if (isCancelled || !containerRef.current) return;
      const GlobeClass = (window as any).Globe;
      if (!GlobeClass) return;

      const rect = container.getBoundingClientRect();
      const parentCard = container.closest(".carbon-card");
      const measuredW =
        rect.width ||
        (parentCard ? parentCard.clientWidth - 32 : 0) ||
        container.clientWidth ||
        window.innerWidth - 32;
      const initW = Math.max(
        280,
        Math.min(window.innerWidth - 24, Math.round(measuredW))
      );
      const measuredH =
        rect.height || container.clientHeight || (window.innerWidth < 640 ? 360 : 500);
      const initH = Math.round(measuredH);

      const topoTextureUrl = "/assets/globe/earth-topo-bathy.jpg";

      try {
        const globe = GlobeClass()(container)
          .width(initW)
          .height(initH)
          .globeImageUrl(topoTextureUrl)
          .bumpImageUrl("")
          .backgroundColor("rgba(0, 0, 0, 0)")
          .showAtmosphere(true)
          .atmosphereColor("#ffffff")
          .atmosphereAltitude(0.18)
          .arcsData(getArcsData())
          .arcStartLat((d: any) => d.startLat)
          .arcStartLng((d: any) => d.startLng)
          .arcEndLat((d: any) => d.endLat)
          .arcEndLng((d: any) => d.endLng)
          .arcColor((d: any) => d.color)
          .arcStroke((d: any) => d.stroke)
          .arcAltitude((d: any) => d.altitude)
          .arcDashLength(0.6)
          .arcDashGap(2)
          .arcDashAnimateTime((d: any) => d.speed)
          .ringsData(getRingsData())
          .ringColor((d: any) => d.color())
          .ringMaxRadius((d: any) => d.maxR)
          .ringPropagationSpeed((d: any) => d.propagationSpeed)
          .ringRepeatPeriod((d: any) => d.repeatPeriod)
          .htmlElementsData(getMarkerNodesData())
          .htmlLat((d: any) => d.lat)
          .htmlLng((d: any) => d.lng)
          .htmlAltitude(0.02)
          .htmlElement((d: any) => {
            const el = document.createElement("div");
            el.className = `globe-marker-wrap ${
              d.isActive ? "globe-marker-active" : ""
            }`;
            el.setAttribute("data-city-node", d.key);

            el.innerHTML = `
              <div class="flex items-center gap-1.5 font-mono">
                <div class="relative w-3.5 h-3.5 flex items-center justify-center">
                  <span class="absolute inset-0 rounded-full bg-white opacity-40 animate-ping"></span>
                  <span class="marker-core w-2 h-2 rounded-full bg-white border border-black shadow-[0_0_8px_#ffffff]"></span>
                </div>
                <div class="marker-tag px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wider uppercase border border-white/20 bg-black/85 text-white/90 shadow-lg whitespace-nowrap transition-all">
                  ${d.name} <span class="text-white/50">(${d.count})</span>
                </div>
              </div>
            `;

            el.addEventListener("click", (e) => {
              e.stopPropagation();
              onSelectCity(d.key);
            });

            return el;
          });

        const controls = globe.controls();
        if (controls) {
          controls.autoRotate = isAutoRotating;
          controls.autoRotateSpeed = 0.45;
          controls.enablePan = false;
          controls.minDistance = 140;
          controls.maxDistance = 500;
        }

        handleResizeFn = () => {
          if (!globe || !container) return;
          const r = container.getBoundingClientRect();
          const pCard = container.closest(".carbon-card");
          const mW =
            r.width ||
            (pCard ? pCard.clientWidth - 32 : 0) ||
            container.clientWidth ||
            window.innerWidth - 32;
          const w = Math.max(
            280,
            Math.min(window.innerWidth - 24, Math.round(mW))
          );
          const h = Math.round(
            r.height ||
              container.clientHeight ||
              (window.innerWidth < 640 ? 360 : 500)
          );
          if (w > 0 && h > 0) {
            globe.width(w);
            globe.height(h);
          }
        };

        if (window.ResizeObserver) {
          resizeObserver = new ResizeObserver(handleResizeFn);
          resizeObserver.observe(container);
        }
        window.addEventListener("resize", handleResizeFn);

        const targetCity = cities[activeCityKey] || cities.istanbul;
        if (targetCity) {
          globe.pointOfView(
            { lat: targetCity.lat, lng: targetCity.lng, altitude: 2.1 },
            1000
          );
        }

        globeInstanceRef.current = globe;
      } catch (e) {
        console.error("Globe init error:", e);
      }
    };

    loadAndInit();

    return () => {
      isCancelled = true;
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      if (handleResizeFn) {
        window.removeEventListener("resize", handleResizeFn);
      }
      if (globeInstanceRef.current) {
        try {
          globeInstanceRef.current._destructor?.();
        } catch {}
        globeInstanceRef.current = null;
      }
    };
  }, []);

  // Update Point of View when activeCityKey changes
  useEffect(() => {
    const globe = globeInstanceRef.current;
    if (!globe) return;
    const city = cities[activeCityKey];
    if (city) {
      globe.pointOfView({ lat: city.lat, lng: city.lng, altitude: 1.45 }, 1200);
      globe.arcsData(getArcsData());
      globe.ringsData(getRingsData());
      globe.htmlElementsData(getMarkerNodesData());
    }
  }, [activeCityKey, cities]);

  // Update autoRotate
  useEffect(() => {
    const globe = globeInstanceRef.current;
    if (globe && globe.controls()) {
      globe.controls().autoRotate = isAutoRotating;
    }
  }, [isAutoRotating]);

  // Update textureMode
  useEffect(() => {
    const globe = globeInstanceRef.current;
    if (!globe) return;
    if (textureMode === "topo") {
      globe.globeImageUrl("/assets/globe/earth-topo-bathy.jpg");
      globe.atmosphereColor("#ffffff");
      globe.atmosphereAltitude(0.18);
    } else if (textureMode === "blue-marble") {
      globe.globeImageUrl("/assets/globe/earth-blue-marble.jpg");
      globe.atmosphereColor("#60a5fa");
      globe.atmosphereAltitude(0.14);
    } else if (textureMode === "carbon-matrix") {
      globe.globeImageUrl(getProceduralCarbonTexture());
      globe.atmosphereColor("#a1a1aa");
      globe.atmosphereAltitude(0.10);
    }
  }, [textureMode]);

  return (
    <div
      ref={containerRef}
      id="globeContainer"
      className="absolute inset-0 w-full h-full overflow-hidden flex items-center justify-center"
    />
  );
}
