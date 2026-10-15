package com.roamsync.app.navigation

import android.view.View
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton
import com.roamsync.app.data.remote.NavigationObservationResponse

data class ServerExecutionState(
    val acceptedSequence: Long = 0,
    val currentEta: String? = null,
    val remainingDistanceMeters: Int? = null,
    val remainingDurationSeconds: Int? = null,
    val riskLevel: String = "unknown",
    val slackMinutes: Int? = null,
    val disruptionId: String? = null,
    val recoveryStatus: String? = null,
    val syncDelayed: Boolean = false,
    val backendSessionOutdated: Boolean = false,
)

enum class UploadFailureAction { RETRY_LATEST, STOP_STALE_SESSION, DROP_INVALID_PAYLOAD }

fun classifyUploadFailure(statusCode: Int): UploadFailureAction = when {
    statusCode == 409 -> UploadFailureAction.STOP_STALE_SESSION
    statusCode in 400..499 && statusCode !in setOf(408, 429) -> UploadFailureAction.DROP_INVALID_PAYLOAD
    else -> UploadFailureAction.RETRY_LATEST
}

fun ServerExecutionState.withResponse(response: NavigationObservationResponse) = copy(
    acceptedSequence = response.acceptedSequence,
    currentEta = response.currentEta,
    remainingDistanceMeters = response.remainingDistanceMeters,
    remainingDurationSeconds = response.remainingDurationSeconds,
    riskLevel = response.riskLevel,
    slackMinutes = response.minimumDownstreamSlackMinutes,
    disruptionId = response.activeDisruption?.id,
    recoveryStatus = response.recoveryPlanning?.status,
    syncDelayed = false,
    backendSessionOutdated = false,
)

fun acceptsRuntimeGeneration(callbackGeneration: Long, currentGeneration: Long): Boolean =
    callbackGeneration == currentGeneration

@Singleton class NavigationRuntime @Inject constructor(private val source: NavigationSource, private val privacy: AmapPrivacyGate, private val observations: NavigationObservationRepository) {
    private val mutable = MutableStateFlow(NavigationRuntimeState())
    val state: StateFlow<NavigationRuntimeState> = mutable.asStateFlow()
    private val serverMutable = MutableStateFlow(ServerExecutionState())
    val serverState: StateFlow<ServerExecutionState> = serverMutable.asStateFlow()
    private var input: NavigationRouteInput? = null
    private var generation = 0L
    private var nextSequence = 1L
    private val sequence = ObservationSequence()
    private var lastUploaded: com.roamsync.app.data.remote.NavigationObservationRequest? = null
    private val outbox = ObservationOutbox()
    private var uploading = false
    private var scenario = DelayScenario.NORMAL
    private val mapper = NavigationObservationMapper()
    private val policy = ObservationUploadPolicy()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    init { scope.launch { source.state.collect { if (acceptsRuntimeGeneration(it.generation, generation)) { mutable.value = it; enqueueObservation(it) } } } }
    suspend fun bind(route: NavigationRouteInput, lastAcceptedSequence: Long = 0, routeRevision: Long = 0) { generation++; input = route; sequence.bind(route.binding.sessionId, route.binding.itineraryVersion, lastAcceptedSequence); nextSequence = sequence.next(route.binding.sessionId, route.binding.itineraryVersion); lastUploaded = null; outbox.clear(); serverMutable.value = ServerExecutionState(acceptedSequence = lastAcceptedSequence); mutable.value = NavigationRuntimeState(route.binding, if (privacy.accepted) NavigationLifecycle.CALCULATING else NavigationLifecycle.PRIVACY_REQUIRED, generation, routeRevision = routeRevision); if (privacy.accepted) source.calculate(route, generation) }
    suspend fun acceptPrivacyAndCalculate() { privacy.accept(); input?.let { source.calculate(it, generation) } }
    suspend fun startSimulation() { source.startSimulation(generation) }
    suspend fun stop() { generation++; mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.STOPPING, generation = generation); source.stop(generation) }
    fun setDelayScenario(value: DelayScenario) { scenario = value; mutable.value.let { enqueueObservation(it, force = true) } }
    fun delayScenario(): DelayScenario = scenario
    private fun enqueueObservation(local: NavigationRuntimeState, force: Boolean = false) {
        if (local.generation != generation || serverMutable.value.backendSessionOutdated) return
        val raw = mapper.map(local, nextSequence) ?: return
        val current = scenario.decorate(raw)
        if (!force && !policy.shouldUpload(lastUploaded, current, java.time.Instant.now())) return
        // Latest-value semantics: telemetry is a current execution fact, not an audit log.
        val transition = force || current.navigationStatus == "arrived" || lastUploaded?.navigationStatus != current.navigationStatus
        outbox.offer(current, transition)
        if (!uploading) { uploading = true; scope.launch { drain() } }
    }
    private suspend fun drain() {
        while (true) {
            val item = outbox.poll()?.copy(sequence = nextSequence) ?: break
            try {
                val response = observations.upload(item)
                sequence.accepted(response.acceptedSequence)
                nextSequence = sequence.next(item.sessionId, item.itineraryVersion)
                lastUploaded = item
                serverMutable.value = serverMutable.value.withResponse(response)
            } catch (e: retrofit2.HttpException) {
                when (classifyUploadFailure(e.code())) {
                    UploadFailureAction.STOP_STALE_SESSION -> {
                        outbox.clear()
                        serverMutable.value = serverMutable.value.copy(backendSessionOutdated = true, syncDelayed = true)
                        break
                    }
                    UploadFailureAction.DROP_INVALID_PAYLOAD -> {
                        // Contract/auth failures will not heal by replaying the
                        // same payload on every AMap callback.
                        outbox.clear()
                        serverMutable.value = serverMutable.value.copy(syncDelayed = true)
                        break
                    }
                    UploadFailureAction.RETRY_LATEST -> Unit
                }
                outbox.restoreLatest(item)
                serverMutable.value = serverMutable.value.copy(syncDelayed = true)
                uploading = false
                return
            } catch (_: Exception) {
                outbox.restoreLatest(item)
                serverMutable.value = serverMutable.value.copy(syncDelayed = true)
                uploading = false
                return
            }
        }
        uploading = false
    }
    fun createNavigationView(): View? = source.createNavigationView()
    fun releaseNavigationView() = source.releaseNavigationView()
}
