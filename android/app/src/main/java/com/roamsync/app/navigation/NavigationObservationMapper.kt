package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationCoordinate
import com.roamsync.app.data.remote.NavigationObservationRequest
import java.time.Instant

/** Converts RoamSync runtime facts, never AMap DTOs, to the backend contract. */
class NavigationObservationMapper {
    fun map(state: NavigationRuntimeState, sequence: Long, now: Instant = Instant.now()): NavigationObservationRequest? {
        val binding = state.binding ?: return null
        val status = when (state.lifecycle) {
            NavigationLifecycle.NAVIGATING -> "navigating"
            NavigationLifecycle.REROUTING -> "rerouting"
            NavigationLifecycle.ARRIVED -> "arrived"
            else -> return null
        }
        val longitude = state.longitude ?: return null
        val latitude = state.latitude ?: return null
        val seconds = state.remainingDurationSeconds ?: return null
        val distance = state.remainingDistanceMeters ?: return null
        return NavigationObservationRequest(
            sessionId = binding.sessionId, itineraryVersion = binding.itineraryVersion,
            sequence = sequence, observedAt = now.toString(),
            position = NavigationCoordinate(longitude, latitude), coordinateSystem = binding.coordinateSystem,
            locationAccuracyMeters = (state.locationAccuracyMeters ?: 50f).coerceAtLeast(0f),
            remainingDistanceMeters = distance.coerceAtLeast(0), remainingDurationSeconds = seconds.coerceAtLeast(0),
            eta = Instant.ofEpochMilli(state.etaEpochMillis ?: now.plusSeconds(seconds.toLong()).toEpochMilli()).toString(),
            routeRevision = binding.routeRevision.toInt(), navigationStatus = status,
            source = "simulation",
        )
    }
}

class ObservationSequence {
    private var sessionKey: Pair<String, Int>? = null
    private var nextValue: Long = 1
    fun bind(sessionId: String, itineraryVersion: Int, lastAccepted: Long) {
        sessionKey = sessionId to itineraryVersion
        nextValue = lastAccepted + 1
    }
    fun next(sessionId: String, itineraryVersion: Int): Long {
        check(sessionKey == sessionId to itineraryVersion) { "observation sequence belongs to another session" }
        return nextValue
    }
    fun accepted(value: Long) { if (value >= nextValue) nextValue = value + 1 }
}
