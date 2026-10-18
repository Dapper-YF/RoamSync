import AMapLoader from "@amap/amap-jsapi-loader";
import { MapPin, MapPinned, MousePointer2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ExplorePoint } from "../domain/explore";

interface ExploreMapPoint {
  point: ExplorePoint;
  label: string;
  id?: string;
}
interface ExploreMapProps {
  center: ExplorePoint;
  points?: ExploreMapPoint[];
  path?: number[][];
  pickMode?: boolean;
  onPickPoint?: (point: ExplorePoint) => void;
  ariaLabel?: string;
  pickLabel?: string;
  selectedId?: string;
  onSelect?: (id: string) => void;
  savedView?: { center: ExplorePoint; zoom: number };
  onViewChange?: (view: { center: ExplorePoint; zoom: number }) => void;
}
type MapStatus = "loading" | "ready" | "missing-config" | "error";
interface AMapOverlay {
  setMap?: (map: null) => void;
}
interface AMapInstance {
  addControl: (control: unknown) => void;
  add: (overlays: AMapOverlay[]) => void;
  setFitView: (
    overlays: AMapOverlay[],
    immediately: boolean,
    padding: number[],
    maxZoom: number,
  ) => void;
  on: (event: string, handler: (event: AMapClickEvent) => void) => void;
  getCenter: () => { getLng: () => number; getLat: () => number };
  getZoom: () => number;
  destroy: () => void;
}
interface AMapClickEvent {
  lnglat: { getLng: () => number; getLat: () => number };
}
type AMapMarker = AMapOverlay & {
  on: (event: string, handler: () => void) => void;
};
interface AMapNamespace {
  Map: new (
    container: HTMLDivElement,
    options: Record<string, unknown>,
  ) => AMapInstance;
  Scale: new (options: Record<string, unknown>) => unknown;
  ToolBar: new (options: Record<string, unknown>) => unknown;
  Marker: new (options: Record<string, unknown>) => AMapMarker;
  Polyline: new (options: Record<string, unknown>) => AMapOverlay;
}

