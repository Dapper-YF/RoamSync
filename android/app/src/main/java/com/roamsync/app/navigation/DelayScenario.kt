package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationObservationRequest
import java.time.Instant

enum class DelayScenario(val minutes: Int, val label: String) {
    NORMAL(0, "正常"), MINOR(8, "轻微延误 +8m"), MAJOR(30, "严重延误 +30m");
    fun decorate(value: NavigationObservationRequest): NavigationObservationRequest =
        if (minutes == 0) value else value.copy(
            remainingDurationSeconds = value.remainingDurationSeconds + minutes * 60,
            eta = Instant.parse(value.eta).plusSeconds(minutes * 60L).toString(),
        )
}
