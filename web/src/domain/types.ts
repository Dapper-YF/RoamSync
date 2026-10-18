export type Fen = number;
export type Coordinates = readonly [longitude: number, latitude: number];
export type ActivityStatus = "planned" | "active" | "completed" | "skipped";
export type PlaceCategory = "sight" | "food" | "culture" | "nature" | "shopping";
export type TripPace = "relaxed" | "balanced" | "intensive";
export type InterestCategory = "history" | "culture" | "nature" | "food" | "photography" | "shopping" | "family" | "nightlife";
export type PreferenceTransportMode = "walk" | "transit" | "driving";

export interface SourceRecord {
  id: string;
  title: string;
  url: string;
  provider: string;
  queriedAt: string;
  confidence: "high" | "medium" | "low";
}

export interface Trip {
  id: string;
  title: string;
  destination: string;
  startDate: string;
  endDate: string;
  totalBudgetFen: Fen | null;
  dailyBudgetFen: Fen | null;
  currency: "CNY";
  accommodation: string;
  destinationAdcode?: string;
  destinationCitycode?: string;
  center?: Coordinates;
  accommodationPoiId?: string;
  accommodationAddress?: string;
  accommodationDistrict?: string;
  accommodationCoordinates?: Coordinates;
  status?: "upcoming" | "active" | "completed" | "archived";
  updatedAt?: string;
  archivedAt?: string;
  version?: number;
}

export interface CitySuggestion {
  name: string;
  adcode: string;
  citycode: string;
  coordinates: Coordinates;
}

export interface TripCreateInput {
  title: string;
  destination: string;
  destinationAdcode: string;
  destinationCitycode: string;
  center: Coordinates;
  accommodation: string;
  accommodationPoiId?: string;
  accommodationAddress?: string;
  accommodationDistrict?: string;
  accommodationCoordinates?: Coordinates;
  startDate: string;
  endDate: string;
  totalBudgetFen: Fen | null;
  dailyBudgetFen: Fen | null;
}

export interface AccommodationPoi {
  poiId: string;
  name: string;
  address: string;
  district: string;
  coordinates: Coordinates;
  typeName: string;
  rating?: number;
}

export interface TripUpdateInput extends Partial<Omit<TripCreateInput, "center">> {
  center?: Coordinates;
  version: number;
  confirmDayRemoval?: boolean;
}

export interface TripPreferences {
  tripId: string;
  pace: TripPace;
  interestCategories: InterestCategory[];
  transportModes: PreferenceTransportMode[];
  dailyStartTime: string;
  dailyEndTime: string;
  mealPreferences: string;
  avoidCategories: string[];
  maxWalkingMinutes: number;
  freeTextRequirements: string;
  version: number;
  updatedAt: string;
}

export type TripPreferencesUpdateInput = Omit<TripPreferences, "tripId" | "updatedAt">;

export interface TripDeletionPreview {
  tripId: string;
  dayPlans: number;
  activities: number;
  candidates: number;
  expenses: number;
}

export interface PlaceCandidate {
  id: string;
  name: string;
  category: PlaceCategory;
  neighborhood: string;
  description: string;
  coordinates: Coordinates;
  suggestedDurationMinutes: number;
  estimatedCostFen: Fen;
  rating: number;
  tags: string[];
  source: SourceRecord;
}

export interface PlaceSearchResult {
  kind: "search";
  provider: "amap";
  providerPoiId: string;
  name: string;
  category: PlaceCategory;
  neighborhood: string;
  description: string;
  coordinates: Coordinates;
  suggestedDurationMinutes: number;
  estimatedCostFen: Fen;
  rating: number;
  tags: string[];
  sourceUrl: string;
}

export type PlaceOption = PlaceCandidate | PlaceSearchResult;

export type ActivityImportance = "low" | "normal" | "high" | "must_do";

export interface Activity {
  id: string;
  placeId: string;
  name: string;
  originalName: string;
  customName?: string;
  category: PlaceCategory;
  neighborhood: string;
  coordinates: Coordinates;
  scheduledTime: string;
  durationMinutes: number;
  importance: ActivityImportance;
  canSkip?: boolean;
  minimumDurationMinutes?: number | null;
  importanceSource?: string;
  canSkipSource?: string;
  minimumDurationSource?: string;
  estimatedCostFen: Fen;
  status: ActivityStatus;
  scheduleLocked: boolean;
  version: number;
  updatedAt: string;
  note?: string;
  source: SourceRecord;
}

