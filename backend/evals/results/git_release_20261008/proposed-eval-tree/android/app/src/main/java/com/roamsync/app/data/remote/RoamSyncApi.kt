package com.roamsync.app.data.remote

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface RoamSyncApi {
    @GET("health/ready")
    suspend fun ready(): HealthResponse

    @POST("api/v1/trips")
    suspend fun createTrip(@Body request: TripCreateRequest): TripResponse

    @GET("api/v1/trips/{tripId}")
    suspend fun getTrip(@Path("tripId") tripId: String): TripResponse

    @GET("api/v1/trips/{tripId}/budget")
    suspend fun getBudget(@Path("tripId") tripId: String): BudgetResponse

    @POST("api/v1/trips/{tripId}/expenses")
    suspend fun createExpense(
        @Path("tripId") tripId: String,
        @Body request: ExpenseCreateRequest,
    ): ExpenseResponse
}
