package com.roamsync.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.roamsync.app.data.remote.*
import com.roamsync.app.navigation.*
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import java.time.LocalDate
import java.time.LocalTime
import java.util.UUID
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*
import retrofit2.HttpException

enum class AppScreen { TRIPS, DETAIL, ASSISTANT, CREATE, NAVIGATION }
data class RoamSyncUiState(
    val screen: AppScreen = AppScreen.TRIPS,
    val trips: List<TripResponse> = emptyList(), val trip: TripResponse? = null,
    val days: List<DayPlan> = emptyList(), val dayId: String? = null, val tab: Int = 0,
    val budget: BudgetResponse? = null, val busy: Boolean = false, val loaded: Boolean = false,
    val error: String? = null, val notice: String? = null,
    val session: AssistantSession? = null, val runs: List<PlanningRun> = emptyList(),
    val run: PlanningRun? = null, val revision: PlanRevision? = null,
    val candidateNames: Map<String, String> = emptyMap(), val draft: String = "",
    val formalRequirements: JsonObject? = null, val formalRequirementsError: String? = null,
    val pendingDecision: PendingFormalDecision? = null,
    val assistantReady: Boolean = false, val scopedDay: Boolean = false,
    val executionProgress: ExecutionProgress? = null,
    val navigationStart: NavigationStartResponse? = null,
    val navigationRuntime: NavigationRuntimeState = NavigationRuntimeState(),
    val serverNavigation: ServerExecutionState = ServerExecutionState(),
    val executionStateSyncDelayed: Boolean = false,
    val delayScenario: DelayScenario = DelayScenario.NORMAL,
    val currentRoutePreview: CurrentRoutePreview? = null,
    val locationObservation: ForegroundLocationObservation? = null,
) {
    val day get() = days.find { it.id == dayId } ?: days.firstOrNull()
}

/** Fresh-fix evidence for the current target, without persisting precise coordinates. */
data class ForegroundLocationObservation(
    val targetActivityId: String,
    val accuracyMeters: Float,
    val capturedAtEpochMillis: Long,
    val provider: String,
    val routeStatus: String,
)

data class PendingFormalDecision(
    val tripId: String, val runId: String, val choice: String, val recovery: Boolean,
    val verifiedAwaitingRetry: Boolean = false,
    val confirmedOutcome: String? = null,
)

data class CurrentRoutePreview(
    val targetActivityId: String,
    val targetName: String,
    val wgs84Longitude: Double,
    val wgs84Latitude: Double,
    val accuracyMeters: Float,
    val capturedAtEpochMillis: Long,
    val mode: String,
    val route: RouteResult,
)

fun shouldAcceptExecutionProgress(incomingSequence: Long?, acceptedObservationSequence: Long): Boolean =
    (incomingSequence ?: acceptedObservationSequence) >= acceptedObservationSequence

fun requireSavedPlan(run: PlanningRun, revision: PlanRevision) {
    check(run.status == "accepted" && revision.status == "accepted") { "方案尚未保存，请重新读取确认状态。" }
}

private fun checkedRequirements(value: JsonObject): JsonObject {
    require(value["version"]?.jsonPrimitive?.intOrNull != null && value["records"] is JsonArray) {
        "有效要求返回内容不可读，请刷新"
    }
    return value
}

private fun requirementStillEffective(value: JsonObject, requirementId: String, dayDate: String?): Boolean {
    if (dayDate == null) return (value["records"] as? JsonArray).orEmpty().any {
        val record = it as? JsonObject
        record?.get("id")?.jsonPrimitive?.contentOrNull == requirementId &&
            record["status"]?.jsonPrimitive?.contentOrNull == "active"
    }
    val byDate = value["effective_by_date"] as? JsonObject ?: return true
    return (byDate[dayDate] as? JsonArray).orEmpty().any {
        (it as? JsonObject)?.get("id")?.jsonPrimitive?.contentOrNull == requirementId
    }
}