export interface ActivityUpdateInput {
  version: number;
  customName?: string | null;
  scheduledTime?: string;
  durationMinutes?: number;
  importance?: ActivityImportance;
  canSkip?: boolean;
  minimumDurationMinutes?: number | null;
  estimatedCostFen?: Fen;
  status?: ActivityStatus;
  note?: string | null;
  scheduleLocked?: boolean;
}

export interface ActivityMoveInput {
  version: number;
  targetDayPlanId: string;
  targetPosition: number;
}

export interface ActivityMoveResult {
  activityId: string;
  sourceDay: DayPlan;
  targetDay: DayPlan;
}

export interface DayPlan {
  id: string;
  tripId: string;
  date: string;
  label: string;
  theme: string;
  activities: Activity[];
  routeMode?: RouteLeg["mode"];
  routeLegs?: RouteLeg[];
  conflicts?: ScheduleConflict[];
}

export interface RouteLeg {
  id?: string;
  fromActivityId: string;
  toActivityId: string;
  durationMinutes: number;
  distanceMeters: number;
  mode: "walk" | "transit" | "driving";
  provider?: string;
  isEstimated?: boolean;
  path?: Coordinates[];
  alternatives?: RouteAlternative[];
}

export interface RouteAlternative {
  distanceMeters: number;
  durationMinutes: number;
  path: Coordinates[];
}

export interface ScheduleConflict {
  activityId: string;
  code: "late_finish";
  message: string;
}

export interface BudgetSummary {
  plannedFen: Fen;
  remainingFen: Fen | null;
  ratio: number | null;
  status: "comfortable" | "watch" | "over" | "unconstrained";
}

export interface PlanningBudgetDay extends BudgetSummary {
  dayPlanId: string;
  date: string;
}

export interface PlanningBudget {
  tripId: string;
  totalPlannedFen: Fen;
  totalRemainingFen: Fen | null;
  days: PlanningBudgetDay[];
}

export interface ActualBudget {
  tripId: string;
  totalBudgetFen: Fen | null;
  totalSpentFen: Fen;
  totalRemainingFen: Fen | null;
  dailyBudgetFen: Fen | null;
  todaySpentFen: Fen;
  todayRemainingFen: Fen | null;
  localDate: string;
}

export interface PlanningContext {
  trip: Trip;
  preferences: TripPreferences;
  days: DayPlan[];
  candidates: PlaceCandidate[];
  actualBudget: ActualBudget;
  planningBudget: PlanningBudget;
  generatedAt: string;
  externalFacts: ExternalFacts;
}

export interface ExternalFacts {
  weather?: { status?: string; provider?: string; queriedAt?: string; temperatureC?: number; precipitationProbability?: number; weatherCode?: number; error?: string };
  search?: { status?: string; provider?: string; queriedAt?: string; query?: string; results?: Array<{ title?: string; url?: string; snippet?: string }>; error?: string };
}

export type PlanningRunStatus =
  | "queued" | "researching" | "awaiting_clarification" | "planning" | "validating"
  | "awaiting_confirmation" | "accepted" | "rejected" | "failed" | "cancelled" | "answered";

export interface PlanningRun {
  decisionMemory?: { count: number; feedback: Array<{ sourceRevisionId: string; reasonCode?: string; reasonText?: string }> };
  progress?: { stage: string; message: string; updated_at: string };
  heartbeatAt?: string;
  responseText?: string;
  id: string;
  tripId: string;
  runType: "initial_plan" | "replan";
  status: PlanningRunStatus;
  userRequest: string;
  modelProvider?: string;
  modelName?: string;
  tokenUsage: number;
  errorCode?: string;
  errorMessage?: string;
  errorDetails?: { validation_errors?: { code: string; message: string; details?: Record<string, unknown> }[]; map_error_code?: string };
  pendingInterrupt?: { kind?: string; questions?: string[]; revision_id?: string };
  createdAt?: string;
  completedAt?: string;
}

export type TripExecutionStatus = "not_started" | "in_progress" | "paused" | "completed";
export type ActivityExecutionStatus = "pending" | "arrived" | "in_progress" | "completed" | "skipped";
export type TripExecutionAction = "arrive" | "start_activity" | "complete" | "skip" | "pause" | "resume" | "finish";
export type DynamicReplanTrigger = "delay" | "weather_change" | "fatigue" | "budget_change" | "user_change";

