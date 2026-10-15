package com.roamsync.app.ui

import com.roamsync.app.data.remote.*
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.*
import org.junit.Test

class ExecutionPresentationTest {
    private fun progress(
        risk: String = "normal", slack: Int? = 15, disruption: DisruptionReference? = null,
        run: RecoveryPlanningReference? = null, revision: RecoveryRevisionReference? = null,
    ) = ExecutionProgress("trip", 1, TripExecution(status = "in_progress", activities = listOf(ActivityExecution("museum", "博物馆预约", "pending", "15:00:00"))),
        navigationTargetName = "博物馆预约", riskLevel = risk, minimumDownstreamSlackMinutes = slack,
        firstImpactedActivityId = "museum", activeDisruption = disruption, activeRecoveryRun = run, recoveryRevision = revision)
    private fun disruption(type: String = "missed_time_window") = DisruptionReference("event", type, "museum", JsonObject(emptyMap()), "2026-09-20T06:00:00Z", "2026-09-20T06:02:00Z", 1)

    @Test fun normalPresentationUsesBackendSlack() { val value = selectExecutionPresentation(progress(), false); assertEquals("行程正常", value.headline); assertEquals("+15 min", value.slack?.valueText); assertEquals("仍有 15 分钟缓冲", value.slack?.explanation) }
    @Test fun delayedPresentationRemainsNonDisruptive() { val value = selectExecutionPresentation(progress(risk = "eta_delayed", slack = 10), false); assertEquals(ExecutionTone.WARNING, value.tone); assertTrue(value.detail.contains("仍可执行")); assertNull(value.disruption) }
    @Test fun disruptionWinsOverDelayedRisk() { val value = selectExecutionPresentation(progress(risk = "eta_delayed", slack = -9, disruption = disruption()), false); assertEquals(ExecutionTone.DISRUPTION, value.tone); assertEquals("预计无法按时到达", value.disruption?.headline); assertEquals("博物馆预约", value.disruption?.impactedActivity?.name); assertEquals("-9 min", value.slack?.valueText) }
    @Test fun disruptionUsesPersistedImpactSlackAfterLiveStateRecovers() {
        val event = disruption().copy(impactSnapshot = JsonObject(mapOf("minimum_slack_minutes" to JsonPrimitive(-9))))
        assertEquals("-9 min", selectExecutionPresentation(progress(slack = 2, disruption = event), false).slack?.valueText)
    }
    @Test fun negativeSlackHasHumanExplanation() { assertEquals("预计超出可行时间 9 分钟", presentSlack(-9).explanation) }
    @Test fun recoveryStatusesArePresentedWithoutCandidateContent() {
        assertEquals("恢复方案已排队", selectExecutionPresentation(progress(disruption = disruption(), run = RecoveryPlanningReference("run", "queued")), false).recovery?.headline)
        assertEquals("正在生成恢复方案", selectExecutionPresentation(progress(disruption = disruption(), run = RecoveryPlanningReference("run", "planning")), false).recovery?.headline)
        assertEquals("恢复方案生成失败", selectExecutionPresentation(progress(disruption = disruption(), run = RecoveryPlanningReference("run", "failed")), false).recovery?.headline)
        assertEquals("恢复方案已准备好", selectExecutionPresentation(progress(disruption = disruption(), revision = RecoveryRevisionReference("revision", "pending")), false).recovery?.headline)
    }
    @Test fun staleStateRetainsLastProjectionAndMarksDelay() { val value = selectExecutionPresentation(progress(disruption = disruption(), run = RecoveryPlanningReference("run", "failed")), true); assertTrue(value.syncDelayed); assertEquals("恢复方案生成失败", value.recovery?.headline) }
    @Test fun debugDelayControlsAreNeverSelectedForRelease() { assertTrue(shouldShowDebugDelayControls(true)); assertFalse(shouldShowDebugDelayControls(false)) }
}
