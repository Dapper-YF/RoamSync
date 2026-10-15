package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationObservationRequest
import java.time.Duration
import java.time.Instant

class ObservationUploadPolicy(
    private val minInterval: Duration = Duration.ofSeconds(5),
    private val durationDeltaSeconds: Int = 45,
    private val distanceDeltaMeters: Int = 75,
) {
    fun shouldUpload(previous: NavigationObservationRequest?, current: NavigationObservationRequest, now: Instant): Boolean {
        if (previous == null || previous.navigationStatus != current.navigationStatus || current.navigationStatus == "arrived") return true
        if (Duration.between(Instant.parse(previous.observedAt), now) >= minInterval) return true
        if (kotlin.math.abs(previous.remainingDurationSeconds - current.remainingDurationSeconds) >= durationDeltaSeconds) return true
        return kotlin.math.abs(previous.remainingDistanceMeters - current.remainingDistanceMeters) >= distanceDeltaMeters
    }
}
