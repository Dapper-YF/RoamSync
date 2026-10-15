import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { DayPlan, PlaceCandidate, Trip, TripPlanningRepository } from "../domain/types";
import { publishMonitor } from "../utils/agentMonitorChannel";
import { AiPlannerPanel } from "./AiPlannerPanel";
import "./AgentMonitor.css";

// Reuses the ordinary conversation component and repository without another Agent.
export function AgentConversation({ repository }: { repository: TripPlanningRepository }) {
  const { tripId = "" } = useParams();
  const navigate = useNavigate();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [days, setDays] = useState<DayPlan[]>([]);
  const [candidates, setCandidates] = useState<PlaceCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [readyTrip, setReadyTrip] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [nextDays, nextCandidates] = await Promise.all([repository.getDays(tripId), repository.getCandidates(tripId)]);
    setDays(nextDays); setCandidates(nextCandidates);
  }, [repository, tripId]);
  useEffect(() => {
    let alive = true;
    if (!tripId) {
      setReadyTrip(""); setDays([]); setCandidates([]); setError(null);
      publishMonitor({ type: "trip_selected", requestId: "workspace" });
      return () => { alive = false; };
    }
    Promise.all([repository.listTrips(), repository.getDays(tripId), repository.getCandidates(tripId)])
      .then(([nextTrips, nextDays, nextCandidates]) => { if (alive) { setTrips(nextTrips); setDays(nextDays); setCandidates(nextCandidates); setError(null); setReadyTrip(tripId); } })
      .catch((cause) => { if (alive) setError(cause instanceof Error ? cause.message : "旅行读取失败"); });
    publishMonitor({ type: "trip_selected", requestId: "workspace", tripId });
    return () => { alive = false; };
  }, [repository, tripId, navigate]);
  return <main className="monitor-conversation"><header>{tripId ? <label>当前旅行 <select aria-label="当前旅行" value={tripId} onChange={(event) => navigate(`/dev/agent-conversation/${event.target.value}`)}>{!trips.some((trip) => trip.id === tripId) && <option value={tripId}>正在读取旅行…</option>}{trips.map((trip) => <option value={trip.id} key={trip.id}>{trip.title}</option>)}</select></label> : <span>创建旅行前 · 旅程总管</span>}<Link to={tripId ? `/trips/${tripId}?ai=1` : "/trips"} target="_blank">打开完整工作台 ↗</Link></header>{error ? <p role="alert">{error}</p> : readyTrip === tripId ? <AiPlannerPanel key={tripId || "pre-trip"} open tripId={tripId || undefined} days={days} candidates={candidates} repository={repository} onClose={() => navigate(tripId ? `/trips/${tripId}` : "/trips")} onAccepted={load} onTripChanged={(id) => navigate(`/dev/agent-conversation/${id}`)} /> : <p>正在读取旅行…</p>}</main>;
}
