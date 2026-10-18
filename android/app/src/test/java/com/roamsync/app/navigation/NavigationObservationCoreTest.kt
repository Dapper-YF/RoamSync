package com.roamsync.app.navigation

import com.roamsync.app.data.remote.NavigationObservationResponse
import com.roamsync.app.data.remote.RecoveryReference
import com.roamsync.app.ui.shouldAcceptExecutionProgress
import java.time.Instant
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class NavigationObservationCoreTest {
    private val binding = NavigationBinding("trip", "execution", "session-a", 7, "from", "to", 5, "gcj02")
    private fun state(lifecycle: NavigationLifecycle = NavigationLifecycle.NAVIGATING) = NavigationRuntimeState(
        binding = binding, lifecycle = lifecycle, generation = 3,
        remainingDistanceMeters = 1200, remainingDurationSeconds = 600,
        etaEpochMillis = Instant.parse("2026-09-20T02:10:00Z").toEpochMilli(),
        longitude = 120.1, latitude = 30.2, locationAccuracyMeters = 8f,
    )

    @Test fun mapperUsesRuntimeFactsAndServerFences() {
        val value = requireNotNull(NavigationObservationMapper().map(state(), 12, Instant.parse("2026-09-20T02:00:00Z")))
        assertEquals("session-a", value.sessionId); assertEquals(7, value.itineraryVersion)
        assertEquals(12, value.sequence); assertEquals(5, value.routeRevision)
        assertEquals("navigating", value.navigationStatus); assertEquals(1200, value.remainingDistanceMeters)
    }

    @Test fun wirePayloadIncludesBackendRequiredSource() {
        val value = requireNotNull(NavigationObservationMapper().map(state(), 12, Instant.parse("2026-09-20T02:00:00Z")))
        val json = Json.encodeToString(value)
        assertTrue(json.contains("\"source\":\"simulation\""))
    }

    @Test fun sequenceBootstrapsAndSwitchesSessionWithoutLeakage() {
        val sequence = ObservationSequence()
        sequence.bind("a", 7, 11); assertEquals(12, sequence.next("a", 7))
        sequence.accepted(12); assertEquals(13, sequence.next("a", 7))
        sequence.bind("b", 1, 3); assertEquals(4, sequence.next("b", 1))
        assertThrows(IllegalStateException::class.java) { sequence.next("a", 7) }

        val recreated = ObservationSequence()
        recreated.bind("b", 1, 4)
        assertEquals(5, recreated.next("b", 1))
    }

    @Test fun delayScenariosOnlyChangeEtaAndDuration() {
        val base = requireNotNull(NavigationObservationMapper().map(state(), 4, Instant.parse("2026-09-20T02:00:00Z")))
        assertEquals(base, DelayScenario.NORMAL.decorate(base))
        listOf(DelayScenario.MINOR to 480, DelayScenario.MAJOR to 1800).forEach { (scenario, seconds) ->
            val changed = scenario.decorate(base)
            assertEquals(base.remainingDurationSeconds + seconds, changed.remainingDurationSeconds)
            assertEquals(Instant.parse(base.eta).plusSeconds(seconds.toLong()).toString(), changed.eta)
            assertEquals(base.copy(remainingDurationSeconds = changed.remainingDurationSeconds, eta = changed.eta), changed)
        }
    }

    @Test fun uploadPolicyThrottlesTelemetryAndLetsTransitionsThrough() {
        val policy = ObservationUploadPolicy()
        val now = Instant.parse("2026-09-20T02:00:00Z")
        val first = requireNotNull(NavigationObservationMapper().map(state(), 1, now))
        assertTrue(policy.shouldUpload(null, first, now))
        val close = first.copy(sequence = 2, observedAt = now.plusSeconds(2).toString(), remainingDistanceMeters = 1150, remainingDurationSeconds = 570)
        assertFalse(policy.shouldUpload(first, close, now.plusSeconds(2)))
        assertTrue(policy.shouldUpload(first, close.copy(remainingDistanceMeters = 1100), now.plusSeconds(2)))
        assertTrue(policy.shouldUpload(first, close.copy(navigationStatus = "arrived"), now.plusSeconds(2)))
        assertTrue(policy.shouldUpload(first, close, now.plusSeconds(6)))
    }

    @Test fun arrivedMapsWithoutAdvancingExecutionDomain() {
        val arrived = requireNotNull(NavigationObservationMapper().map(state(NavigationLifecycle.ARRIVED), 9))
        assertEquals("arrived", arrived.navigationStatus)
        assertEquals("to", binding.toActivityId)
    }

    @Test fun outboxCoalescesTelemetryButPreservesTransition() {
        val mapper = NavigationObservationMapper(); val now = Instant.parse("2026-09-20T02:00:00Z")
        val one = requireNotNull(mapper.map(state(), 1, now)); val two = one.copy(sequence = 2, remainingDistanceMeters = 900)
        val arrived = one.copy(sequence = 3, navigationStatus = "arrived")
        val box = ObservationOutbox(4)
        box.offer(one, false); box.offer(two, false); assertEquals(1, box.size())
        box.offer(arrived, true); assertEquals(2, box.size())
        assertEquals("arrived", box.poll()?.navigationStatus)
        assertEquals(900, box.poll()?.remainingDistanceMeters)
    }

    @Test fun outboxIsBoundedAndTransientRestoreKeepsLatestFact() {
        val one = requireNotNull(NavigationObservationMapper().map(state(), 1))
        val box = ObservationOutbox(2)
        box.offer(one.copy(sequence = 1), true)
        box.offer(one.copy(sequence = 2), true)
        box.offer(one.copy(sequence = 3), true)
        assertEquals(2, box.size())
        assertEquals(2L, box.poll()?.sequence)
        assertEquals(3L, box.poll()?.sequence)

        box.offer(one.copy(sequence = 4, remainingDistanceMeters = 800), false)
        box.restoreLatest(one.copy(sequence = 5, remainingDistanceMeters = 700))
        assertEquals(700, box.poll()?.remainingDistanceMeters)
    }

    @Test fun httpFailureClassificationStops409AndDoesNotRetryInvalidContract() {
        assertEquals(UploadFailureAction.STOP_STALE_SESSION, classifyUploadFailure(409))
        assertEquals(UploadFailureAction.DROP_INVALID_PAYLOAD, classifyUploadFailure(422))
        assertEquals(UploadFailureAction.RETRY_LATEST, classifyUploadFailure(429))
        assertEquals(UploadFailureAction.RETRY_LATEST, classifyUploadFailure(503))
    }

    @Test fun observationResponseUpdatesOnlyServerProjection() {
        val response = NavigationObservationResponse(
            acceptedSequence = 17, replayed = false, sessionStatus = "active",
            currentEta = "2026-09-20T03:00:00Z", remainingDistanceMeters = 700,
            remainingDurationSeconds = 360, riskLevel = "infeasible",
            minimumDownstreamSlackMinutes = -9,
            activeDisruption = RecoveryReference("disruption", "active", "itinerary_infeasible"),
            recoveryPlanning = RecoveryReference("run", "queued"),
        )
        val value = ServerExecutionState(syncDelayed = true).withResponse(response)
        assertEquals(17, value.acceptedSequence)
        assertEquals("2026-09-20T03:00:00Z", value.currentEta)
        assertEquals(700, value.remainingDistanceMeters)
        assertEquals(-9, value.slackMinutes)
        assertEquals("disruption", value.disruptionId)
        assertEquals("queued", value.recoveryStatus)
        assertFalse(value.syncDelayed)
    }

    @Test fun pollingAndGenerationFencesRejectOlderFacts() {
        assertFalse(shouldAcceptExecutionProgress(11, 12))
        assertTrue(shouldAcceptExecutionProgress(12, 12))
        assertTrue(shouldAcceptExecutionProgress(null, 12))
        assertFalse(acceptsRuntimeGeneration(4, 5))
        assertTrue(acceptsRuntimeGeneration(5, 5))
    }
}
