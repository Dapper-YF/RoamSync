package com.roamsync.app.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.roamsync.app.data.*
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject

@Composable
internal fun DraftRequirementsNative(s: TourismState, vm: TourismViewModel, draftId: String, version: Int, disabled: Boolean) {
    val state = s.draftEffectiveRequirements
    var showHistory by rememberSaveable(draftId) { mutableStateOf(false) }
    var pendingId by rememberSaveable(draftId) { mutableStateOf("") }
    var pendingDay by rememberSaveable(draftId) { mutableIntStateOf(-1) }
    val records = state?.rows("records").orEmpty()
    val active = records.filter { it.text("status") == "active" }
    val effectiveDays = state?.obj("effective_by_day")?.mapNotNull { (day, value) ->
        val applies = (value as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
        day.toIntOrNull()?.let { index -> index to applies.map { it.text("id") }.toSet() }
    }?.toMap().orEmpty()
    AppCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("有效要求", style = MaterialTheme.typography.titleLarge, color = Ink)
            Text("${active.size} 条", color = DeepTeal, fontSize = 12.sp)
        }
        Text("来自你的明确表达，适用于草稿和后续规划。撤销一条要求不会直接改写活动。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        if (state == null) {
            Text("要求暂未读取。", color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedButton(onClick = vm::refreshDraftRequirements, enabled = !s.busy) { Text("读取已保存要求") }
        } else if (active.isEmpty()) {
            Text("还没有单独记录的有效要求。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            active.forEach { requirement ->
                val id = requirement.text("id")
                val days = effectiveDays.filterValues { id in it }.keys.sorted()
                Column(verticalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
                    Text(requirement.text("text"), color = Ink, fontWeight = FontWeight.SemiBold)
                    Text(
                        "${if (requirement.text("strength") == "hard") "明确要求" else "尽量满足"} · 适用${days.takeIf { it.isNotEmpty() }?.joinToString("、") { "第${it}天" } ?: "整个草稿"} · 用户明确表达",
                        color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp,
                    )
                    OutlinedButton(onClick = { pendingId = id; pendingDay = -1 }, enabled = !disabled && id.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("撤销整条要求") }
                    if (days.isNotEmpty()) {
                        Text("也可以只对某一天撤销：", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            days.forEach { day ->
                                OutlinedButton(onClick = { pendingId = id; pendingDay = day }, enabled = !disabled) { Text("仅第${day}天") }
                            }
                        }
                    }
                    HorizontalDivider(color = Mist)
                }
            }
        }
        val history = records.filter { it.text("status") != "active" }
        if (history.isNotEmpty()) {
            TextButton(onClick = { showHistory = !showHistory }) { Text(if (showHistory) "收起历史要求" else "查看已撤销或被覆盖的要求（${history.size}）") }
            if (showHistory) history.forEach { record ->
                Text("${record.text("text")} · ${if (record.text("status") == "revoked") "已撤销" else "已被覆盖"}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
        }
        if (state?.get("version") != null) Text("要求版本 ${state.text("version")} · 草稿版本 $version", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
    }
    if (pendingId.isNotBlank()) AlertDialog(
        onDismissRequest = { pendingId = ""; pendingDay = -1 },
        title = { Text("撤销这条要求？") },
        text = { Text(if (pendingDay < 0) "这条要求将在整个草稿范围内撤销。已生成的活动不会因此自动改变。" else "这条要求只会在第${pendingDay}天撤销，其他日期仍保留。已生成的活动不会因此自动改变。") },
        confirmButton = { TextButton(onClick = { val id = pendingId; val day = pendingDay.takeIf { it > 0 }; pendingId = ""; pendingDay = -1; vm.revokeDraftRequirement(id, day) }) { Text("确认撤销") } },
        dismissButton = { TextButton(onClick = { pendingId = ""; pendingDay = -1 }) { Text("返回") } },
    )
}
