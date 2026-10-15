package com.roamsync.app.data.remote

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.PUT
import retrofit2.http.Query
import kotlinx.serialization.json.JsonObject

interface RoamSyncApi {
    @GET("api/v1/trips") suspend fun trips(): List<TripResponse>
    @GET("api/v1/trips/{id}/days") suspend fun days(@Path("id") id: String): List<DayPlan>
    @GET("api/v1/trips/{id}/candidates") suspend fun candidates(@Path("id") id: String): List<PlaceCandidate>
    @GET("api/v1/trips/{id}/planning-runs") suspend fun runs(@Path("id") id: String): List<PlanningRun>
    @GET("api/v1/planning-runs/{id}") suspend fun run(@Path("id") id: String): PlanningRun
    @GET("api/v1/planning-runs/{id}/revision") suspend fun revision(@Path("id") id: String): PlanRevision
    @POST("api/v1/planning-runs/{id}/decision") suspend fun decideRun(@Path("id") id: String, @Body body: JsonObject): RunDecision
    @POST("api/v1/assistant/sessions") suspend fun session(@Body body: JsonObject): AssistantSession
    @POST("api/v1/assistant/sessions/{id}/messages") suspend fun message(@Path("id") id: String, @Body body: JsonObject): AssistantSession
    @POST("api/v1/assistant/sessions/{id}/decision") suspend fun decideAction(@Path("id") id: String, @Body body: JsonObject): AssistantSession
    @PUT("api/v1/activities/{id}") suspend fun updateActivity(@Path("id") id: String, @Body body: JsonObject): PlanActivity
    @POST("api/v1/day-plans/{id}/route") suspend fun route(@Path("id") id: String, @Body body: JsonObject): DayPlan
    @GET("api/v1/locations/cities") suspend fun cities(@Query("keyword") query: String): List<JsonObject>
    @POST("api/v1/trips") suspend fun createFullTrip(@Body body: JsonObject): TripResponse
    @GET("health/ready")
    suspend fun ready(): HealthResponse

    @POST("api/v1/trips")
    suspend fun createTrip(@Body request: TripCreateRequest): TripResponse

    @GET("api/v1/trips/{tripId}")
    suspend fun getTrip(@Path("tripId") tripId: String): TripResponse

    @GET("api/v1/trips/{tripId}/budget")
    suspend fun getBudget(@Path("tripId") tripId: String): BudgetResponse

    @POST("api/v1/trips/{tripId}/navigation/start")
    suspend fun startNavigation(@Path("tripId") tripId: String, @Body request: NavigationStartRequest): NavigationStartResponse

    @GET("api/v1/trips/{tripId}/execution-progress")
    suspend fun executionProgress(@Path("tripId") tripId: String): ExecutionProgress

    @POST("api/v1/navigation-sessions/{sessionId}/actions")
    suspend fun navigationAction(@Path("sessionId") sessionId: String, @Body request: NavigationSessionActionRequest): NavigationSession

    @POST("api/v1/navigation-observations")
    suspend fun observeNavigation(@Body request: NavigationObservationRequest): NavigationObservationResponse

    @POST("api/v1/trips/{tripId}/expenses")
    suspend fun createExpense(
        @Path("tripId") tripId: String,
        @Body request: ExpenseCreateRequest,
    ): ExpenseResponse
}
