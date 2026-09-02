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
  totalBudgetFen: Fen;
  dailyBudgetFen: Fen;
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
  totalBudgetFen: Fen;
  dailyBudgetFen: Fen;
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
  remainingFen: Fen;
  ratio: number;
  status: "comfortable" | "watch" | "over";
}

export interface PlanningBudgetDay extends BudgetSummary {
  dayPlanId: string;
  date: string;
}

export interface PlanningBudget {
  tripId: string;
  totalPlannedFen: Fen;
  totalRemainingFen: Fen;
  days: PlanningBudgetDay[];
}

export interface ActualBudget {
  tripId: string;
  totalBudgetFen: Fen;
  totalSpentFen: Fen;
  totalRemainingFen: Fen;
  dailyBudgetFen: Fen;
  todaySpentFen: Fen;
  todayRemainingFen: Fen;
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
}

export type PlanningRunStatus =
  | "queued" | "researching" | "awaiting_clarification" | "planning" | "validating"
  | "awaiting_confirmation" | "accepted" | "rejected" | "failed" | "cancelled";

export interface PlanningRun {
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
  pendingInterrupt?: { kind?: string; questions?: string[]; revision_id?: string };
}

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
}

export interface PlanRevision {
  id: string;
  planningRunId: string;
  reason: string;
  activities: CandidatePlanActivity[];
  differenceSummary: Record<string, unknown>;
  validationResult: Record<string, unknown>;
  sourceIds: string[];
  status: "pending" | "accepted" | "rejected" | "superseded";
}

export interface TripPlanningRepository {
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
  createPlanningRun(tripId: string, userRequest: string): Promise<PlanningRun>;
  getPlanningRun(runId: string): Promise<PlanningRun>;
  answerPlanningRun(runId: string, answer: string): Promise<PlanningRun>;
  getPlanRevision(runId: string): Promise<PlanRevision>;
  acceptPlanRevision(revisionId: string): Promise<PlanRevision>;
  rejectPlanRevision(revisionId: string): Promise<PlanRevision>;
}
