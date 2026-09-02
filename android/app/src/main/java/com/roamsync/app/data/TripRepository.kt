package com.roamsync.app.data

import com.roamsync.app.data.remote.BudgetResponse
import com.roamsync.app.data.remote.ExpenseCreateRequest
import com.roamsync.app.data.remote.RoamSyncApi
import com.roamsync.app.data.remote.TripCreateRequest
import com.roamsync.app.data.remote.TripResponse
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TripRepository @Inject constructor(private val api: RoamSyncApi) {
    suspend fun isBackendReady(): Boolean = api.ready().status == "ready"
    suspend fun createTrip(request: TripCreateRequest): TripResponse = api.createTrip(request)
    suspend fun getTrip(tripId: String): TripResponse = api.getTrip(tripId)
    suspend fun getBudget(tripId: String): BudgetResponse = api.getBudget(tripId)
    suspend fun createExpense(tripId: String, request: ExpenseCreateRequest) =
        api.createExpense(tripId, request)
}
