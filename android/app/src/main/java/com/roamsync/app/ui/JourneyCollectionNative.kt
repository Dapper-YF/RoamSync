package com.roamsync.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.roamsync.app.data.text
import com.roamsync.app.data.remote.TripResponse
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.serialization.json.JsonObject

private data class JourneyGroup(val id: String, val title: String, val detail: String)

private val journeyGroups = listOf(
    JourneyGroup("drafts", "正在筹划", "日期可以以后再定。先把想去的地方和旅行要求安排好。"),
    JourneyGroup("upcoming", "即将出发", "查看已经确认的安排，核对出发前需要的信息。"),
    JourneyGroup("active", "正在旅行", "继续当前活动，查看下一站和实际进度。"),
    JourneyGroup("history", "历史旅行", "回看过去保留的日程。"),
)

@Composable
internal fun JourneyCollectionNative(
    tourism: TourismState,
    journey: RoamSyncUiState,
    section: String,
    onSectionChange: (String) -> Unit,
    onCreateDraft: () -> Unit,
    onOpenDraft: (String) -> Unit,
    onOpenTrip: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()
    val group = journeyGroups.firstOrNull { it.id == section } ?: journeyGroups.first()
    val matches: (String) -> Boolean = { value ->
        query.isBlank() || value.contains(query.trim(), ignoreCase = true)
    }
    val drafts = tourism.travelDrafts.filter { draft ->
        matches("${draft.text("title")} ${draft.text("city")} ${draft.text("requirements")}")
    }
    val tripsInSection = journey.trips.filter { trip ->
        tripPhase(trip, today) == section && matches("${trip.title} ${trip.destination} ${trip.startDate} ${trip.endDate}")
    }.sortedWith(
        if (section == "history") compareByDescending<TripResponse> { it.endDate }
        else compareBy<TripResponse> { it.startDate },
    )

    LazyColumn(
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("YOUR NEXT CHAPTER", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp)
                    Text("旅程，按你的节奏继续。", style = MaterialTheme.typography.headlineSmall, color = Ink)
                }
                OutlinedButton(onClick = onRefresh) { Text("刷新") }
            }
        }
        item {
            Button(onClick = onCreateDraft, modifier = Modifier.fillMaxWidth()) {
                Text("＋  筹划新旅行")
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                journeyGroups.forEach { option ->
                    val count = if (option.id == "drafts") tourism.travelDrafts.size
                    else journey.trips.count { tripPhase(it, today) == option.id }
                    FilterChip(
                        selected = section == option.id,
                        onClick = { onSectionChange(option.id) },
                        label = { Text("${option.title}  $count") },
                    )
                }
            }
        }
        item {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it.take(100) },
                placeholder = { Text("旅行名称、目的地或日期") },
                leadingIcon = { Text("⌕", color = DeepTeal, fontSize = 20.sp) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(group.title, style = MaterialTheme.typography.titleLarge, color = Ink)
                Text(group.detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
        }
        if (section == "drafts") {
            tourism.error?.let { error -> item { ErrorNotice(error, !tourism.busy, onRefresh) } }
            if (drafts.isEmpty() && !tourism.busy) {
                item {
                    QuietState(
                        "还没有旅行草稿",
                        "想先找个地方逛逛，可以去探索；确定要安排一趟旅行时，从这里开始筹划。",
                    )
                }
            }
            items(drafts, key = { it.text("id") }) { draft ->
                val cancelled = draft.text("status") == "cancelled"
                AppCard(modifier = Modifier.clickable { onOpenDraft(draft.text("id")) }) {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(draft.text("title").ifBlank { "未命名旅行" }, style = MaterialTheme.typography.titleLarge, color = Ink)
                            Text("${draft.text("city")} · ${draft.text("day_count")} 天 · 日期未定", color = DeepTeal, fontSize = 12.sp)
                        }
                        Text(if (cancelled) "可恢复" else "草稿", color = DeepTeal, fontSize = 11.sp)
                    }
                    Text(
                        draft.text("requirements").ifBlank { "继续整理想去的地方和旅行要求。" },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                    )
                    Text(if (cancelled) "查看和恢复  →" else "继续筹划  →", color = DeepTeal, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                }
            }
        } else {
            if (!journey.loaded && journey.busy) {
                item { QuietState("正在读取旅程", "正在从 RoamSync 服务读取已经保存的安排。") }
            }
            journey.error?.let { error ->
                item { ErrorNotice(error, !journey.busy, onRefresh) }
            }
            if (tripsInSection.isEmpty() && !journey.busy && journey.error == null) {
                item { QuietState("暂无${group.title}", "你保留的正式安排会显示在对应阶段。") }
            }
            items(tripsInSection, key = { it.id }) { trip ->
                AppCard(modifier = Modifier.clickable { onOpenTrip(trip.id) }) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(trip.title, style = MaterialTheme.typography.titleLarge, color = Ink)
                            Text(trip.destination.ifBlank { "目的地暂缺" }, color = DeepTeal, fontSize = 12.sp)
                        }
                        Text(group.title, color = DeepTeal, fontSize = 11.sp)
                    }
                    Text("${trip.startDate} — ${trip.endDate}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    Text(
                        when (section) {
                            "active" -> "继续今天的旅行  →"
                            "history" -> "回看日程  →"
                            else -> "查看出发安排  →"
                        },
                        color = DeepTeal,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 12.sp,
                    )
                }
            }
        }
        item { androidx.compose.foundation.layout.Spacer(Modifier.padding(bottom = 8.dp)) }
    }
}