@HiltViewModel
class RoamSyncViewModel @Inject constructor(private val api: RoamSyncApi, private val saved: SavedStateHandle = SavedStateHandle(), private val runtime: NavigationRuntime? = null) : ViewModel() {
    private val mutable = MutableStateFlow(RoamSyncUiState(pendingDecision = saved.get<String>("formalDecisionRun")?.let { run ->
        val trip = saved.get<String>("formalDecisionTrip") ?: return@let null
        val choice = saved.get<String>("formalDecisionChoice") ?: return@let null
        PendingFormalDecision(trip, run, choice, saved.get<Boolean>("formalDecisionRecovery") == true)
    }))
    val state = mutable.asStateFlow()
    private var poll: Job? = null
    private var executionPoll: Job? = null
    private var productPlannerPoll: Job? = null
    private var work: Job? = null
    private var operationToken = 0
    private var submission: Pair<String, String>? = null
    private var expenseSubmission: Pair<String, String>? = null
    private var stayExtensionSubmission: Pair<String, String>? = null
    private fun rememberDecision(pending: PendingFormalDecision?) {
        if (pending == null) {
            saved.remove<String>("formalDecisionRun")
            saved.remove<String>("formalDecisionTrip")
            saved.remove<String>("formalDecisionChoice")
            saved.remove<Boolean>("formalDecisionRecovery")
        } else {
            saved["formalDecisionRun"] = pending.runId
            saved["formalDecisionTrip"] = pending.tripId
            saved["formalDecisionChoice"] = pending.choice
            saved["formalDecisionRecovery"] = pending.recovery
        }
        mutable.update { it.copy(pendingDecision = pending) }
    }
    private suspend fun reconcilePendingDecision() {
        val pending = mutable.value.pendingDecision ?: return
        val observed = runCatching { api.run(pending.runId) }.getOrNull() ?: return
        when (observed.status) {
            "accepted", "rejected" -> {
                mutable.update { it.copy(pendingDecision = pending.copy(verifiedAwaitingRetry = false, confirmedOutcome = observed.status)) }
                if (observed.status != pending.choice + "ed") {
                    mutable.update { it.copy(error = "服务端决定与上次提交不一致，请核对正式日程") }
                }
            }
            "awaiting_confirmation" -> mutable.update { it.copy(pendingDecision = pending.copy(verifiedAwaitingRetry = true)) }
            else -> mutable.update { it.copy(error = "原候选状态已变化，请核对后再操作") }
        }
    }
    fun resolvePendingDecision() = operation {
        val pending = requireNotNull(mutable.value.pendingDecision) { "没有待核对的决定" }
        val observed = api.run(pending.runId)
        syncRun(observed)
        reconcilePendingDecision()
        if (observed.status in setOf("accepted", "rejected")) loadTrip(pending.tripId)
        else mutable.update { it.copy(notice = if (observed.status == "awaiting_confirmation") "服务端仍在等待决定；可明确重试上次相同选择" else "候选状态已变化，请核对") }
    }
    fun retryPendingDecision() = operation {
        val pending = requireNotNull(mutable.value.pendingDecision) { "没有待核对的决定" }
        require(pending.verifiedAwaitingRetry) { "请先查询服务端状态" }
        val latest = api.run(pending.runId)
        require(latest.status == "awaiting_confirmation") { "服务端状态已变化，请先刷新核对" }
        performFormalDecision(pending)
    }
    init { refresh(); runtime?.let { value -> viewModelScope.launch { value.state.collect { current -> mutable.update { it.copy(navigationRuntime = current) } } }; viewModelScope.launch { var staleHandled = false; value.serverState.collect { current -> mutable.update { it.copy(serverNavigation = current) }; if (current.backendSessionOutdated && !staleHandled) { staleHandled = true; runCatching { refreshNavigationProgress() } } else if (!current.backendSessionOutdated) { staleHandled = false } } } } }

