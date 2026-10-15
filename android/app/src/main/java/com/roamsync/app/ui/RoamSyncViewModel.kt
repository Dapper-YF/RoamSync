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
    val assistantReady: Boolean = false, val scopedDay: Boolean = false,
    val executionProgress: ExecutionProgress? = null,
    val navigationStart: NavigationStartResponse? = null,
    val navigationRuntime: NavigationRuntimeState = NavigationRuntimeState(),
    val serverNavigation: ServerExecutionState = ServerExecutionState(),
    val executionStateSyncDelayed: Boolean = false,
    val delayScenario: DelayScenario = DelayScenario.NORMAL,
) {
    val day get() = days.find { it.id == dayId } ?: days.firstOrNull()
}

fun shouldAcceptExecutionProgress(incomingSequence: Long?, acceptedObservationSequence: Long): Boolean =
    (incomingSequence ?: acceptedObservationSequence) >= acceptedObservationSequence

fun requireSavedPlan(run: PlanningRun, revision: PlanRevision) {
    check(run.status == "accepted" && revision.status == "accepted") { "方案尚未保存，请重新读取确认状态。" }
}

@HiltViewModel
class RoamSyncViewModel @Inject constructor(private val api: RoamSyncApi, private val saved: SavedStateHandle = SavedStateHandle(), private val runtime: NavigationRuntime? = null) : ViewModel() {
    private val mutable = MutableStateFlow(RoamSyncUiState())
    val state = mutable.asStateFlow()
    private var poll: Job? = null
    private var executionPoll: Job? = null
    private var work: Job? = null
    private var operationToken = 0
    private var submission: Pair<String, String>? = null
    private var expenseSubmission: Pair<String, String>? = null
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
        else { val trips = api.trips(); mutable.update { it.copy(trips = trips, loaded = true) } }
    }
    private suspend fun loadTrip(id: String) = coroutineScope {
        val trip = async { api.getTrip(id) }; val days = async { api.days(id) }; val budget = async { api.getBudget(id) }
        // This persisted BFF projection makes reopen/rotation recoverable. It
        // is still read-only: the server remains session authority.
        val progress = async { api.executionProgress(id) }
        val loadedTrip = trip.await(); val loadedDays = days.await(); val loadedBudget = budget.await(); val loadedProgress = progress.await()
        mutable.update { it.copy(trip = loadedTrip, days = loadedDays, budget = loadedBudget, executionProgress = loadedProgress,
            dayId = it.dayId?.takeIf { key -> loadedDays.any { d -> d.id == key } } ?: loadedDays.firstOrNull()?.id) }
    }
    fun openTrip(id: String) = operation {
        poll?.cancel(); executionPoll?.cancel(); loadTrip(id)
        mutable.update { it.copy(screen = AppScreen.DETAIL, tab = 0, session = null, run = null, revision = null, draft = "") }
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
                mutable.update { it.copy(screen = AppScreen.TRIPS, trip = null, days = emptyList(), budget = null, executionProgress = null, navigationStart = null) }; refresh()
            }
            else -> Unit
        }
    }
    fun selectDay(id: String) { mutable.update { it.copy(dayId = id) } }
    fun selectTab(tab: Int) { mutable.update { it.copy(tab = tab) } }
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
            mutable.update { it.copy(revision = revision, candidateNames = candidates.associate { p -> p.id to p.name }) }
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
            val next = api.decideRun(run.id, buildJsonObject { put("decision", if (accept) "accept" else "reject") }).run
            syncRun(next)
            if (accept) {
                requireSavedPlan(next, requireNotNull(mutable.value.revision))
                try { loadTrip(next.trip_id) }
                catch (e: Exception) { throw IllegalStateException("方案已保存，但正式行程读取失败。请点击刷新重试。", e) }
                mutable.update { it.copy(notice = "已保存到正式行程，最新安排已同步") }
            }
        }
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
