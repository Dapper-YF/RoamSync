package com.roamsync.app.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HealthResponse(val status: String)

@Serializable
data class TripCreateRequest(
    val title: String,
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String,
    @SerialName("total_budget_fen") val totalBudgetFen: Long,
    @SerialName("daily_budget_fen") val dailyBudgetFen: Long,
    val currency: String = "CNY",
    val timezone: String = "Asia/Shanghai",
)

@Serializable
data class TripResponse(
    val id: String,
    val title: String,
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String,
    @SerialName("total_budget_fen") val totalBudgetFen: Long? = null,
    @SerialName("daily_budget_fen") val dailyBudgetFen: Long? = null,
    val currency: String,
    val timezone: String,
    val destination: String = "",
    val accommodation: String = "",
    val status: String = "upcoming",
    val version: Int = 1,
    @SerialName("center_longitude") val longitude: Double? = null,
    @SerialName("center_latitude") val latitude: Double? = null,
)

@Serializable
data class ExpenseCreateRequest(
    @SerialName("idempotency_key") val idempotencyKey: String,
    @SerialName("amount_fen") val amountFen: Long,
    val category: String,
    val description: String,
)

@Serializable
data class ExpenseResponse(
    val id: String,
    @SerialName("trip_id") val tripId: String,
    val duplicate: Boolean,
)

@Serializable
data class BudgetResponse(
    @SerialName("trip_id") val tripId: String,
    val currency: String,
    @SerialName("total_budget_fen") val totalBudgetFen: Long? = null,
    @SerialName("total_spent_fen") val totalSpentFen: Long,
    @SerialName("total_remaining_fen") val totalRemainingFen: Long? = null,
    @SerialName("daily_budget_fen") val dailyBudgetFen: Long? = null,
    @SerialName("today_spent_fen") val todaySpentFen: Long,
    @SerialName("today_remaining_fen") val todayRemainingFen: Long? = null,
    @SerialName("local_date") val localDate: String,
)