export interface ActivityExecution {
  id?: string;
  activityId: string;
  dayPlanId: string;
  dayDate: string;
  name: string;
  scheduledTime: string;
  estimatedCostFen: Fen;
  status: ActivityExecutionStatus;
  actualArrivedAt?: string;
  actualStartedAt?: string;
  actualEndedAt?: string;
  delayMinutes: number;
}

export interface TravelEvent {
  id: string;
  eventType: string;
  activityId?: string;
  occurredAt: string;
  details: Record<string, unknown>;
}

export interface TripExecution {
  id?: string;
  tripId: string;
  status: TripExecutionStatus;
  currentDate: string;
  currentDayPlanId?: string;
  currentActivityId?: string;
  actualStartedAt?: string;
  actualEndedAt?: string;
  pausedAt?: string;
  scheduleDelayMinutes: number;
  remainingActivityCount: number;
  remainingEstimatedCostFen: Fen;
  activities: ActivityExecution[];
  events: TravelEvent[];
}

/** Mirrors the execution-progress BFF; it does not infer domain risk. */
export type ExecutionRiskState = "normal" | "eta_delayed" | "disruption" | "unknown";
export type NavigationSessionStatus = "created" | "active" | "rerouting" | "arrived" | "completed" | "failed" | "cancelled" | "superseded";
export interface NavigationSessionSummary { id: string; itineraryVersion: number; fromActivityId: string; toActivityId: string; plannedDepartureAt: string; plannedArrivalAt: string; currentEta?: string; remainingDistanceMeters?: number; status: NavigationSessionStatus; lastLocationAt?: string; updatedAt: string; }
export interface TripDisruptionSummary { id: string; eventType: "missed_time_window" | "itinerary_infeasible"; impactedIdentity: string; impactSnapshot: Record<string, unknown>; detectedAt: string; lastSeenAt: string; itineraryVersion: number; }
export interface RecoveryPlanningSummary { id: string; status: PlanningRunStatus; disruptionEventId: string; baseTripVersion: number; errorCode?: string; errorMessage?: string; }
export interface RecoveryChangeSummary { adjustedActivities: Array<{ activityId: string; name?: string; beforeStartTime: string; afterStartTime: string; beforeDurationMinutes?: number; afterDurationMinutes?: number; }>; }
export interface PendingRecoveryRevisionSummary { id: string; status: "pending"; reason: string; differenceSummary: Record<string, unknown>; proposedSnapshot: { explanation: string; activities: CandidatePlanActivity[] }; changeSummary: RecoveryChangeSummary; }
export interface ActivityExperienceProgress { activityExecutionId: string; activityId: string; plannedDurationMinutes: number; actualStartedAt?: string; actualEndedAt?: string; elapsedExperienceMinutes?: number; totalExtensionMinutes: number; projectedEndAt?: string; }
export interface RecoveryPlanning { source: "navigation_disruption" | "activity_experience"; status: "queued" | "planning" | "awaiting_confirmation" | "accepted" | "rejected" | "superseded" | "failed"; planningRunId: string; reasonSummary: string; triggerActivityId?: string; triggerActivityName?: string; timeShiftMinutes?: number; minimumDownstreamSlackMinutes?: number; firstImpactedActivityId?: string; pendingRevision: PendingRecoveryRevisionSummary | null; sourceDetail: Record<string, unknown>; }
export interface ExecutionProgress { tripId: string; itineraryVersion: number; execution: TripExecution; navigationSession: NavigationSessionSummary | null; currentActivityName: string | null; currentActivityExperience?: ActivityExperienceProgress | null; experienceImpact?: { impactState: "unavailable" | "none" | "absorbed" | "at_risk" | "infeasible"; minimumDownstreamSlackMinutes?: number; timeShiftMinutes?: number } | null; navigationTargetName: string | null; riskLevel: ExecutionRiskState; minimumDownstreamSlackMinutes: number | null; firstImpactedActivityId: string | null; activeDisruption: TripDisruptionSummary | null; activeRecoveryRun: RecoveryPlanningSummary | null; recoveryRevision: PendingRecoveryRevisionSummary | null; recoveryPlanning?: RecoveryPlanning | null; generatedAt: string; }

export interface CandidatePlanActivity {
  candidateId: string;
  dayDate: string;
  placeCandidateId: string;
  plannedStartTime: string;
  durationMinutes: number;
  estimatedCostFen: Fen;
  transportModeToHere: PreferenceTransportMode;
  reason: string;
  locked: boolean;
  replacesActivityId?: string;
  placeName?: string;
}

