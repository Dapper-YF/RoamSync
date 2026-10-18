import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type {
  ExplorePlace,
  ExploreResults,
  ExplorePoint,
  ExploreRoute,
} from "../domain/explore";
export interface RouteState {
  origin?: ExplorePoint;
  originName: string;
  query: string;
  mode: "walk" | "driving";
  result?: ExploreRoute;
}
export interface Scene {
  input: string;
  region: string;
  city: string;
  query: string;
  category: "all" | "sight" | "food" | "hotel";
  results?: ExploreResults;
  scroll: number;
  view: "list" | "map";
  selected?: string;
  routes: Record<string, RouteState>;
  maps: Partial<Record<string, { center: ExplorePoint; zoom: number }>>;
  returnTo: string;
}
const empty: Scene = {
  input: "",
  region: "",
  city: "",
  query: "",
  category: "all",
  scroll: 0,
  view: "list",
  routes: {},
  maps: {},
  returnTo: "/",
};
function restore(): Scene {
  try {
    const value = JSON.parse(
      sessionStorage.getItem("roamsync.discovery.v1") || "null",
    );
    return value ? { ...empty, ...value } : empty;
  } catch {
    return empty;
  }
}
const Context = createContext<{
  scene: Scene;
  update: (patch: Partial<Scene>) => void;
  remember: (place: ExplorePlace) => void;
  places: Record<string, ExplorePlace>;
} | null>(null);
export function DiscoveryState({ children }: { children: ReactNode }) {
  const [scene, setScene] = useState(restore);
  const [places, setPlaces] = useState<Record<string, ExplorePlace>>({});
  useEffect(() => {
    try {
      sessionStorage.setItem("roamsync.discovery.v1", JSON.stringify(scene));
    } catch {
      /* Browsing remains available when storage is full. */
    }
  }, [scene]);
  return (
    <Context.Provider
      value={{
        scene,
        update: (patch) => setScene((s) => ({ ...s, ...patch })),
        places,
        remember: (place) => setPlaces((p) => ({ ...p, [place.id]: place })),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useScene() {
  const state = useContext(Context);
  if (!state) throw Error("DiscoveryState required");
  return state;
}
