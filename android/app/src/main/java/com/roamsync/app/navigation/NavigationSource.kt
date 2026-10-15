package com.roamsync.app.navigation

import android.view.View
import kotlinx.coroutines.flow.StateFlow

/** SDK-neutral contract. No trip feasibility or backend mutation belongs here. */
enum class NavigationLifecycle { IDLE, PRIVACY_REQUIRED, CALCULATING, ROUTE_READY, NAVIGATING, REROUTING, ARRIVED, STOPPING, STOPPED, FAILED }
data class NavigationBinding(val tripId: String, val tripExecutionId: String, val sessionId: String, val itineraryVersion: Int, val fromActivityId: String, val toActivityId: String, val routeRevision: Long = 0, val coordinateSystem: String = "gcj02")
data class NavigationRouteInput(val binding: NavigationBinding, val originLongitude: Double, val originLatitude: Double, val destinationLongitude: Double, val destinationLatitude: Double, val travelMode: String, val coordinateSystem: String)
data class NavigationRuntimeState(val binding: NavigationBinding? = null, val lifecycle: NavigationLifecycle = NavigationLifecycle.IDLE, val generation: Long = 0, val remainingDistanceMeters: Int? = null, val remainingDurationSeconds: Int? = null, val etaEpochMillis: Long? = null, val longitude: Double? = null, val latitude: Double? = null, val locationAccuracyMeters: Float? = null, val currentRoad: String? = null, val nextInstruction: String? = null, val routeRevision: Long = 0, val error: String? = null)
interface NavigationSource {
    val state: StateFlow<NavigationRuntimeState>
    suspend fun calculate(input: NavigationRouteInput, generation: Long)
    suspend fun startSimulation(generation: Long)
    suspend fun stop(generation: Long)
    fun createNavigationView(): View?
    fun releaseNavigationView()
}