export type GoalStatus = "satisfied" | "unsatisfied" | "partially_satisfied" | "not_evaluable";
export interface PlanningGoals {
  targetDays: string[];
  hardGoals: { endBefore?: string | null; maxWalkingMinutes?: number | null };
  softGoals: { pace?: "relaxed" | "balanced" | "packed" | null; minimizeWalking: boolean; preserveExisting: boolean };
}
export interface GoalSatisfactionItem { goal: string; type: "hard" | "soft"; status: GoalStatus; evidence: Record<string, unknown>; }
export interface GoalSatisfaction { results: GoalSatisfactionItem[]; }

export interface PlanRevision {
  id: string;
  planningRunId: string;
  reason: string;
  activities: CandidatePlanActivity[];
  differenceSummary: Record<string, unknown>;
  validationResult: Record<string, unknown>;
  planningGoals?: PlanningGoals;
  goalSatisfaction?: GoalSatisfaction;
  sourceIds: string[];
  status: "pending" | "accepted" | "rejected" | "superseded";
  rejectionReasonCode?: "too_rushed" | "too_much_walking" | "activity_mix_not_preferred" | "schedule_too_late" | "too_expensive" | "other";
  rejectionReasonText?: string;
}

export interface TripPlanningRepository {
  getAssistantSession?(tripId?: string): Promise<AssistantSession>;
  resetAssistantSession?(sessionId: string): Promise<AssistantSession>;
  sendAssistantMessage?(sessionId: string, message: string, messageId: string, selectedDayId?: string, selectedActivityId?: string): Promise<AssistantSession>;
  streamAssistantMessage?(sessionId: string, message: string, messageId: string, onEvent: (event: AssistantStreamEvent) => void, selectedDayId?: string, selectedActivityId?: string): Promise<AssistantSession>;
  decideAssistantAction?(sessionId: string, actionId: string, accept: boolean): Promise<AssistantSession>;
  listTrips(): Promise<Trip[]>;
  createTrip(input: TripCreateInput): Promise<Trip>;
  searchCities(query: string): Promise<CitySuggestion[]>;
  searchAccommodationPois(query: string, city: string): Promise<AccommodationPoi[]>;
  updateTrip(tripId: string, input: TripUpdateInput): Promise<Trip>;
  getTripPreferences(tripId: string): Promise<TripPreferences>;
  updateTripPreferences(tripId: string, input: TripPreferencesUpdateInput): Promise<TripPreferences>;
  getPlanningContext(tripId: string): Promise<PlanningContext>;
  duplicateTrip(tripId: string): Promise<Trip>;
  archiveTrip(tripId: string): Promise<Trip>;
  getTripDeletionPreview(tripId: string): Promise<TripDeletionPreview>;
  deleteTrip(tripId: string): Promise<void>;
  getTrip(tripId: string): Promise<Trip>;
  getDays(tripId: string): Promise<DayPlan[]>;
  getCandidates(tripId: string): Promise<PlaceCandidate[]>;
  searchPlaces(tripId: string, query: string, category?: PlaceCategory): Promise<PlaceSearchResult[]>;
  getPlanningBudget(tripId: string): Promise<PlanningBudget>;
  addActivity(dayId: string, place: string | PlaceSearchResult): Promise<Activity>;
  updateActivity(activityId: string, input: ActivityUpdateInput): Promise<Activity>;
  moveActivity(activityId: string, input: ActivityMoveInput): Promise<ActivityMoveResult>;
  reorderActivities(dayId: string, activityIds: string[]): Promise<DayPlan>;
  recalculateRoute(dayId: string, mode: RouteLeg["mode"]): Promise<DayPlan>;
  removeActivity(activityId: string): Promise<void>;
  createPlanningRun(tripId: string, userRequest: string, options?: { runType?: PlanningRun["runType"]; selectedDayId?: string; selectedActivityId?: string }): Promise<PlanningRun>;
  listPlanningRuns(tripId: string): Promise<PlanningRun[]>;
  getPlanningRun(runId: string): Promise<PlanningRun>;
  answerPlanningRun(runId: string, answer: string): Promise<PlanningRun>;
  decidePlanningRun(runId: string, decision: "accept" | "reject"): Promise<{ run: PlanningRun; revision: PlanRevision }>;
  getPlanRevision(runId: string): Promise<PlanRevision>;
  acceptPlanRevision(revisionId: string): Promise<PlanRevision>;
  rejectPlanRevision(revisionId: string, feedback?: { reasonCode?: PlanRevision["rejectionReasonCode"]; reasonText?: string }): Promise<PlanRevision>;
  getTripExecution(tripId: string): Promise<TripExecution>;
  getExecutionProgress(tripId: string): Promise<ExecutionProgress>;
  startTripExecution(tripId: string, dayPlanId?: string): Promise<TripExecution>;
  applyTripExecutionAction(executionId: string, action: TripExecutionAction, activityId?: string): Promise<TripExecution>;
  extendStay(activityExecutionId: string, extensionMinutes: number, clientActionId: string): Promise<void>;
  leaveEarly(activityExecutionId: string, clientActionId: string): Promise<void>;
  requestDynamicReplan(tripId: string, trigger: DynamicReplanTrigger, details: string): Promise<PlanningRun>;
}