    private fun operation(block: suspend () -> Unit) {
        if (mutable.value.busy) return
        mutable.update { it.copy(busy = true, error = null, notice = null) }
        val token = ++operationToken
        work = viewModelScope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (token == operationToken) mutable.update { it.copy(error = userError(e)) } }
            finally { if (token == operationToken) mutable.update { it.copy(busy = false) } }
        }
    }
    fun refresh() = operation {
        if (mutable.value.screen == AppScreen.ASSISTANT) restoreAssistant()
        else if (mutable.value.screen == AppScreen.NAVIGATION) refreshNavigationProgress()
        else if (mutable.value.trip != null) loadTrip(requireNotNull(mutable.value.trip).id)
        else {
            val rememberedTripId = saved.get<String>("selectedTripId")
            if (rememberedTripId != null) {
                loadTrip(rememberedTripId)
                mutable.update { it.copy(screen = AppScreen.DETAIL, tab = 0, loaded = true) }
            } else {
                val trips = api.trips(); mutable.update { it.copy(trips = trips, loaded = true) }
            }
        }
    }
    private suspend fun loadTrip(id: String) = coroutineScope {
        if (mutable.value.pendingDecision?.tripId == id) reconcilePendingDecision()
        val trip = async { api.getTrip(id) }; val days = async { api.days(id) }; val budget = async { api.getBudget(id) }
        // This persisted BFF projection makes reopen/rotation recoverable. It
        // is still read-only: the server remains session authority.
        val progress = async { api.executionProgress(id) }
        val planningRuns = async { api.runs(id) }
        val requirements = async { runCatching { checkedRequirements(api.tripRequirements(id)) } }
        val loadedTrip = trip.await(); val loadedDays = days.await(); val loadedBudget = budget.await(); val loadedProgress = progress.await()
        val loadedRuns = planningRuns.await()
        val loadedRequirements = requirements.await()
        mutable.update { it.copy(trip = loadedTrip, days = loadedDays, budget = loadedBudget, executionProgress = loadedProgress,
            runs = loadedRuns, run = null, revision = null, candidateNames = emptyMap(),
            formalRequirements = loadedRequirements.getOrNull(),
            formalRequirementsError = if (loadedRequirements.isFailure) "有效要求暂时无法读取，请刷新后核对。" else null,
            dayId = loadedProgress.execution.currentDayPlanId?.takeIf { key -> loadedDays.any { d -> d.id == key } }
                ?: it.dayId?.takeIf { key -> loadedDays.any { d -> d.id == key } } ?: loadedDays.firstOrNull()?.id,
            currentRoutePreview = it.currentRoutePreview?.takeIf { preview ->
                executionNextStop(loadedProgress, loadedDays, loadedProgress.execution.currentDayPlanId)?.id == preview.targetActivityId
            }) }
        loadedRuns.firstOrNull()?.let { latest -> syncRun(latest); if (latest.working) pollProductPlan(latest) }
        if (mutable.value.pendingDecision?.tripId == id && mutable.value.pendingDecision?.confirmedOutcome in setOf("accepted", "rejected")) rememberDecision(null)
    }
    fun refreshFormalRequirements() = operation {
        val trip = requireNotNull(mutable.value.trip)
        val requirements = checkedRequirements(api.tripRequirements(trip.id))
        mutable.update { it.copy(formalRequirements = requirements, formalRequirementsError = null) }
    }
    fun revokeFormalRequirement(requirementId: String, dayDate: String? = null) = operation {
        val trip = requireNotNull(mutable.value.trip)
        val existing = requireNotNull(mutable.value.formalRequirements) { "请先读取有效要求" }
        val version = existing["version"]?.jsonPrimitive?.intOrNull ?: error("要求版本不可读，请刷新")
        require(requirementId.isNotBlank()) { "请选择一条有效要求" }
        val body = buildJsonObject {
            put("expected_version", version)
            put("requirement_id", requirementId)
            if (dayDate != null) put("day_date", dayDate)
        }
        val result = try { checkedRequirements(api.revokeTripRequirement(trip.id, body)) }
        catch (e: Exception) {
            if (e is CancellationException) throw e
            // A committed revoke can lose its response. Query before offering
            // another write; a version change alone does not prove this revoke.
            val observed = runCatching { checkedRequirements(api.tripRequirements(trip.id)) }.getOrNull()
            if (observed == null || requirementStillEffective(observed, requirementId, dayDate)) {
                mutable.update { it.copy(formalRequirementsError = "撤销结果未确认，请刷新有效要求后核对。") }
                throw e
            }
            observed
        }
        mutable.update { it.copy(formalRequirements = result, formalRequirementsError = null,
            notice = "要求已撤销；正式日程未自动改动") }
    }
    fun openTrip(id: String) = operation {
        poll?.cancel(); executionPoll?.cancel(); productPlannerPoll?.cancel(); loadTrip(id)
        saved["selectedTripId"] = id
        mutable.update { it.copy(screen = AppScreen.DETAIL, tab = 0, session = null, draft = "",
            currentRoutePreview = null, locationObservation = null) }
    }
    fun back() {
        if (mutable.value.busy) {
            if (mutable.value.screen != AppScreen.ASSISTANT) return
            ++operationToken; work?.cancel()
            mutable.update { it.copy(busy = false) }
        }
        poll?.cancel()
        executionPoll?.cancel()
        when (mutable.value.screen) {
            AppScreen.ASSISTANT -> { mutable.update { it.copy(screen = if (it.trip != null) AppScreen.DETAIL else AppScreen.TRIPS, error = null) }; refresh() }
            AppScreen.NAVIGATION -> mutable.update { it.copy(screen = AppScreen.DETAIL, error = null) }
            AppScreen.DETAIL, AppScreen.CREATE -> {
                saved.remove<String>("selectedTripId")
                mutable.update { it.copy(screen = AppScreen.TRIPS, trip = null, days = emptyList(), budget = null, executionProgress = null, navigationStart = null) }; refresh()
            }
            else -> Unit
        }
    }
    fun selectDay(id: String) { mutable.update { it.copy(dayId = id) } }
    fun selectTab(tab: Int) { mutable.update { it.copy(tab = tab) } }
    fun startTodayExecution() = operation {
        val state = mutable.value
        val trip = requireNotNull(state.trip) { "请先打开一趟正式旅行" }
        val today = LocalDate.now(java.time.ZoneId.of(trip.timezone)).toString()
        val day = state.days.firstOrNull { it.date == today } ?: state.day
            ?: error("这趟旅行还没有可执行的正式日程")
        require(day.activities.isNotEmpty()) { "所选日期没有可执行的正式安排" }
        api.startExecution(trip.id, TripExecutionStartRequest(day.id))
        val progress = api.executionProgress(trip.id)
        mutable.update { it.copy(executionProgress = progress, dayId = progress.execution.currentDayPlanId ?: day.id,
            currentRoutePreview = null, notice = if (today == day.date) "已开始当天正式行程" else "已开始所选日期的正式行程") }
    }

    fun executionAction(action: String) = operation {
        val trip = requireNotNull(mutable.value.trip)
        val progress = requireNotNull(mutable.value.executionProgress) { "请先刷新正式行程状态" }
        val executionId = requireNotNull(progress.execution.id) { "请先开始当天正式行程" }
        val activityId = progress.execution.currentActivityId
        require(action in setOf("arrive", "start_activity", "complete", "pause", "resume", "finish")) { "不支持的行程操作" }
        api.tripExecutionAction(executionId, TripExecutionActionRequest(action, activityId))
        val activeNavigation = progress.navigationSession
        if (action in setOf("arrive", "complete") && activeNavigation != null && activeNavigation.toActivityId == activityId) {
            // Manual arrival/completion is the user's execution fact. Close a
            // matching route session only after the formal action succeeds.
            runCatching { api.navigationAction(activeNavigation.id, NavigationSessionActionRequest("complete")) }
        }
        val updated = api.executionProgress(trip.id)
        mutable.update { it.copy(executionProgress = updated,
            dayId = updated.execution.currentDayPlanId ?: it.dayId, currentRoutePreview = null,
            notice = executionActionNotice(action)) }
    }

    fun extendCurrentStay(minutes: Int) = operation {
        require(minutes in 1..480) { "延长时间须在 1–480 分钟之间" }
        val trip = requireNotNull(mutable.value.trip)
        val progress = requireNotNull(mutable.value.executionProgress)
        val currentId = requireNotNull(progress.execution.currentActivityId) { "当前没有可延长的活动" }
        val item = progress.execution.activities.find { it.activityId == currentId }
            ?: error("当前活动状态尚未同步，请刷新后重试")
        val executionActivityId = requireNotNull(item.id) { "活动执行记录尚未创建，请先开始行程" }
        val fingerprint = "${trip.id}|$executionActivityId|$minutes|${progress.itineraryVersion}"
        if (stayExtensionSubmission?.first != fingerprint) {
            stayExtensionSubmission = fingerprint to UUID.randomUUID().toString()
        }
        val result = api.extendStay(executionActivityId, ExtendStayRequest(
            clientActionId = requireNotNull(stayExtensionSubmission).second, extensionMinutes = minutes,
            expectedItineraryVersion = progress.itineraryVersion,
        ))
        val updated = api.executionProgress(trip.id)
        stayExtensionSubmission = null
        mutable.update { it.copy(executionProgress = updated, currentRoutePreview = null,
            notice = "已记录延长 ${result.extensionMinutes} 分钟；后续影响由 RoamSync 服务评估") }
    }

    fun decideRecovery(accept: Boolean) = operation {
        val tripId = requireNotNull(mutable.value.trip).id
        val recovery = requireNotNull(mutable.value.executionProgress?.recoveryPlanning) { "当前没有待决定的恢复方案" }
        require(recovery.status == "awaiting_confirmation" && recovery.pendingRevision != null) { "恢复方案尚未准备好，请刷新后重试" }
        require(mutable.value.pendingDecision == null) { "上次决定结果待核对，请先查询服务端状态" }
        performFormalDecision(PendingFormalDecision(tripId, recovery.planningRunId, if (accept) "accept" else "reject", true))
    }

    private suspend fun performFormalDecision(pending: PendingFormalDecision) {
        val current = mutable.value.pendingDecision
        require(current == null || (current.runId == pending.runId && current.choice == pending.choice && current.recovery == pending.recovery)) {
            "另一项决定结果待核对，请先查询服务端状态"
        }
        rememberDecision(pending.copy(verifiedAwaitingRetry = false))
        val desired = if (pending.choice == "accept") "accepted" else "rejected"
        val decided = try { api.decideRun(pending.runId, buildJsonObject { put("decision", pending.choice) }).run }
        catch (e: Exception) {
            if (e is CancellationException) throw e
            val observed = runCatching { api.run(pending.runId) }.getOrNull()
            if (observed?.status == "awaiting_confirmation") {
                mutable.update { it.copy(pendingDecision = pending.copy(verifiedAwaitingRetry = true)) }
            }
            if (observed?.status != desired) throw IllegalStateException("上次决定结果尚未确认。请先查询服务端状态；已确认日程不会自动改动。", e)
            observed
        }
        require(decided.status == desired) { "服务端决定状态不一致，请刷新核对" }
        // Keep the marker until the adopted trip is reread. A failed refresh
        // must never reopen the stale Accept button against a terminal run.
        mutable.update { it.copy(run = decided, pendingDecision = pending.copy(confirmedOutcome = decided.status)) }
        syncRun(decided)
        if (pending.choice == "accept") requireSavedPlan(decided, requireNotNull(mutable.value.revision))
        try { loadTrip(pending.tripId) }
        catch (e: Exception) { throw IllegalStateException("决定已保存，但正式行程读取失败。请点击刷新重试。", e) }
        mutable.update { it.copy(notice = if (pending.recovery) {
            if (pending.choice == "accept") "恢复方案已由服务接受，正式行程已刷新" else "已拒绝恢复方案，原正式行程仍保留"
        } else if (pending.choice == "accept") "已保存到正式行程，最新安排已同步" else "已保留原日程") }
    }

    fun previewRouteToNextStop(fix: ForegroundLocationFix, mode: String = "walk") = operation {
        require(mode in setOf("walk", "driving")) { "当前支持步行或驾车路线" }
        val state = mutable.value
        val trip = requireNotNull(state.trip)
        val target = executionNextStop(state.executionProgress, state.days, state.dayId)
            ?: error("当前正式行程没有尚未完成的下一站")
        val destination = GeoPoint(target.longitude, target.latitude, "GCJ02")
        val observed = ForegroundLocationObservation(target.id, fix.accuracyMeters,
            fix.capturedAtEpochMillis, fix.provider, "querying")
        mutable.update { it.copy(locationObservation = observed, currentRoutePreview = null) }
        val route = try { api.routeFromCurrentLocation(RouteQuery(fix.gcj02, destination, mode)) }
            catch (e: Exception) {
                if (e is CancellationException) throw e
                mutable.update { it.copy(locationObservation = observed.copy(routeStatus = "unavailable"),
                    error = "前台定位成功；${currentLocationRouteFailure(e)}") }
                return@operation
            }
        mutable.update { it.copy(currentRoutePreview = CurrentRoutePreview(
            targetActivityId = target.id, targetName = target.display_name.ifBlank { target.name },
            wgs84Longitude = fix.wgs84.longitude, wgs84Latitude = fix.wgs84.latitude,
            accuracyMeters = fix.accuracyMeters, capturedAtEpochMillis = fix.capturedAtEpochMillis,
            mode = mode, route = route,
        ), locationObservation = observed.copy(routeStatus = "available")) }
    }

    fun locationError(message: String) { mutable.update { it.copy(error = message, notice = null, locationObservation = null) } }
    fun startNavigation() = operation {
        val trip = requireNotNull(mutable.value.trip)
        val started = api.startNavigation(trip.id, NavigationStartRequest(trip.version))
        mutable.update { it.copy(screen = AppScreen.NAVIGATION, navigationStart = started) }
        refreshNavigationProgress()
        bindRuntime(started.navigationSession)
        beginExecutionPolling()
    }
    fun acceptAmapPrivacy() = operation { runtime?.acceptPrivacyAndCalculate() ?: error("导航引擎暂不可用") }
    fun startSimulation() = operation { runtime?.startSimulation() ?: error("导航引擎暂不可用") }
    fun cancelNavigation() = operation {
        runtime?.stop()
        val active = mutable.value.executionProgress?.navigationSession ?: mutable.value.navigationStart?.navigationSession ?: return@operation
        api.navigationAction(active.id, NavigationSessionActionRequest("cancel"))
        refreshNavigationProgress()
        executionPoll?.cancel()
        mutable.update { it.copy(notice = "导航已停止") }
    }
    private suspend fun bindRuntime(session: NavigationSession) {
        val activities = mutable.value.days.flatMap { it.activities }
        val from = activities.find { it.id == session.fromActivityId } ?: return
        val to = activities.find { it.id == session.toActivityId } ?: return
        runtime?.bind(NavigationRouteInput(NavigationBinding(session.tripId, session.tripExecutionId, session.id, session.itineraryVersion, session.fromActivityId, session.toActivityId, session.routeRevision.toLong(), session.coordinateSystem), from.longitude, from.latitude, to.longitude, to.latitude, session.travelMode, session.coordinateSystem), session.lastLocationSequence, session.routeRevision.toLong())
    }
    fun navigationView() = runtime?.createNavigationView()
    fun releaseNavigationView() = runtime?.releaseNavigationView()
    fun selectDelayScenario(value: DelayScenario) { runtime?.setDelayScenario(value); mutable.update { it.copy(delayScenario = value) } }
    private suspend fun refreshNavigationProgress() {
        val tripId = mutable.value.trip?.id ?: return
        val incoming = api.executionProgress(tripId)
        val accepted = mutable.value.serverNavigation.acceptedSequence
        if (shouldAcceptExecutionProgress(incoming.navigationSession?.lastLocationSequence, accepted)) {
            mutable.update { it.copy(executionProgress = incoming, executionStateSyncDelayed = false) }
        }
    }
    private fun beginExecutionPolling() {
        executionPoll?.cancel()
        executionPoll = viewModelScope.launch {
            while (isActive && mutable.value.screen == AppScreen.NAVIGATION) {
                delay(5000)
                try {
                    refreshNavigationProgress()
                    if (mutable.value.executionProgress?.navigationSession == null) break
                } catch (e: CancellationException) { throw e }
                catch (e: Exception) {
                    // Keep the last successful server projection visible. A
                    // transient read failure must never make a disruption look
                    // normal merely because polling is temporarily unavailable.
                    mutable.update { it.copy(executionStateSyncDelayed = true) }
                }
            }
        }
    }
    private fun draftKey() = "draft:${mutable.value.trip?.id ?: "global"}"
    fun editDraft(text: String) { saved[draftKey()] = text.take(4000); mutable.update { it.copy(draft = text.take(4000)) } }
    fun clearNotice() { mutable.update { it.copy(notice = null) } }
    fun createScreen() { mutable.update { it.copy(screen = AppScreen.CREATE, error = null) } }

    fun openAssistant(draft: String = "", scopedDay: Boolean = false) = operation {
        val restoredDraft = draft.ifBlank { saved.get<String>(draftKey()).orEmpty() }
        mutable.update { it.copy(screen = AppScreen.ASSISTANT, assistantReady = false, session = null,
            run = null, revision = null, draft = restoredDraft, scopedDay = scopedDay) }
        restoreAssistant()
    }
    private suspend fun restoreAssistant() {
        poll?.cancel()
        val tripId = mutable.value.trip?.id
        val session = api.session(buildJsonObject { tripId?.let { put("trip_id", it) } })
        val runs = tripId?.let { api.runs(it) }.orEmpty()
        mutable.update { it.copy(session = session, runs = runs, assistantReady = true) }
        val latest = runs.firstOrNull() ?: session.latest_run_id?.let { api.run(it) }
        if (latest != null) { syncRun(latest); beginPolling(latest) }
    }
    private suspend fun syncRun(run: PlanningRun) {
        mutable.update { it.copy(run = run, runs = listOf(run) + it.runs.filterNot { old -> old.id == run.id }, revision = null) }
        if (run.status in setOf("awaiting_confirmation", "accepted", "rejected")) {
            val revision = api.revision(run.id)
            val candidates = api.candidates(run.trip_id)
            val savedNames = mutable.value.days.flatMap { it.activities }.associate { it.place_id to it.display_name.ifBlank { it.name } }
            mutable.update { it.copy(revision = revision, candidateNames = savedNames + candidates.associate { p -> p.id to p.name }) }
        }
    }
    private fun beginPolling(initial: PlanningRun) {
        poll?.cancel()
        if (!initial.working) return
        poll = viewModelScope.launch {
            while (isActive && mutable.value.screen == AppScreen.ASSISTANT) {
                delay(1500)
                try {
                    val next = api.run(initial.id); syncRun(next)
                    if (!next.working) break
                } catch (e: CancellationException) { throw e }
                catch (e: Exception) { mutable.update { it.copy(error = "进度读取失败，可点击刷新继续：${userError(e)}") }; break }
            }
        }
    }
    private suspend fun receiveSession(session: AssistantSession) {
        if (session.trip_id != null && session.trip_id != mutable.value.trip?.id) loadTrip(session.trip_id)
        mutable.update { it.copy(session = session, run = null, revision = null) }
        session.latest_run_id?.let { id -> val run = api.run(id); syncRun(run); beginPolling(run) }
    }
    fun send() {
        val s = mutable.value
        val message = s.draft.trim()
        if (!s.assistantReady || s.run?.working == true || message.isBlank()) return
        val session = s.session ?: return
        operation {
            if (s.run?.status == "awaiting_clarification") {
                val next = api.decideRun(s.run.id, buildJsonObject { put("decision", "clarify"); put("answer", message) }).run
                editDraft(""); syncRun(next); beginPolling(next)
            } else {
                val key = "$message|${session.id}"
                if (submission?.first != key) submission = key to UUID.randomUUID().toString()
                val next = api.message(session.id, buildJsonObject {
                    put("message", message); put("message_id", requireNotNull(submission).second)
                    if (s.scopedDay) s.day?.id?.let { put("selected_day_id", it) }
                })
                submission = null; editDraft(""); receiveSession(next)
            }
        }
    }
    fun decideAction(accept: Boolean) {
        val session = mutable.value.session ?: return
        val action = session.pending_action ?: return
        operation {
            receiveSession(api.decideAction(session.id, buildJsonObject { put("action_id", action.id); put("accept", accept) }))
            mutable.update { it.copy(notice = if (accept) "旅行已保存" else "已取消，可以继续讨论") }
        }
    }
    fun decidePlan(accept: Boolean) {
        val run = mutable.value.run ?: return
        operation {
            require(run.status == "awaiting_confirmation") { "候选方案尚未准备好，请刷新" }
            require(mutable.value.pendingDecision == null) { "上次决定结果待核对，请先查询服务端状态" }
            performFormalDecision(PendingFormalDecision(run.trip_id, run.id, if (accept) "accept" else "reject", false))
        }
    }
    /** Explicit Planner action used by the single product AI screen.
     * Conversation stays in TourismViewModel; this creates only a planning run. */
    fun requestTripPlan(message: String, scopedDay: Boolean = false) = operation {
        val trip = requireNotNull(mutable.value.trip) { "请先打开正式旅行" }
        val request = message.trim()
        require(request.isNotBlank()) { "请输入具体调整要求" }
        require(mutable.value.pendingDecision == null) { "上次决定结果待核对，请先查询服务端状态" }
        val existing = mutable.value.run
        require(existing?.working != true && existing?.status != "awaiting_confirmation") {
            "已有待决定方案，请先查看或拒绝"
        }
        val days = mutable.value.days
        val previous = api.runs(trip.id)
        val blocking = previous.firstOrNull { it.working || it.status in setOf("awaiting_confirmation", "awaiting_clarification") }
        require(blocking == null || blocking.user_request == request) { "已有待处理的正式候选，请先核对或决定" }
        val pending = blocking
        val run = pending ?: try {
            api.createPlanningRun(trip.id, buildJsonObject {
                put("run_type", if (days.any { it.activities.isNotEmpty() }) "replan" else "initial_plan")
                put("user_request", request)
                if (scopedDay) mutable.value.day?.id?.let { put("selected_day_id", it) }
            })
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            val observed = runCatching { api.runs(trip.id) }.getOrNull()?.firstOrNull()
            if (observed == null || observed.user_request != request ||
                !(observed.working || observed.status == "awaiting_confirmation")) throw e
            observed
        }
        syncRun(run)
        pollProductPlan(run)
    }
    private fun pollProductPlan(run: PlanningRun) {
        productPlannerPoll?.cancel()
        if (run.working) productPlannerPoll = viewModelScope.launch {
            while (isActive && mutable.value.trip?.id == run.trip_id) {
                delay(1500)
                try {
                    val next = api.run(run.id)
                    syncRun(next)
                    if (!next.working) break
                } catch (e: CancellationException) { throw e }
                catch (e: Exception) {
                    mutable.update { it.copy(error = "方案进度读取失败；可刷新方案状态：${userError(e)}") }
                    break
                }
            }
        }
    }
    fun refreshTripPlan() = operation {
        val trip = requireNotNull(mutable.value.trip) { "请先打开正式旅行" }
        val runs = api.runs(trip.id)
        mutable.update { it.copy(runs = runs) }
        runs.firstOrNull()?.let { syncRun(api.run(it.id)) }
    }
    fun decideTripPlan(accept: Boolean) {
        val run = mutable.value.run ?: return
        if (run.status != "awaiting_confirmation") {
            mutable.update { it.copy(error = "候选方案尚未准备好，请刷新") }
            return
        }
        decidePlan(accept)
    }
    fun answerTripPlanClarification(answer: String) = operation {
        val run = requireNotNull(mutable.value.run) { "请先读取候选状态" }
        require(run.status == "awaiting_clarification") { "当前方案无需补充" }
        require(answer.trim().isNotBlank()) { "请先填写补充要求" }
        val next = try { api.decideRun(run.id, buildJsonObject {
            put("decision", "clarify"); put("answer", answer.trim())
        }).run } catch (e: Exception) {
            if (e is CancellationException) throw e
            val observed = runCatching { api.run(run.id) }.getOrNull()
            if (observed == null || observed.status == "awaiting_clarification") throw e
            observed
        }
        syncRun(next)
        pollProductPlan(next)
    }
    fun restoreRun(run: PlanningRun) = operation { val next = api.run(run.id); syncRun(next); beginPolling(next) }
    fun updateActivity(activity: PlanActivity, time: String, duration: String, cost: String, note: String, locked: Boolean) = operation {
        require(runCatching { LocalTime.parse(time) }.isSuccess) { "请输入有效时间，例如 09:30" }
        val minutes = duration.toIntOrNull(); require(minutes != null && minutes in 1..1440) { "停留时间应在 1–1440 分钟之间" }
        val fen = if (cost.trim() in setOf("0", "0.0", "0.00")) 0L else yuanTextToFen(cost)
        require(fen != null) { "请输入有效预算，最多两位小数" }
        api.updateActivity(activity.id, buildJsonObject {
            put("version", activity.version); put("scheduled_time", time); put("duration_minutes", minutes)
            put("estimated_cost_fen", fen); put("note", note); put("schedule_locked", locked)
        })
        loadTrip(requireNotNull(mutable.value.trip).id); mutable.update { it.copy(notice = "活动已更新") }
    }
    fun route(mode: String) = operation {
        api.route(requireNotNull(mutable.value.day).id, buildJsonObject { put("mode", mode) })
        loadTrip(requireNotNull(mutable.value.trip).id)
    }
    fun addExpense(amount: String, category: String, description: String) = operation {
        val fen = yuanTextToFen(amount); require(fen != null && description.isNotBlank()) { "请填写有效金额和消费说明" }
        val id = requireNotNull(mutable.value.trip).id
        val fingerprint = "$id|$fen|$category|${description.trim()}"
        if (expenseSubmission?.first != fingerprint) expenseSubmission = fingerprint to UUID.randomUUID().toString()
        api.createExpense(id, ExpenseCreateRequest(requireNotNull(expenseSubmission).second, fen, category, description.trim()))
        val budget = api.getBudget(id)
        expenseSubmission = null
        mutable.update { it.copy(budget = budget, notice = "记账成功") }
    }
    fun createTrip(title: String, destination: String, start: String, end: String, total: String) = operation {
        require(title.isNotBlank() && destination.isNotBlank()) { "请填写旅行名称和目的地" }
        val startDate = LocalDate.parse(start); val endDate = LocalDate.parse(end)
        val count = java.time.temporal.ChronoUnit.DAYS.between(startDate, endDate) + 1
        require(count in 1..31) { "一次旅行支持 1 至 31 天" }
        val fen = yuanTextToFen(total); require(fen != null && fen >= count) { "请输入有效的旅行总预算" }
        val city = api.cities(destination).filter { it["name"]?.jsonPrimitive?.content?.removeSuffix("市") == destination.removeSuffix("市") }.singleOrNull()
        require(city != null) { "请使用明确的城市名，例如杭州市" }
        val trip = api.createFullTrip(buildJsonObject {
            put("title", title.trim()); put("destination", city.getValue("name"))
            put("destination_adcode", city.getValue("adcode")); put("destination_citycode", city.getValue("citycode"))
            put("center_longitude", city.getValue("longitude")); put("center_latitude", city.getValue("latitude"))
            put("start_date", start); put("end_date", end); put("total_budget_fen", fen); put("daily_budget_fen", fen / count)
        })
        loadTrip(trip.id); mutable.update { it.copy(screen = AppScreen.DETAIL, tab = 0, notice = "旅行已创建，可以告诉旅程总管你的偏好") }
    }
}