@Composable
internal fun JourneyDraftCreationNative(
    s: TourismState,
    vm: TourismViewModel,
    onBack: () -> Unit,
) {
    var city by rememberSaveable { mutableStateOf(s.city) }
    var title by rememberSaveable { mutableStateOf("") }
    var days by rememberSaveable { mutableIntStateOf(3) }
    var requirements by rememberSaveable { mutableStateOf("") }

    LazyColumn(
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { TextButtonWithBack(onClick = onBack) }
        item { PageHeading("MAKE ROOM FOR IDEAS", "从一个旅行想法开始。", "日期可以以后再定。") }
        s.error?.let { error -> item { ErrorNotice(error, !s.busy, vm::retry) } }
        item {
            AppCard {
                OutlinedTextField(
                    value = city,
                    onValueChange = { city = it.take(100); vm.editCity(it.take(100)) },
                    label = { Text("想去哪里") },
                    placeholder = { Text("城市或目的地") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it.take(200) },
                    label = { Text("旅行名称") },
                    placeholder = { Text("可留空") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("大约几天", color = Ink, fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = { days = (days - 1).coerceAtLeast(1) }, enabled = days > 1) { Text("−") }
                    Text("$days 天", style = MaterialTheme.typography.titleMedium, color = Ink)
                    OutlinedButton(onClick = { days = (days + 1).coerceAtMost(14) }, enabled = days < 14) { Text("＋") }
                }
                OutlinedTextField(
                    value = requirements,
                    onValueChange = { requirements = it.take(3000) },
                    label = { Text("这次想怎么玩") },
                    placeholder = { Text("同行人、旅行节奏，或特别想去的地方") },
                    minLines = 3,
                    maxLines = 6,
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    onClick = { vm.editCity(city); vm.createDraft(title, days, requirements) },
                    enabled = !s.busy && city.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (s.busy) "正在创建…" else "开始筹划") }
            }
        }
    }
}

@Composable
private fun TextButtonWithBack(onClick: () -> Unit) {
    androidx.compose.material3.TextButton(onClick = onClick) {
        Text("‹  返回旅程", color = DeepTeal)
    }
}

private fun tripPhase(trip: TripResponse, today: String): String = when {
    trip.status in setOf("archived", "completed") || trip.endDate < today -> "history"
    trip.status == "active" || trip.startDate <= today -> "active"
    else -> "upcoming"
}