export type AssistantStreamEvent =
  | { type: "analysis_delta" | "answer_delta"; delta: string }
  | { type: "status"; message: string }
  | { type: "reset" }
  | { type: "done"; session: AssistantSession }
  | { type: "error"; message: string };

export interface AssistantSession {
  id: string;
  trip_id: string | null;
  latest_run_id: string | null;
  messages: Array<{
    id: string; user: string; assistant: string; run_id?: string | null;
    context?: { version: "assistant-context-v1"; topic_id: string;
      route_request?: { origin_place_id: string; destination_place_id: string; mode: "walk" | "driving" } | null };
    read_tools?: { comparison?: { status: "available" | "unavailable"; items: Array<{place_id:string;name:string;city:string;address:string|null;rating:number|null;reference_cost_yuan:number|null;source:string;retrieved_at:string}>;missing_count:number;semantics:"provider_reference_not_live_quote" }; route?: { status: "available" | "unavailable"; result?: { mode: "walk" | "driving"; distance_meters: number; duration_seconds: number } } };
    place_cards?: Array<{
      place: { place_id: string; name: string; city: string; source: string; retrieved_at: string; images?: import('../data/placeContentRepository').ContentImage[] };
      role: "discussed" | "recommendation"; suggestion_ids: string[];
      detail_path: string; reason_kind: "assistant_advice_unverified";
    }>;
    companion_result?: {
      response_text: string; analysis_summary?: string; goal_type: string; status: "completed" | "needs_information" | "needs_clarification";
      suggestions: Array<{ suggestion_id: string; suggestion_type: string; title: string; summary: string;
        grounding: "unverified_proposal" | "knowledge_supported"; conversation_turn_id: string; status: string }>;
      resolved_suggestion_refs: string[];
      explanation?: { explanation_type: string; based_on_prior_decision: boolean; source_turn_ref?: string | null; source_decision_ref?: string | null; fact_freshness_warning?: string | null } | null;
      runtime_trace: string[];
      answer_evidence_refs?: string[];
      knowledge_evidence?: Array<{ evidence_ref: string; text: string; source_reference: string;
        knowledge_type: string; scope: "stable" | "semi_stable"; document_id?: string | null;
        chunk_id?: string | null; source_name?: string | null; external_place_ref?: string | null }>;
      grounding_status?: string;
      grounding_limitations?: string[];
      knowledge_retrieval?: { status: string; outcome?: string | null; retrieval_mode?: string | null } | null;
    };
    planning_brief?: { brief_id: string; status: "prepared" | "needs_clarification";
      authorization_turn_id: string; suggestion_refs: string[]; must_do: string[] } | null;
    goal_routing?: {
      goal_type: "travel_chat" | "destination_exploration" | "destination_discovery" | "travel_advice" | "comparison" | "recommendation" | "explanation" | "trip_planning" | "trip_modification" | "replan" | "trip_execution";
      confidence: number; target_runtime: "companion" | "planning" | "execution";
      mutation_requested: boolean; trip_context_required: boolean; knowledge_required: boolean;
      live_fact_likely_required: boolean; referenced_entities: string[];
      referenced_previous_decision: boolean; clarification_needed: boolean; signals: string[];
    };
  }>;
  pending_action: null | {
    id: string; tool: "create_trip" | "reschedule_trip" | "reuse_trip";
    title: string; source_title?: string; city: { name: string };
    start_date: string; end_date: string; total_budget_fen: number; daily_budget_fen: number;
    preferences: string; summary: string;
  };
}
