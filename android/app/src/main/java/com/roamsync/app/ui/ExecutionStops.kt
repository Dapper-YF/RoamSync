package com.roamsync.app.ui

import com.roamsync.app.data.remote.DayPlan
import com.roamsync.app.data.remote.ExecutionProgress
import com.roamsync.app.data.remote.PlanActivity

/** Selects only from the formal schedule and persisted execution statuses. */
fun executionCurrentActivity(progress: ExecutionProgress?, days: List<DayPlan>): PlanActivity? {
    val id = progress?.execution?.currentActivityId ?: return null
    return days.asSequence().flatMap { it.activities.asSequence() }.firstOrNull { it.id == id }
}

/**
 * A pending current activity is the next destination. Once the traveller has
 * arrived or started that activity, the next incomplete formal activity is
 * the route destination. This is presentation selection, not plan logic.
 */
fun executionNextStop(progress: ExecutionProgress?, days: List<DayPlan>, defaultDayId: String?): PlanActivity? {
    val execution = progress?.execution
    if (execution?.id == null) return days.firstOrNull { it.id == defaultDayId }?.activities?.firstOrNull()
    if (execution.status == "completed") return null

    val orderedExecution = execution.activities
    val currentId = execution.currentActivityId
    if (currentId == null) {
        val nextId = orderedExecution.firstOrNull { it.status !in TERMINAL_ACTIVITY_STATUSES }?.activityId ?: return null
        return formalActivity(days, nextId)
    }
    val current = orderedExecution.firstOrNull { it.activityId == currentId }
    if (current == null || current.status == "pending") return formalActivity(days, currentId)
    val currentIndex = orderedExecution.indexOfFirst { it.activityId == currentId }
    val nextId = orderedExecution.drop(currentIndex + 1)
        .firstOrNull { it.status !in TERMINAL_ACTIVITY_STATUSES }?.activityId ?: return null
    return formalActivity(days, nextId)
}

fun executionActivityStatus(progress: ExecutionProgress?, activityId: String): String? =
    progress?.execution?.activities?.firstOrNull { it.activityId == activityId }?.status

fun executionActionNotice(action: String): String = when (action) {
    "arrive" -> "已记录手动到达"
    "start_activity" -> "已开始体验当前活动"
    "complete" -> "已完成当前活动，正式执行已切换到下一站"
    "pause" -> "行程执行已暂停"
    "resume" -> "行程执行已恢复"
    "finish" -> "正式行程执行已结束"
    else -> "行程状态已更新"
}

private fun formalActivity(days: List<DayPlan>, id: String) =
    days.asSequence().flatMap { it.activities.asSequence() }.firstOrNull { it.id == id }

private val TERMINAL_ACTIVITY_STATUSES = setOf("completed", "skipped")
