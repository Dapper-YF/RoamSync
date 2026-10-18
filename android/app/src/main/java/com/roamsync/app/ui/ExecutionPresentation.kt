package com.roamsync.app.ui

import com.roamsync.app.data.remote.DisruptionReference
import com.roamsync.app.data.remote.ExecutionProgress
import com.roamsync.app.data.remote.RecoveryPlanningReference
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Presentation-only translation of the server execution projection.
 * It deliberately contains no ETA, Slack, or feasibility calculation. */
enum class ExecutionTone { NORMAL, WARNING, DISRUPTION, UNKNOWN }

fun shouldShowDebugDelayControls(isDebugBuild: Boolean): Boolean = isDebugBuild

data class SlackPresentation(val value: Int, val valueText: String, val explanation: String)
data class ImpactedActivityPresentation(val name: String, val scheduledTime: String?)
data class RecoveryPresentation(val headline: String, val detail: String? = null, val isFailure: Boolean = false)
data class DisruptionPresentation(
    val headline: String,
    val explanation: String,
    val impactedActivity: ImpactedActivityPresentation?,
    val firstDetectedAt: String,
    val lastSeenAt: String,
)
data class ExecutionPresentation(
    val tone: ExecutionTone,
    val headline: String,
    val detail: String,
    val targetName: String?,
    val slack: SlackPresentation?,
    val disruption: DisruptionPresentation? = null,
    val recovery: RecoveryPresentation? = null,
    val syncDelayed: Boolean = false,
)

fun selectExecutionPresentation(progress: ExecutionProgress?, syncDelayed: Boolean): ExecutionPresentation {
    if (progress == null) return ExecutionPresentation(
        tone = ExecutionTone.UNKNOWN, headline = "正在读取行程状态", detail = "导航继续运行，正在同步 RoamSync 行程状态。", targetName = null, slack = null, syncDelayed = syncDelayed,
    )
    val disruption = progress.activeDisruption
    // A live detector may recover after the event was persisted (for example
    // once the device reaches the destination). The disruption card explains
    // why the event was raised, so its persisted impact snapshot is the
    // authoritative display fact for that card.
    val slackValue = disruption?.impactSnapshot?.get("minimum_slack_minutes")
        ?.jsonPrimitive?.intOrNull ?: progress.minimumDownstreamSlackMinutes
    val slack = slackValue?.let(::presentSlack)
    val impacted = impactedActivity(progress)
    if (disruption != null) return ExecutionPresentation(
        tone = ExecutionTone.DISRUPTION,
        headline = "当前延误将影响后续行程",
        detail = disruptionExplanation(disruption.eventType),
        targetName = progress.navigationTargetName,
        slack = slack,
        disruption = DisruptionPresentation(
            headline = disruptionTitle(disruption.eventType),
            explanation = disruptionExplanation(disruption.eventType),
            impactedActivity = impacted,
            firstDetectedAt = disruption.detectedAt,
            lastSeenAt = disruption.lastSeenAt,
        ),
        recovery = presentRecovery(progress.activeRecoveryRun, progress.recoveryRevision != null),
        syncDelayed = syncDelayed,
    )
    val delayed = progress.riskLevel == "eta_delayed" || progress.riskLevel == "warning"
    return if (delayed) ExecutionPresentation(
        tone = ExecutionTone.WARNING,
        headline = "预计到达有所延迟",
        detail = "当前计划仍可执行，后续安排暂不受影响。",
        targetName = progress.navigationTargetName,
        slack = slack,
        syncDelayed = syncDelayed,
    ) else ExecutionPresentation(
        tone = if (progress.riskLevel == "unknown") ExecutionTone.UNKNOWN else ExecutionTone.NORMAL,
        headline = if (progress.riskLevel == "unknown") "正在读取行程状态" else "行程正常",
        detail = if (progress.riskLevel == "unknown") "等待下一次服务端状态同步。" else "当前安排仍在可执行范围内。",
        targetName = progress.navigationTargetName,
        slack = slack,
        syncDelayed = syncDelayed,
    )
}

fun presentSlack(value: Int) = SlackPresentation(
    value = value,
    valueText = if (value > 0) "+$value min" else "$value min",
    explanation = when {
        value > 0 -> "仍有 $value 分钟缓冲"
        value < 0 -> "预计超出可行时间 ${-value} 分钟"
        else -> "已没有时间缓冲"
    },
)

private fun impactedActivity(progress: ExecutionProgress): ImpactedActivityPresentation? {
    val identity = progress.firstImpactedActivityId ?: progress.activeDisruption?.impactedIdentity ?: return null
    val activity = progress.execution.activities.find { it.activityId == identity } ?: return null
    return ImpactedActivityPresentation(activity.name, activity.scheduledTime.takeIf { it.isNotBlank() })
}

private fun disruptionTitle(eventType: String) = when (eventType) {
    "missed_time_window" -> "预计无法按时到达"
    "itinerary_infeasible" -> "当前行程已无法按原计划完成"
    else -> "当前行程需要关注"
}

private fun disruptionExplanation(eventType: String) = when (eventType) {
    "missed_time_window" -> "预计到达时间已超过后续活动的固定时间窗。"
    "itinerary_infeasible" -> "当前延误已使后续安排无法按原计划衔接。"
    else -> "RoamSync 发现当前行程可能无法继续按原计划执行。"
}

private fun presentRecovery(run: RecoveryPlanningReference?, hasPendingRevision: Boolean): RecoveryPresentation? = when {
    hasPendingRevision -> RecoveryPresentation("恢复方案已准备好", "稍后可在恢复方案中查看并决定是否采用。")
    run == null -> null
    run.status == "queued" -> RecoveryPresentation("恢复方案已排队", "RoamSync 正在等待生成恢复方案。")
    run.status in setOf("researching", "planning", "validating", "awaiting_clarification") -> RecoveryPresentation("正在生成恢复方案", "RoamSync 正在分析当前行程影响。")
    run.status == "failed" -> RecoveryPresentation("恢复方案生成失败", "暂未改变正式行程，请继续按当前导航前进。", true)
    run.status == "rejected" -> RecoveryPresentation("之前的恢复方案已被拒绝")
    else -> RecoveryPresentation("恢复方案状态：${run.status}")
}
