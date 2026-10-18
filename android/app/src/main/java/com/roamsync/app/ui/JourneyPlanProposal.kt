package com.roamsync.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.math.BigDecimal
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

@Composable
internal fun JourneyPlanProposalCard(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    val run = s.run
    if (run == null) {
        Text("尚无候选方案。提交具体调整要求后，RoamSync 会生成可核对的方案。", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        val decided = run.status in setOf("accepted", "rejected")
        var showHistory by rememberSaveable(run.id) { mutableStateOf(false) }
        Text("${tripPlanStatus(run.status)} · ${run.user_request.take(100)}", fontWeight = FontWeight.SemiBold)
        if (decided) {
            Text(if (run.status == "accepted") "已确认保存，当前安排以上方正式日程为准。" else "已拒绝，原正式日程保留。", color = DeepTeal, fontSize = 12.sp)
            OutlinedButton(onClick = { showHistory = !showHistory }) { Text(if (showHistory) "收起方案记录" else "查看方案记录") }
        }
        if (!decided) run.response_text?.takeIf(String::isNotBlank)?.let { Text(it, fontSize = 13.sp, lineHeight = 20.sp) }
        run.pending_interrupt?.questions?.forEach { Text(it, fontSize = 13.sp) }
        if (run.status == "awaiting_clarification") {
            var answer by rememberSaveable(run.id) { mutableStateOf("") }
            OutlinedTextField(answer, { answer = it.take(3000) }, modifier = Modifier.fillMaxWidth(), label = { Text("补充旅行要求") }, minLines = 2)
            Button(onClick = { vm.answerTripPlanClarification(answer) }, enabled = !s.busy && answer.isNotBlank()) { Text("提交补充") }
        }
        run.error_message?.takeIf(String::isNotBlank)?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
        s.revision?.takeIf { !decided || showHistory }?.let { revision ->
            HorizontalDivider()
            if (!decided) Text(if (revision.proposed_snapshot.activities.isEmpty()) revision.reason else revision.proposed_snapshot.explanation.ifBlank { revision.reason }, fontSize = 13.sp, lineHeight = 20.sp)
            Text("${revision.proposed_snapshot.activities.size} 项安排 · ${revision.source_ids.size} 条参考来源", color = DeepTeal, fontSize = 11.sp)
            // Use the server's target_days to distinguish a cleared target day
            // from an omitted day which must retain its adopted schedule.
            val targetDates = (revision.planning_goals?.get("target_days") as? JsonArray).orEmpty()
                .mapNotNull { it.jsonPrimitive.contentOrNull }
            val changedDates = (targetDates + revision.proposed_snapshot.activities.map { it.day_date }).distinct().sorted()
            if (changedDates.isEmpty()) Text("候选未列出可核对的日期；请刷新并核对范围后再决定。", color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
            changedDates.forEach { date ->
                val current = s.days.firstOrNull { it.date == date }?.activities.orEmpty()
                val proposed = revision.proposed_snapshot.activities.filter { it.day_date == date }
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(date, color = Teal, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    Text("现在：${if (current.isEmpty()) "暂无安排" else current.joinToString("、") { "${it.scheduled_time.take(5)} ${it.display_name.ifBlank { it.name }}" }}", fontSize = 12.sp)
                    Text("候选：${if (proposed.isEmpty()) "暂无安排" else proposed.joinToString("、") { "${it.planned_start_time.take(5)} ${s.candidateNames[it.place_candidate_id] ?: "地点资料待加载"}" }}", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                    proposed.forEach { activity ->
                        Text("${activity.duration_minutes} 分钟 · ${proposalCost(activity.estimated_cost_fen)} 元", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (activity.reason.isNotBlank()) Text(activity.reason, fontSize = 11.sp, lineHeight = 17.sp)
                    }
                }
                HorizontalDivider()
            }
            val untouched = s.days.filterNot { it.date in changedDates }
            if (untouched.isNotEmpty()) Text("${untouched.joinToString("、") { it.date }}：本次候选未调整，保持原安排。", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (run.status == "awaiting_confirmation") {
                Text("候选不会自动改动正式行程。核对后再选择是否保存。", fontSize = 12.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = { vm.decideTripPlan(false) }, enabled = !s.busy && s.pendingDecision == null, modifier = Modifier.weight(1f)) { Text("保留原日程") }
                    Button(onClick = { vm.decideTripPlan(true) }, enabled = !s.busy && s.pendingDecision == null && changedDates.isNotEmpty(), modifier = Modifier.weight(1f)) { Text("确认采用调整") }
                }
            } else if (revision.status == "accepted") {
                Text("已保存；正式行程已重新读取。", color = DeepTeal, fontSize = 12.sp)
            } else if (revision.status == "rejected") {
                Text("已拒绝；原正式行程仍保留。", color = DeepTeal, fontSize = 12.sp)
            }
        }
        if (s.runs.size > 1) {
            Text("历史方案", fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
            s.runs.filterNot { it.id == run.id }.take(5).forEach { previous ->
                OutlinedButton(onClick = { vm.restoreRun(previous) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                    Text("${tripPlanStatus(previous.status)} · ${previous.user_request.take(55)}", maxLines = 2)
                }
            }
        }
    }
}

private fun proposalCost(fen: Long): String = BigDecimal.valueOf(fen, 2).stripTrailingZeros().toPlainString()
private fun tripPlanStatus(status: String): String = when (status) {
    "queued", "researching", "planning", "validating" -> "正在准备"
    "awaiting_confirmation" -> "待你确认"
    "accepted" -> "已保存"
    "rejected" -> "已拒绝"
    "failed" -> "未完成"
    "awaiting_clarification" -> "需要补充"
    else -> "方案状态：$status"
}
