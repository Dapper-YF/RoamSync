package com.roamsync.app.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable data class NavigationStartRequest(@SerialName("expected_itinerary_version") val expectedItineraryVersion: Int? = null)
@Serializable data class NavigationCoordinate(val longitude: Double, val latitude: Double)
@Serializable data class NavigationSession(
    val id: String, @SerialName("trip_id") val tripId: String,
    @SerialName("trip_execution_id") val tripExecutionId: String,
    @SerialName("from_activity_id") val fromActivityId: String,
    @SerialName("to_activity_id") val toActivityId: String,
    @SerialName("itinerary_version") val itineraryVersion: Int,
    @SerialName("travel_mode") val travelMode: String,
    @SerialName("planned_departure_at") val plannedDepartureAt: String,
    @SerialName("planned_arrival_at") val plannedArrivalAt: String,
    @SerialName("current_eta") val currentEta: String? = null,
    @SerialName("remaining_distance_meters") val remainingDistanceMeters: Int? = null,
    @SerialName("remaining_duration_seconds") val remainingDurationSeconds: Int? = null,
    @SerialName("route_revision") val routeRevision: Int = 0,
    @SerialName("last_location_sequence") val lastLocationSequence: Long = 0,
    val status: String,
    @SerialName("coordinate_system") val coordinateSystem: String = "gcj02",
)
@Serializable data class ActivityExecution(
    @SerialName("activity_id") val activityId: String, val name: String,
    val status: String, @SerialName("scheduled_time") val scheduledTime: String,
)
@Serializable data class TripExecution(
    val id: String? = null, val status: String,
    @SerialName("current_activity_id") val currentActivityId: String? = null,
    val activities: List<ActivityExecution> = emptyList(),
)
@Serializable data class NavigationStartResponse(
    @SerialName("navigation_session") val navigationSession: NavigationSession,
    val execution: TripExecution, val resumed: Boolean,
)
@Serializable data class ExecutionProgress(
    @SerialName("trip_id") val tripId: String,
    @SerialName("itinerary_version") val itineraryVersion: Int,
    val execution: TripExecution,
    @SerialName("navigation_session") val navigationSession: NavigationSession? = null,
    @SerialName("current_activity_name") val currentActivityName: String? = null,
    @SerialName("navigation_target_name") val navigationTargetName: String? = null,
    @SerialName("risk_level") val riskLevel: String,
    @SerialName("minimum_downstream_slack_minutes") val minimumDownstreamSlackMinutes: Int? = null,
    @SerialName("first_impacted_activity_id") val firstImpactedActivityId: String? = null,
    @SerialName("active_disruption") val activeDisruption: DisruptionReference? = null,
    @SerialName("active_recovery_run") val activeRecoveryRun: RecoveryPlanningReference? = null,
    @SerialName("recovery_revision") val recoveryRevision: RecoveryRevisionReference? = null,
)
@Serializable data class RecoveryReference(val id: String, val status: String? = null, @SerialName("event_type") val eventType: String? = null)
@Serializable data class DisruptionReference(
    val id: String, @SerialName("event_type") val eventType: String,
    @SerialName("impacted_identity") val impactedIdentity: String,
    @SerialName("impact_snapshot") val impactSnapshot: JsonObject = JsonObject(emptyMap()),
    @SerialName("detected_at") val detectedAt: String,
    @SerialName("last_seen_at") val lastSeenAt: String,
    @SerialName("itinerary_version") val itineraryVersion: Int,
)
@Serializable data class RecoveryPlanningReference(
    val id: String, val status: String,
    @SerialName("error_code") val errorCode: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
)
@Serializable data class RecoveryRevisionReference(val id: String, val status: String)
@Serializable data class NavigationSessionActionRequest(val action: String)
@Serializable data class NavigationObservationRequest(
    @SerialName("session_id") val sessionId: String,
    @SerialName("itinerary_version") val itineraryVersion: Int,
    val sequence: Long,
    @SerialName("observed_at") val observedAt: String,
    val position: NavigationCoordinate,
    @SerialName("coordinate_system") val coordinateSystem: String,
    @SerialName("location_accuracy_meters") val locationAccuracyMeters: Float,
    @SerialName("remaining_distance_meters") val remainingDistanceMeters: Int,
    @SerialName("remaining_duration_seconds") val remainingDurationSeconds: Int,
    val eta: String,
    @SerialName("route_revision") val routeRevision: Int,
    @SerialName("navigation_status") val navigationStatus: String,
    // No Kotlin default: kotlinx.serialization omits default-valued fields by
    // default, while the backend deliberately requires the observation source.
    val source: String,
)
@Serializable data class NavigationObservationResponse(
    @SerialName("accepted_sequence") val acceptedSequence: Long,
    val replayed: Boolean,
    @SerialName("session_status") val sessionStatus: String,
    @SerialName("current_eta") val currentEta: String,
    @SerialName("remaining_distance_meters") val remainingDistanceMeters: Int,
    @SerialName("remaining_duration_seconds") val remainingDurationSeconds: Int,
    @SerialName("risk_level") val riskLevel: String,
    @SerialName("minimum_downstream_slack_minutes") val minimumDownstreamSlackMinutes: Int? = null,
    @SerialName("first_impacted_activity_id") val firstImpactedActivityId: String? = null,
    @SerialName("active_disruption") val activeDisruption: RecoveryReference? = null,
    @SerialName("recovery_planning") val recoveryPlanning: RecoveryReference? = null,
)
