package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationObservationRequest

/** Bounded outbox: transitions are ordered; ordinary telemetry is one latest-value slot. */
class ObservationOutbox(private val transitionCapacity: Int = 8) {
    private val transitions = ArrayDeque<NavigationObservationRequest>()
    private var latest: NavigationObservationRequest? = null
    @Synchronized fun offer(value: NavigationObservationRequest, transition: Boolean) {
        if (transition) {
            if (transitions.size == transitionCapacity) transitions.removeFirst()
            transitions.addLast(value)
        } else latest = value
    }
    @Synchronized fun poll(): NavigationObservationRequest? =
        if (transitions.isNotEmpty()) transitions.removeFirst() else latest.also { latest = null }
    @Synchronized fun restoreLatest(value: NavigationObservationRequest) { latest = value }
    @Synchronized fun clear() { transitions.clear(); latest = null }
    @Synchronized fun size(): Int = transitions.size + if (latest == null) 0 else 1
}