export function ExploreMap({
  center,
  points = [],
  path = [],
  pickMode = false,
  onPickPoint,
  ariaLabel = "地点地图",
  pickLabel = "起点",
  selectedId,
  onSelect,
  savedView,
  onViewChange,
}: ExploreMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const amapRef = useRef<AMapNamespace | null>(null);
  const overlaysRef = useRef<AMapOverlay[]>([]);
  const pickHandlerRef = useRef(onPickPoint);
  const pickModeRef = useRef(pickMode);
  const [status, setStatus] = useState<MapStatus>("loading");
  const viewRef = useRef(savedView);
  const changeRef = useRef(onViewChange);
  const selectRef = useRef(onSelect);
  const fitted = useRef(false);
  const previousPath = useRef(path);
  useEffect(() => {
    changeRef.current = onViewChange;
    selectRef.current = onSelect;
  }, [onViewChange, onSelect]);
  const key = import.meta.env.VITE_AMAP_WEB_KEY?.trim();
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE?.trim();

  useEffect(() => {
    pickHandlerRef.current = onPickPoint;
    pickModeRef.current = pickMode;
  }, [onPickPoint, pickMode]);

  useEffect(() => {
    if (!key || !securityCode) {
      setStatus("missing-config");
      return;
    }
    if (!containerRef.current) return;
    let cancelled = false;
    window._AMapSecurityConfig = { securityJsCode: securityCode };
    setStatus("loading");
    AMapLoader.load({
      key,
      version: "2.0",
      plugins: ["AMap.Scale", "AMap.ToolBar"],
    })
      .then((loaded) => {
        if (cancelled || !containerRef.current) return;
        const AMap = loaded as unknown as AMapNamespace;
        amapRef.current = AMap;
        const map = new AMap.Map(containerRef.current, {
          viewMode: "2D",
          zoom: viewRef.current?.zoom ?? 13,
          center: [
            viewRef.current?.center.longitude ?? center.longitude,
            viewRef.current?.center.latitude ?? center.latitude,
          ],
          mapStyle: "amap://styles/whitesmoke",
        });
        map.addControl(new AMap.Scale({ position: "RB" }));
        map.addControl(new AMap.ToolBar({ position: "RB", offset: [18, 72] }));
        map.on("click", (event) => {
          if (!pickModeRef.current) return;
          const longitude = event.lnglat.getLng();
          const latitude = event.lnglat.getLat();
          if (Number.isFinite(longitude) && Number.isFinite(latitude))
            pickHandlerRef.current?.({
              longitude,
              latitude,
              coordinate_system: "gcj02",
            });
        });
        mapRef.current = map;
        const capture = () => {
          const c = map.getCenter();
          changeRef.current?.({
            center: {
              longitude: c.getLng(),
              latitude: c.getLat(),
              coordinate_system: "gcj02",
            },
            zoom: map.getZoom(),
          });
        };
        map.on("moveend", capture);
        map.on("zoomend", capture);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
      overlaysRef.current.forEach((overlay) => overlay.setMap?.(null));
      overlaysRef.current = [];
      mapRef.current?.destroy();
      mapRef.current = null;
      amapRef.current = null;
    };
  }, [key, securityCode]);

  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !amapRef.current) return;
    const AMap = amapRef.current;
    overlaysRef.current.forEach((overlay) => overlay.setMap?.(null));
    const markers = points.map(({ point, id }, index) => {
      const marker = new AMap.Marker({
        position: [point.longitude, point.latitude],
        anchor: "center",
        zIndex: index === 0 && points.length > 1 ? 140 : 100,
        content: `<span class="rxp-map-marker" style="${id && selectedId === id ? "background:#dd815d" : ""}">${id ? index + 1 : points.length > 1 ? (index === 0 ? "起" : "终") : "•"}</span>`,
      });
      if (id) marker.on("click", () => selectRef.current?.(id));
      return marker;
    });
    const routeLine =
      path.length > 1
        ? [
            new AMap.Polyline({
              path,
              strokeColor: "#1e897d",
              strokeWeight: 5,
              strokeOpacity: 0.86,
              lineJoin: "round",
              showDir: true,
              zIndex: 60,
            }),
          ]
        : [];
    overlaysRef.current = [...routeLine, ...markers];
    if (overlaysRef.current.length) {
      mapRef.current.add(overlaysRef.current);
      const pathChanged =
        path.length > 1 &&
        JSON.stringify(previousPath.current) !== JSON.stringify(path);
      if ((!fitted.current && !viewRef.current) || pathChanged)
        mapRef.current.setFitView(
          overlaysRef.current,
          false,
          [72, 72, 72, 72],
          15,
        );
      fitted.current = true;
      previousPath.current = path;
    }
  }, [path, points, status, selectedId]);

  return (
    <section
      className={`rxp-amap-stage${pickMode ? " is-pickable" : ""}`}
      aria-label={ariaLabel}
    >
      <div
        ref={containerRef}
        className="rxp-amap-canvas"
        data-testid="explore-map-canvas"
      />
      {status !== "ready" && (
        <div className="rxp-amap-fallback" role="status">
          <span className="rxp-amap-fallback-icon">
            {status === "error" ? (
              <TriangleAlert size={23} />
            ) : pickMode ? (
              <MousePointer2 size={23} />
            ) : (
              <MapPinned size={23} />
            )}
          </span>
          <strong>
            {status === "loading"
              ? "正在连接高德地图"
              : status === "missing-config"
                ? "地图暂时不可用"
                : "暂时无法连接地图"}
          </strong>
          <p>
            {status === "missing-config"
              ? "你可以继续查看地点信息，或打开高德原始信息。"
              : status === "error"
                ? "请稍后重试，或打开高德原始信息。"
                : pickMode
                  ? `地图准备好后，可点击任意位置设置${pickLabel}。`
                  : "地点坐标与外部地图入口仍可使用。"}
          </p>
          {pickMode && (
            <small>
              <MapPin size={12} />
              也可以搜索地点设置{pickLabel}
            </small>
          )}
        </div>
      )}
      {status === "ready" && pickMode && (
        <div className="rxp-map-pick-hint">
          <MousePointer2 size={14} />
          点击地图选{pickLabel}
        </div>
      )}
    </section>
  );
}
