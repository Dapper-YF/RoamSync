package com.roamsync.app.ui

import com.roamsync.app.data.remote.*
import java.io.IOException
import java.lang.reflect.Proxy
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.*
import org.junit.*
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class PlanningWorkflowTest {
    private val dispatcher = StandardTestDispatcher()
    private val handlers = mutableMapOf<String, (Array<out Any?>) -> Any?>()
    private val api = Proxy.newProxyInstance(RoamSyncApi::class.java.classLoader, arrayOf(RoamSyncApi::class.java)) { _, method, args ->
        handlers[method.name]?.invoke(args ?: emptyArray()) ?: error("Unexpected API call: ${method.name}")
    } as RoamSyncApi
    private val trip = TripResponse("trip", "杭州之旅", "2026-09-20", "2026-09-21", 300000, 150000, "CNY", "Asia/Shanghai", destination = "杭州市")
    private val budget = BudgetResponse("trip", "CNY", 300000, 0, 300000, 150000, 0, 150000, "2026-09-20")
    private val candidate = ProposedActivity("p", "2026-09-20", "place", "09:00:00", 90, 3000, "减少折返")
    private val pending = PlanningRun("run", "trip", "awaiting_confirmation", "丰富一些")
    private val revision = PlanRevision("revision", "pending", "增加文化体验", ProposedPlan("顺路增加一个博物馆", listOf(candidate)))
    private var currentRun = pending
    private var currentRevision = revision
    private var days = listOf(DayPlan("day", "2026-09-20"))

    @Before fun setup() {
        Dispatchers.setMain(dispatcher)
        handlers["trips"] = { listOf(trip) }; handlers["getTrip"] = { trip }; handlers["days"] = { days }; handlers["getBudget"] = { budget }
        handlers["executionProgress"] = { ExecutionProgress("trip", 1, TripExecution(status = "not_started"), riskLevel = "unknown") }
        handlers["session"] = { AssistantSession("session", "trip", "run") }
        handlers["runs"] = { listOf(currentRun) }; handlers["run"] = { currentRun }
        handlers["revision"] = { currentRevision }; handlers["candidates"] = { listOf(PlaceCandidate("place", "博物馆")) }
    }
    @After fun tearDown() { Dispatchers.resetMain() }
    private fun ready(): RoamSyncViewModel {
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        vm.openTrip("trip"); dispatcher.scheduler.runCurrent()
        vm.openAssistant(); dispatcher.scheduler.runCurrent()
        return vm
    }
    @Test fun acceptedPlanReloadsFormalActivities() {
        val vm = ready()
        handlers["decideRun"] = {
            currentRun = pending.copy(status = "accepted"); currentRevision = revision.copy(status = "accepted")
            days = listOf(DayPlan("day", "2026-09-20", activities = listOf(PlanActivity("a", "place", "博物馆", scheduled_time = "09:00:00", duration_minutes = 90, estimated_cost_fen = 3000, longitude = 120.0, latitude = 30.0, version = 1))))
            RunDecision(currentRun)
        }
        vm.decidePlan(true); dispatcher.scheduler.runCurrent()
        assertEquals("博物馆", vm.state.value.days.single().activities.single().name)
        assertEquals("accepted", vm.state.value.revision?.status)
        assertNull(vm.state.value.error)
    }
    @Test fun readFailureAfterAcceptanceDoesNotReportUnsaved() {
        val vm = ready()
        handlers["decideRun"] = { currentRevision = revision.copy(status = "accepted"); RunDecision(pending.copy(status = "accepted")) }
        handlers["days"] = { throw IOException("offline") }
        vm.decidePlan(true); dispatcher.scheduler.runCurrent()
        assertEquals("accepted", vm.state.value.run?.status)
        assertTrue(vm.state.value.error.orEmpty().contains("方案已保存"))
    }
    @Test fun rejectedPlanNeverReloadsOrChangesFormalPlan() {
        val vm = ready()
        handlers["decideRun"] = { currentRevision = revision.copy(status = "rejected"); RunDecision(pending.copy(status = "rejected")) }
        handlers["days"] = { error("Must not load or change plan when rejecting") }
        vm.decidePlan(false); dispatcher.scheduler.runCurrent()
        assertNull(vm.state.value.error); assertTrue(vm.state.value.days.single().activities.isEmpty())
    }
    @Test fun retryMessageKeepsIdempotencyKey() {
        val vm = ready(); val ids = mutableListOf<String>()
        handlers["message"] = { args ->
            ids += (args[1] as JsonObject).getValue("message_id").jsonPrimitive.content
            if (ids.size == 1) throw IOException("timeout")
            AssistantSession("session", "trip")
        }
        vm.editDraft("现在的行程怎么样？"); vm.send(); dispatcher.scheduler.runCurrent()
        vm.send(); dispatcher.scheduler.runCurrent()
        assertEquals(2, ids.size); assertEquals(ids[0], ids[1]); assertEquals("", vm.state.value.draft)
    }
    @Test fun clarificationContinuesRunInsteadOfCreatingAnother() {
        currentRun = pending.copy(status = "awaiting_clarification", pending_interrupt = PlanningInterrupt("clarification", listOf("哪一天？")))
        val vm = ready(); var decision = ""
        handlers["decideRun"] = { args -> decision = (args[1] as JsonObject).getValue("decision").jsonPrimitive.content; RunDecision(pending.copy(status = "answered", response_text = "好的")) }
        vm.editDraft("第一天"); vm.send(); dispatcher.scheduler.runCurrent()
        assertEquals("clarify", decision); assertEquals("answered", vm.state.value.run?.status)
    }
    @Test fun queryingPassesWholeTripUnlessDayWasExplicitlySelected() {
        val vm = ready(); var body = JsonObject(emptyMap())
        handlers["message"] = { args -> body = args[1] as JsonObject; AssistantSession("session", "trip") }
        vm.editDraft("旅行安排如何？"); vm.send(); dispatcher.scheduler.runCurrent()
        assertFalse(body.containsKey("selected_day_id"))
        vm.openAssistant(scopedDay = true); dispatcher.scheduler.runCurrent()
        vm.editDraft("这一天轻松些"); vm.send(); dispatcher.scheduler.runCurrent()
        assertEquals("day", body.getValue("selected_day_id").jsonPrimitive.content)
    }
    @Test fun serverDtoAcceptsAdditionalFieldsAndNullRunId() {
        val json = Json { ignoreUnknownKeys = true }
        val value = json.decodeFromString<AssistantSession>("""{"id":"s","trip_id":null,"latest_run_id":null,"pending_action":null,"messages":[{"id":"m","user":"你好","assistant":"你好","tool":"reply","run_id":null,"goal_routing":{"goal_type":"travel_chat","target_runtime":"companion","mutation_requested":false},"companion_result":{"response_text":"你好","suggestions":[],"runtime_trace":["interpret_goal"],"answer_evidence_refs":["knowledge_1"],"knowledge_evidence":[{"evidence_ref":"knowledge_1","source_reference":"https://whc.unesco.org/en/list/1334","document_id":"history","chunk_id":"chunk"}],"grounding_status":"citations_validated","grounding_limitations":["claim_entailment_not_verified"],"knowledge_retrieval":{"outcome":"available"}},"planning_brief":null}]}""")
        assertEquals("你好", value.messages.single().assistant)
    }
    @Test fun requireBothAcceptedStatuses() {
        assertThrows(IllegalStateException::class.java) { requireSavedPlan(pending.copy(status = "accepted"), revision) }
    }
    @Test fun restoresNewerWebRunBeforeStaleSessionPointer() {
        val webRun = pending.copy(id = "new-web-run", status = "answered", response_text = "来自 Web 的最新回答")
        handlers["runs"] = { listOf(webRun, pending) }
        val vm = ready()
        assertEquals("new-web-run", vm.state.value.run?.id)
    }
    @Test fun manualCreationUsesResolvedCityAndExactMoney() {
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        var body = JsonObject(emptyMap())
        handlers["cities"] = { listOf(Json.parseToJsonElement("""{"name":"杭州市","adcode":"330100","citycode":"0571","longitude":120.1,"latitude":30.2}""").jsonObject) }
        handlers["createFullTrip"] = { args -> body = args[0] as JsonObject; trip }
        vm.createTrip("周末杭州", "杭州", "2026-09-20", "2026-09-21", "1200.50"); dispatcher.scheduler.runCurrent()
        assertEquals(120050, body.getValue("total_budget_fen").jsonPrimitive.int)
        assertEquals("330100", body.getValue("destination_adcode").jsonPrimitive.content)
        assertEquals(AppScreen.DETAIL, vm.state.value.screen)
    }
    @Test fun startNavigationUsesBackendAtomicUseCaseAndRestoresExecutionProjection() {
        val session = NavigationSession("nav", "trip", "exec", "a", "b", 1, "walk", "2026-09-20T09:00:00+08:00", "2026-09-20T09:20:00+08:00", status = "active")
        val execution = TripExecution("exec", "in_progress", "a", listOf(ActivityExecution("a", "起点", "pending", "09:00:00")))
        handlers["startNavigation"] = { args ->
            assertEquals(1, (args[1] as NavigationStartRequest).expectedItineraryVersion)
            NavigationStartResponse(session, execution, false)
        }
        handlers["executionProgress"] = { ExecutionProgress("trip", 1, execution, navigationSession = session, navigationTargetName = "终点", riskLevel = "normal") }
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        vm.openTrip("trip"); dispatcher.scheduler.runCurrent()
        vm.startNavigation(); dispatcher.scheduler.runCurrent()
        assertEquals(AppScreen.NAVIGATION, vm.state.value.screen)
        assertEquals("nav", vm.state.value.executionProgress?.navigationSession?.id)
        assertNull(vm.state.value.error)
    }
    @Test fun cancellingNavigationRefreshesPersistedProjection() {
        val session = NavigationSession("nav", "trip", "exec", "a", "b", 1, "walk", "2026-09-20T09:00:00+08:00", "2026-09-20T09:20:00+08:00", status = "active")
        val execution = TripExecution("exec", "in_progress", "a")
        handlers["startNavigation"] = { NavigationStartResponse(session, execution, false) }
        var live = true
        handlers["executionProgress"] = { ExecutionProgress("trip", 1, execution, if (live) session else null, riskLevel = "normal") }
        handlers["navigationAction"] = { live = false; session.copy(status = "cancelled") }
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        vm.openTrip("trip"); dispatcher.scheduler.runCurrent()
        vm.startNavigation(); dispatcher.scheduler.runCurrent()
        vm.cancelNavigation(); dispatcher.scheduler.runCurrent()
        assertNull(vm.state.value.executionProgress?.navigationSession)
        assertEquals("导航已停止", vm.state.value.notice)
    }

    @Test fun navigationNetworkFailureStaysOnDetailAndShowsRetryableError() {
        handlers["startNavigation"] = { throw IOException("offline") }
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        vm.openTrip("trip"); dispatcher.scheduler.runCurrent()
        vm.startNavigation(); dispatcher.scheduler.runCurrent()
        assertEquals(AppScreen.DETAIL, vm.state.value.screen)
        assertTrue(vm.state.value.error.orEmpty().isNotBlank())
    }

    @Test fun confirmedAssistantCreationOpensNewTripAndKeepsConversation() {
        val vm = RoamSyncViewModel(api); dispatcher.scheduler.runCurrent()
        val action = AssistantAction("action", "create_trip", "杭州", AssistantCity("杭州市"), "2026-09-20", "2026-09-21", 300000, 150000, "创建新旅行")
        handlers["session"] = { AssistantSession("global", pending_action = action) }
        vm.openAssistant(); dispatcher.scheduler.runCurrent()
        handlers["decideAction"] = { args -> assertTrue((args[1] as JsonObject).getValue("accept").jsonPrimitive.boolean); AssistantSession("global", "trip", messages = listOf(AssistantMessage("m", "确认", "旅行已创建"))) }
        vm.decideAction(true); dispatcher.scheduler.runCurrent()
        assertEquals("trip", vm.state.value.trip?.id)
        assertEquals("旅行已创建", vm.state.value.session?.messages?.single()?.assistant)
        assertEquals(AppScreen.ASSISTANT, vm.state.value.screen)
    }
}


