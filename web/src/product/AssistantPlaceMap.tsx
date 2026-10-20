import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { AssistantSession } from "../domain/types";
import { ExploreMap } from "./ExploreMap";

type Cards = NonNullable<AssistantSession["messages"][number]["place_cards"]>;

export function AssistantPlaceMap({ cards }: { cards: Cards }) {
  const host = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!host.current) return;
    if (typeof IntersectionObserver === "undefined") { setVisible(true); return; }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "120px" });
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  const places = cards.filter(c => c.reason_kind === "retrieved_reference" && /^[0-9a-f-]{36}$/i.test(c.place.place_id)).map(c => c.place).slice(0, 3);
  const mapped = places.filter(p => p.coordinate_system === "gcj02" && typeof p.longitude === "number" && Number.isFinite(p.longitude) && Math.abs(p.longitude) <= 180 && typeof p.latitude === "number" && Number.isFinite(p.latitude) && Math.abs(p.latitude) <= 90);
  const points = mapped.map(p => ({ id: p.place_id, label: p.name, point: { longitude: p.longitude!, latitude: p.latitude!, coordinate_system: "gcj02" as const } }));
  if (!places.length) return null;
  return <section ref={host} className="assistant-place-map" aria-label="回答中的地点">
    {points.length > 0 && <div className="assistant-place-map-canvas">
      {visible ? <ExploreMap center={points[0].point} points={points} ariaLabel="回答中的地点地图" /> : <div className="assistant-map-placeholder">地点地图</div>}
    </div>}
    <div className="assistant-place-map-links">{places.map((p, i) => <Link key={p.place_id} state={{ from: "/assistant" }} to={`/places/${p.place_id}`} aria-label={`查看${p.name}详情`}><span>{places.length > 1 ? `${i + 1}. ` : ""}{p.name}</span><span>查看详情 ↗</span></Link>)}</div>
  </section>;
}
