package com.roamsync.app.ui

import com.roamsync.app.data.remote.ActivityExecution
import com.roamsync.app.data.remote.DayPlan
import com.roamsync.app.data.remote.ExecutionProgress
import com.roamsync.app.data.remote.PlanActivity
import com.roamsync.app.data.remote.TripExecution
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ExecutionStopsTest {
    private val first = PlanActivity("a", "place-a", "起点", "起点", "09:00:00", 45, 0, 120.0, 30.0, version = 1)
    private val second = PlanActivity("b", "place-b", "下一站", "下一站", "10:00:00", 45, 0, 120.1, 30.1, version = 1)
    private val days = listOf(DayPlan("day", "2026-10-16", activities = listOf(first, second)))

    @Test fun preStartRouteTargetsFirstFormalActivityOnChosenDay() {
        val progress = ExecutionProgress("trip", 1, TripExecution(status = "not_started"), riskLevel = "unknown")
        assertEquals(first, executionNextStop(progress, days, "day"))
        assertNull(executionNextStop(progress, days, "other"))
    }

    @Test fun pendingCurrentActivityIsTheNextStop() {
        val progress = progress("a", listOf(state("a", "pending"), state("b", "pending")))
        assertEquals(first, executionNextStop(progress, days, "day"))
    }

    @Test fun afterArrivalRouteTargetsTheNextIncompleteFormalActivity() {
        val progress = progress("a", listOf(state("a", "in_progress"), state("b", "pending")))
        assertEquals(second, executionNextStop(progress, days, "day"))
        assertEquals(first, executionCurrentActivity(progress, days))
    }

    @Test fun serverAdvancedCurrentActivityBecomesNextStopAfterCompletion() {
        val progress = progress("b", listOf(state("a", "completed"), state("b", "pending")))
        assertEquals(second, executionNextStop(progress, days, "day"))
    }

    private fun progress(currentId: String, activities: List<ActivityExecution>) = ExecutionProgress(
        "trip", 1, TripExecution("execution", "in_progress", currentId, activities), riskLevel = "unknown",
    )

    private fun state(id: String, status: String) = ActivityExecution(id, id, status, "09:00:00", id = "execution-$id")
}
