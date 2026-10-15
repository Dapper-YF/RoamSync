package com.roamsync.app.data.remote

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable data class DayPlan(
    val id: String, val date: String, val label: String = "", val theme: String = "",
    val route_mode: String = "walk", val activities: List<PlanActivity> = emptyList(),
    val route_legs: List<RouteLeg> = emptyList(), val conflicts: List<PlanConflict> = emptyList(),
)
@Serializable data class PlanConflict(val message: String)
@Serializable data class PlanActivity(
    val id: String, val place_id: String, val name: String, val display_name: String = "",
    val scheduled_time: String, val duration_minutes: Int, val estimated_cost_fen: Long,
    val longitude: Double, val latitude: Double, val neighborhood: String = "",
    val status: String = "planned", val importance: String = "normal", val schedule_locked: Boolean = false,
    val version: Int, val note: String? = null,
)
@Serializable data class RouteLeg(
    val from_activity_id: String, val to_activity_id: String, val mode: String,
    val distance_meters: Int, val duration_minutes: Int, val is_estimated: Boolean = false,
    val path: List<List<Double>> = emptyList(),
)
@Serializable data class PlaceCandidate(val id: String, val name: String)
@Serializable data class AssistantSession(
    val id: String, val trip_id: String? = null, val latest_run_id: String? = null,
    val messages: List<AssistantMessage> = emptyList(), val pending_action: AssistantAction? = null,
)
@Serializable data class AssistantMessage(val id: String, val user: String, val assistant: String, val run_id: String? = null)
@Serializable data class AssistantCity(val name: String)
@Serializable data class AssistantAction(
    val id: String, val tool: String, val title: String, val city: AssistantCity,
    val start_date: String, val end_date: String, val total_budget_fen: Long, val daily_budget_fen: Long,
    val summary: String, val preferences: String = "", val source_title: String? = null,
)
@Serializable data class PlanningRun(
    val id: String, val trip_id: String, val status: String, val user_request: String,
    val response_text: String? = null, val error_message: String? = null,
    val pending_interrupt: PlanningInterrupt? = null,
) {
    val working get() = status in setOf("queued", "researching", "planning", "validating")
}
@Serializable data class PlanningInterrupt(val kind: String, val questions: List<String> = emptyList())
@Serializable data class RunDecision(val run: PlanningRun)
@Serializable data class ProposedActivity(
    val candidate_id: String, val day_date: String, val place_candidate_id: String,
    val planned_start_time: String, val duration_minutes: Int, val estimated_cost_fen: Long,
    val reason: String = "",
)
@Serializable data class ProposedPlan(val explanation: String = "", val activities: List<ProposedActivity> = emptyList())
@Serializable data class PlanRevision(
    val id: String, val status: String, val reason: String, val proposed_snapshot: ProposedPlan,
    val validation_result: JsonObject = JsonObject(emptyMap()), val source_ids: List<String> = emptyList(),
)
