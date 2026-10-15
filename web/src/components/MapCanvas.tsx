import AMapLoader from "@amap/amap-jsapi-loader";
import { LocateFixed, Map, Route, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Activity, Coordinates, RouteLeg } from "../domain/types";

interface MapCanvasProps {
  activities: Activity[];
  center?: Coordinates;
  accommodation?: { name: string; coordinates: Coordinates };
  routeLegs: RouteLeg[];
  selectedActivityId: string | null;
  onSelectActivity: (activityId: string) => void;
}

type MapStatus = "loading" | "ready" | "missing-config" | "error";

interface AMapOverlay {
  setMap?: (map: null) => void;
}

interface AMapMarker extends AMapOverlay {
  on: (event: "click", handler: () => void) => void;
}

interface AMapInstance {
  addControl: (control: unknown) => void;
  add: (overlays: AMapOverlay[]) => void;
  setFitView: (overlays: AMapOverlay[], immediately: boolean, padding: number[], maxZoom: number) => void;
  panTo: (coordinates: Activity["coordinates"], duration: number) => void;
  destroy: () => void;
}

interface AMapNamespace {
  Map: new (container: HTMLDivElement, options: Record<string, unknown>) => AMapInstance;
  Scale: new (options: Record<string, unknown>) => unknown;
  ToolBar: new (options: Record<string, unknown>) => unknown;
  Marker: new (options: Record<string, unknown>) => AMapMarker;
  Polyline: new (options: Record<string, unknown>) => AMapOverlay;
}

export function MapCanvas({ activities, center, accommodation, routeLegs, selectedActivityId, onSelectActivity }: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const amapRef = useRef<AMapNamespace | null>(null);
  const overlaysRef = useRef<AMapOverlay[]>([]);
  const [status, setStatus] = useState<MapStatus>("loading");
  const key = import.meta.env.VITE_AMAP_WEB_KEY?.trim();
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE?.trim();

  useEffect(() => {
    if (!key || !securityCode) {
      setStatus("missing-config");
      return;
    }
    if (!containerRef.current) return;

    let cancelled = false;
    window._AMapSecurityConfig = { securityJsCode: securityCode };
    setStatus("loading");
    AMapLoader.load({ key, version: "2.0", plugins: ["AMap.Scale", "AMap.ToolBar"] })
      .then((loadedAMap) => {
        if (cancelled || !containerRef.current) return;
        const AMap = loadedAMap as unknown as AMapNamespace;
        amapRef.current = AMap;
        mapRef.current = new AMap.Map(containerRef.current, {
          viewMode: "2D",
          zoom: 13,
          center: center ?? [116.397428, 39.90923],
          mapStyle: "amap://styles/whitesmoke",
        });
        mapRef.current.addControl(new AMap.Scale({ position: "RB" }));
        mapRef.current.addControl(new AMap.ToolBar({ position: "RB", offset: [18, 72] }));
        setStatus("ready");
      })
      .catch(() => !cancelled && setStatus("error"));

    return () => {
      cancelled = true;
      overlaysRef.current.forEach((overlay) => overlay.setMap?.(null));
      overlaysRef.current = [];
      mapRef.current?.destroy();
      mapRef.current = null;
      amapRef.current = null;
    };
  }, [center, key, securityCode]);

  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !amapRef.current) return;
    const AMap = amapRef.current;
    overlaysRef.current.forEach((overlay) => overlay.setMap?.(null));
    const markers = activities.map((activity, index) => {
      const selected = activity.id === selectedActivityId;
      const marker = new AMap.Marker({
        position: activity.coordinates,
        anchor: "center",
        zIndex: selected ? 150 : 100,
        content: `<button class="map-marker${selected ? " is-selected" : ""}" aria-label="${activity.name}">${index + 1}</button>`,
      });
      marker.on("click", () => onSelectActivity(activity.id));
      return marker;
    });
    const accommodationMarker = accommodation ? new AMap.Marker({
      position: accommodation.coordinates,
      anchor: "center",
      zIndex: 90,
      content: `<div class="map-marker accommodation-marker" aria-label="住宿：${accommodation.name}">住</div>`,
    }) : null;
    const alternativePolylines = routeLegs.flatMap((leg) =>
      (leg.alternatives ?? []).map((alternative) => new AMap.Polyline({
        path: alternative.path,
        strokeColor: "#789d99",
        strokeWeight: 3,
        strokeOpacity: 0.34,
        strokeStyle: "dashed",
        lineJoin: "round",
        zIndex: 40,
      })),
    );
    const routePolylines = routeLegs
      .filter((leg) => (leg.path?.length ?? 0) > 1)
      .map((leg) => new AMap.Polyline({
            path: leg.path,
            strokeColor: "#1b8f83",
            strokeWeight: 5,
            strokeOpacity: 0.82,
            strokeStyle: "solid",
            lineJoin: "round",
            showDir: true,
            zIndex: 50,
          }));
    overlaysRef.current = [...alternativePolylines, ...routePolylines, ...markers, ...(accommodationMarker ? [accommodationMarker] : [])];
    mapRef.current.add(overlaysRef.current);
    if (activities.length > 0) mapRef.current.setFitView(overlaysRef.current, false, [92, 92, 92, 430], 15);
  }, [accommodation, activities, onSelectActivity, routeLegs, selectedActivityId, status]);

  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !selectedActivityId) return;
    const selected = activities.find((activity) => activity.id === selectedActivityId);
    if (selected) mapRef.current.panTo(selected.coordinates, 280);
  }, [activities, selectedActivityId, status]);

  return (
    <section className="map-stage" aria-label="旅行地图">
      <div ref={containerRef} className="map-container" data-testid="map-container" />
      {status !== "ready" && <MapFallback status={status} activities={activities} />}
      <div className="map-mode-pill"><Map size={16} /> 路线视图</div>
      <div className="map-legend glass-panel">
        <span><i className="legend-dot planned" />计划节点</span>
        {accommodation && <span><i className="legend-dot accommodation" />住宿</span>}
        <span><i className="legend-line" />高德最短路线</span>
        {routeLegs.some((leg) => (leg.alternatives?.length ?? 0) > 0) && <span><i className="legend-line alternative" />备选路线</span>}
      </div>
      <button className="map-locate glass-button" type="button" aria-label="定位到行程">
        <LocateFixed size={18} />
      </button>
    </section>
  );
}

function MapFallback({ status, activities }: { status: MapStatus; activities: Activity[] }) {
  const isMissing = status === "missing-config";
  return (
    <div className="map-fallback" data-testid="map-fallback">
      <div className="fallback-road road-a" />
      <div className="fallback-road road-b" />
      <div className="fallback-water" />
      {activities.map((activity, index) => (
        <span key={activity.id} className={`fallback-pin pin-${(index % 4) + 1}`}>{index + 1}</span>
      ))}
      <div className="map-config-card glass-panel">
        {status === "loading" ? <span className="spinner" /> : isMissing ? <Route size={22} /> : <TriangleAlert size={22} />}
        <div>
          <strong>{status === "loading" ? "正在载入高德地图" : isMissing ? "高德底图尚未配置" : "地图暂时无法加载"}</strong>
          <p>{isMissing ? "在 web/.env.local 中设置 Web Key 与安全密钥；当前展示视觉回退层。" : "请检查网络、Key 绑定域名与安全密钥。"}</p>
        </div>
      </div>
    </div>
  );
}