private fun userError(e: Exception): String {
    if (e is HttpException) {
        if (e.code() == 409) return "行程已在其他地方更新，请刷新后重试。"
        val detail = runCatching { Json.parseToJsonElement(e.response()?.errorBody()?.string().orEmpty()).jsonObject["detail"] }.getOrNull()
        val message = when (detail) { is JsonPrimitive -> detail.content; is JsonObject -> detail["message"]?.jsonPrimitive?.content; else -> null }
        return message?.let(::planningError) ?: "请求失败（${e.code()}），请稍后重试。"
    }
    return if (e is java.io.IOException) "暂时无法连接服务，请检查网络后重试。" else e.message ?: "操作失败，请重试。"
}

fun planningError(message: String?): String {
    val text = message.orEmpty()
    return when {
        "intent_scope_new_activity_outside_target" in text -> "这次候选方案超出了指定日期的修改范围，尚未保存。请明确要调整哪几天，或改为调整整趟旅行。"
        "route_travel_time_conflict" in text -> "候选安排没有留够交通时间，尚未保存。可以减少当天地点，或要求预留更多交通时间。"
        "candidate plan still violates constraints" in text -> "暂时没有找到满足全部要求的方案。请调整需求后重试，原行程仍然保留。"
        "timeout" in text.lowercase() || "超时" in text -> "处理超时，请稍后重试。已保存的行程仍然保留。"
        "quota" in text.lowercase() || "429" in text -> "服务配额暂时耗尽，请稍后重试。"
        "provider" in text.lowercase() -> "AI 服务暂时没有完成这次请求，请稍后重试。已保存的行程仍然保留。"
        text.isBlank() -> "服务暂时不可用，请稍后重试。"
        else -> text
    }
}
