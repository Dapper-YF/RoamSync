package com.roamsync.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.roamsync.app.data.remote.*
import com.roamsync.app.navigation.readForegroundLocation
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*

/** The one native detail for an adopted formal trip. It has no inner tab bar. */
@Composable
fun FormalJourneyNative(s: RoamSyncUiState, vm: RoamSyncViewModel, onAskAssistant: (String, Boolean) -> Unit) {
    val trip = s.trip ?: return
    val today = remember(trip.timezone) { LocalDate.now(ZoneId.of(trip.timezone)).toString() }
    val historical = today > trip.endDate || trip.status == "archived"
    val progress = s.executionProgress
    val recovery = progress?.recoveryPlanning
    LaunchedEffect(trip.id, recovery?.planningRunId, recovery?.status) {
        if (recovery?.status in setOf("queued", "researching", "planning", "validating")) {
            while (true) {
                delay(3000)
                vm.refresh()
            }
        }
    }
    val day = s.day
    val next = executionNextStop(progress, s.days, day?.id)
    val current = executionCurrentActivity(progress, s.days)
    LazyColumn(
        modifier = Modifier.fillMaxSize().imePadding(),
        contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(if (historical) "MEMORIES TO KEEP" else if (today >= trip.startDate) "MAKE TODAY YOURS" else "LOOKING FORWARD", color = Teal, fontSize = 11.sp, letterSpacing = 1.5.sp)
                Text(trip.title, style = MaterialTheme.typography.headlineMedium, color = Ink, fontWeight = FontWeight.SemiBold)
                Text("${trip.destination} · ${trip.startDate} — ${trip.endDate}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedButton(onClick = { onAskAssistant(if (historical) "帮我回顾这次旅行的安排。" else "结合当前日程和实际进度，下一步有什么建议？", false) }) {
                    Text("和 AI 聊聊")
                }
            }
        }
        s.error?.let { message -> item { ErrorNotice(message, !s.busy, vm::refresh) } }
        s.notice?.let { message -> item { AppCard(color = Mist) { Text(message, color = DeepTeal); TextButton(onClick = vm::clearNotice) { Text("收起") } } } }
        s.pendingDecision?.takeIf { it.tripId == trip.id }?.let { pending -> item { PendingDecisionCard(s, vm, pending) } }
        item { FormalRequirementsCard(s, vm, historical) }
        if (!historical) item { CurrentJourneyCard(s, vm, today, day, current, next) }
        if (!historical) progress?.experienceImpact?.takeIf { it.impactState in setOf("absorbed", "at_risk", "infeasible") }?.let { impact ->
            item { ExperienceImpactCard(impact) }
        }
        if (!historical && (recovery != null || progress?.activeDisruption != null || progress?.riskLevel == "eta_delayed")) {
            item { JourneyImpactCard(s, vm, onAskAssistant) }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (historical) "保留的旅行日程" else "已确认的日程", style = MaterialTheme.typography.titleLarge, color = Ink)
                Text(if (historical) "过去保存的活动、时间与路线。" else "候选调整只有在你明确采用后，才会替换这里的安排。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    s.days.forEachIndexed { index, item -> FilterChip(selected = item.id == day?.id, onClick = { vm.selectDay(item.id) }, label = { Text("第${index + 1}天 · ${item.date.takeLast(5)}") }) }
                }
            }
        }
        if (day == null) item { QuietState("暂时没有日程", "请刷新旅行，核对已保存的正式安排。") }
        else item { ConfirmedAgendaCard(s, vm, day) }
        if (!historical) {
            item { JourneyPreparationCard(s, onAskAssistant) }
            item { JourneyAdjustmentCard(s, vm) }
        }
    }
}

@Composable
private fun PendingDecisionCard(s: RoamSyncUiState, vm: RoamSyncViewModel, pending: PendingFormalDecision) {
    AppCard(color = Color(0xFFFFF2E5)) {
        Text(if (pending.confirmedOutcome == null) "上次决定结果待核对" else "决定已确认，正在同步正式日程", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text("上次选择：${if (pending.choice == "accept") "确认采用" else "保留原案"}。先读取服务端状态，避免重复提交。", fontSize = 13.sp)
        Button(onClick = vm::resolvePendingDecision, enabled = !s.busy) { Text(if (pending.confirmedOutcome == null) "查询决定结果" else "同步正式日程") }
        if (pending.verifiedAwaitingRetry && pending.confirmedOutcome == null) {
            Text("刚才读取到的候选仍在等待决定。若需要，可明确重试上次相同选择。", fontSize = 12.sp)
            OutlinedButton(onClick = vm::retryPendingDecision, enabled = !s.busy) { Text("确认重试原决定") }
        }
    }
}

@Composable
private fun ExperienceImpactCard(impact: ExperienceTimeImpact) {
    AppCard(color = if (impact.impactState == "absorbed") Mist else Color(0xFFFFF2E5)) {
        Text(when (impact.impactState) {
            "absorbed" -> "可用缓冲仍能容纳这次停留变化"
            "at_risk" -> "停留变化压缩了后续时间"
            else -> "按当前停留时间，后续安排难以完成"
        }, style = MaterialTheme.typography.titleLarge, color = Ink)
        Text(when (impact.impactState) {
            "absorbed" -> "后续活动仍可使用已有缓冲，已确认日程没有自动改动。"
            "at_risk" -> "后续活动时间较紧，请关注下一站及必要的调整选择。"
            else -> "需要核对后续活动与调整建议。采用新的安排仍由你明确确认。"
        }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        impact.timeShiftMinutes?.let { Text("实际停留带来的时间变化：$it 分钟", fontSize = 13.sp) }
        impact.minimumDownstreamSlackMinutes?.let { Text("后续最少可用缓冲：$it 分钟", fontSize = 13.sp) }
    }
}

@Composable
private fun FormalRequirementsCard(s: RoamSyncUiState, vm: RoamSyncViewModel, historical: Boolean) {
    val requirements = s.formalRequirements
    val records = (requirements?.get("records") as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
    val active = records.filter { it["status"]?.jsonPrimitive?.contentOrNull == "active" }
    val dates = ((requirements?.get("effective_by_date") as? JsonObject)?.keys ?: emptySet()).sorted()
    var expanded by rememberSaveable(s.trip?.id) { mutableStateOf(false) }
    var scope by rememberSaveable(s.trip?.id) { mutableStateOf("") }
    AppCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("有效要求", style = MaterialTheme.typography.titleLarge, color = Ink, modifier = Modifier.weight(1f))
            TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) "收起" else "查看（${active.size}）") }
        }
        s.formalRequirementsError?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 13.sp) }
        if (expanded) {
            Text("来自你的明确表达。建议、收藏和活动锁定各有独立作用。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            if (requirements == null) Text("尚未读取到有效要求。请刷新后核对。", fontSize = 13.sp)
            else {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = scope.isEmpty(), onClick = { scope = "" }, label = { Text("全部适用范围") })
                    dates.forEach { date -> FilterChip(selected = scope == date, onClick = { scope = date }, label = { Text(date) }) }
                }
                if (active.isEmpty()) Text("还没有单独记录的有效要求。", fontSize = 13.sp)
                active.forEach { record ->
                    val id = record["id"]?.jsonPrimitive?.contentOrNull.orEmpty()
                    val text = record["text"]?.jsonPrimitive?.contentOrNull.orEmpty()
                    val strength = record["strength"]?.jsonPrimitive?.contentOrNull
                    val byDate = requirements["effective_by_date"] as? JsonObject
                    val applies = dates.filter { date -> (byDate?.get(date) as? JsonArray).orEmpty().any { (it as? JsonObject)?.get("id")?.jsonPrimitive?.contentOrNull == id } }
                    HorizontalDivider(color = Color(0xFFE8E6DC))
                    Text(text, color = Ink, fontWeight = FontWeight.SemiBold)
                    Text("${if (strength == "hard") "明确硬要求，候选仍需核验" else "尽量满足"} · 适用：${applies.joinToString("、").ifBlank { "当前范围" }}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    if (!historical) OutlinedButton(onClick = { vm.revokeFormalRequirement(id, scope.ifBlank { null }) }, enabled = !s.busy && id.isNotBlank() && (scope.isEmpty() || scope in applies)) { Text("撤销这条要求") }
                }
                val inactive = records.filter { it["status"]?.jsonPrimitive?.contentOrNull != "active" }
                if (inactive.isNotEmpty()) {
                    Text("已撤销或被覆盖", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    inactive.forEach { Text("${it["text"]?.jsonPrimitive?.contentOrNull.orEmpty()} · ${if (it["status"]?.jsonPrimitive?.contentOrNull == "revoked") "已撤销" else "已被覆盖"}", fontSize = 12.sp) }
                }
            }
            TextButton(onClick = vm::refreshFormalRequirements, enabled = !s.busy) { Text("刷新有效要求") }
        }
    }
}

@Composable
private fun CurrentJourneyCard(s: RoamSyncUiState, vm: RoamSyncViewModel, today: String, selected: DayPlan?, current: PlanActivity?, next: PlanActivity?) {
    val execution = s.executionProgress?.execution
    val started = execution?.id != null
    val todayDay = s.days.firstOrNull { it.date == today }
    val startDay = todayDay ?: selected
    val status = current?.let { executionActivityStatus(s.executionProgress, it.id) }
    AppCard(color = Mist) {
        Text(when (execution?.status) {
            "completed" -> "本次旅行已结束"
            "paused" -> "旅行暂时停下来了"
            "in_progress" -> "此刻和下一站"
            else -> "准备好了，就开始今天的旅行"
        }, style = MaterialTheme.typography.titleLarge, color = Ink)
        if (!started) {
            Text("这里记录你主动确认的到达与完成。路线查询不代表实时导航。", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("${startDay?.date ?: today} · ${startDay?.activities?.size ?: 0} 个已确认安排", fontSize = 13.sp)
            Button(onClick = vm::startTodayExecution, enabled = !s.busy && startDay?.activities?.isNotEmpty() == true, modifier = Modifier.fillMaxWidth()) { Text("开始这一天的旅行") }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) { Text("现在", color = Teal, fontSize = 12.sp); Text(current?.display_name?.ifBlank { current.name } ?: "当前没有进行中的活动", fontWeight = FontWeight.SemiBold, color = Ink) }
                Text("→", color = Teal)
                Column(Modifier.weight(1f)) { Text("下一站", color = Teal, fontSize = 12.sp); Text(next?.display_name?.ifBlank { next.name } ?: "今天没有下一站", fontWeight = FontWeight.SemiBold, color = Ink) }
            }
            s.executionProgress?.currentActivityExperience?.takeIf { it.activityId == current?.id }?.let { experience ->
                Text("已体验 ${experience.elapsedExperienceMinutes ?: 0} 分钟 · 原计划 ${experience.plannedDurationMinutes} 分钟", fontSize = 13.sp)
                experience.projectedEndAt?.let { raw ->
                    val local = runCatching { Instant.parse(raw).atZone(ZoneId.of(s.trip?.timezone ?: "Asia/Shanghai")).format(DateTimeFormatter.ofPattern("HH:mm")) }.getOrElse { "时间待核对" }
                    Text("预计结束 $local", fontSize = 12.sp)
                }
            }
            Text("尚有 ${execution.remainingActivityCount} 项活动", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            if (execution.status == "paused") Button(onClick = { vm.executionAction("resume") }, enabled = !s.busy) { Text("继续旅行") }
            else if (execution.status == "in_progress") {
                when (status) {
                    "pending" -> Button(onClick = { vm.executionAction("arrive") }, enabled = !s.busy) { Text("我已到达") }
                    "arrived" -> Button(onClick = { vm.executionAction("start_activity") }, enabled = !s.busy) { Text("开始体验") }
                    "in_progress" -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { vm.executionAction("complete") }, enabled = !s.busy) { Text("完成这站") }
                        ExtendStayButton(s, vm)
                    }
                }
                if (execution.remainingActivityCount == 0) Button(onClick = { vm.executionAction("finish") }, enabled = !s.busy) { Text("结束本次旅行") }
                else OutlinedButton(onClick = { vm.executionAction("pause") }, enabled = !s.busy) { Text("暂停旅行") }
            }
        }
        next?.let { target -> NextStopRoute(s, vm, target) }
        s.locationObservation?.takeIf { it.targetActivityId == next?.id }?.let { observation -> LocationObservationCard(observation) }
        s.currentRoutePreview?.takeIf { it.targetActivityId == next?.id }?.let { preview ->
            Text("高德${if (preview.mode == "walk") "步行" else "驾车"}路线 · ${preview.route.distanceMeters}米 · 约${preview.route.durationSeconds / 60}分钟（供应商估算）", fontSize = 13.sp)
            CurrentLocationRouteMap(preview)
        }
        Text("到达、开始、延长与完成只按你的手动确认记录。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
    }
}

@Composable
private fun ExtendStayButton(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var show by rememberSaveable { mutableStateOf(false) }
    OutlinedButton(onClick = { show = true }, enabled = !s.busy) { Text("延长停留") }
    if (show) AlertDialog(onDismissRequest = { if (!s.busy) show = false }, title = { Text("延长当前停留") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("服务会重新评估后续安排；日程不会自动改动。")
            listOf(15, 30, 60).forEach { minutes -> OutlinedButton(onClick = { vm.extendCurrentStay(minutes); show = false }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("延长 $minutes 分钟") } }
        } }, confirmButton = {}, dismissButton = { TextButton(onClick = { show = false }) { Text("取消") } })
}

@Composable
private fun NextStopRoute(s: RoamSyncUiState, vm: RoamSyncViewModel, target: PlanActivity) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var locating by remember(target.id) { mutableStateOf(false) }
    var mode by remember(target.id) { mutableStateOf("walk") }
    val route: () -> Unit = {
        if (!locating) scope.launch {
            locating = true
            try { vm.previewRouteToNextStop(readForegroundLocation(context), mode) }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { vm.locationError(e.message ?: "无法获取当前位置") }
            finally { locating = false }
        }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        if (result[Manifest.permission.ACCESS_FINE_LOCATION] == true || result[Manifest.permission.ACCESS_COARSE_LOCATION] == true) route()
        else vm.locationError("未授予定位权限，未请求路线。")
    }
    HorizontalDivider(color = Color(0xFFD5DDD3))
    Text("前往下一站 · ${target.display_name.ifBlank { target.name }}", fontWeight = FontWeight.SemiBold)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("walk" to "步行", "driving" to "驾车").forEach { (value, label) -> FilterChip(selected = mode == value, onClick = { mode = value }, enabled = !s.busy && !locating, label = { Text(label) }) }
    }
    OutlinedButton(onClick = {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (fine || coarse) route() else permission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }, enabled = !s.busy && !locating) { Text(if (locating) "正在查询路线…" else "查询下一站路线") }
    Text("点击后仅读取一次前台位置；要求新于30秒、精度在100米内。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
}

@Composable
private fun LocationObservationCard(observation: ForegroundLocationObservation) {
    val time = runCatching { Instant.ofEpochMilli(observation.capturedAtEpochMillis).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("HH:mm:ss")) }.getOrDefault("时间未知")
    Text("定位：精度约${observation.accuracyMeters.toInt()}米 · $time · ${observation.provider.ifBlank { "系统" }}", color = DeepTeal, fontSize = 12.sp)
    Text(if (observation.routeStatus == "available") "路线查询成功" else if (observation.routeStatus == "unavailable") "定位成功，路线查询失败" else "路线查询中", fontSize = 12.sp)
}

@Composable
private fun JourneyImpactCard(s: RoamSyncUiState, vm: RoamSyncViewModel, onAskAssistant: (String, Boolean) -> Unit) {
    val progress = s.executionProgress ?: return
    val recovery = progress.recoveryPlanning
    AppCard(color = Color(0xFFFFF2E5)) {
        Text("接下来的安排可能受影响", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text(recovery?.reasonSummary ?: "当前进度可能影响后续活动，请核对安排。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        progress.minimumDownstreamSlackMinutes?.let { Text("后续最少可用缓冲 $it 分钟", fontSize = 13.sp) }
        if (recovery?.status in setOf("queued", "planning")) Text("正在准备调整建议；已确认日程保持原样。", color = DeepTeal)
        if (recovery?.status == "failed") Text("调整建议暂未生成；已确认日程保持原样。", color = MaterialTheme.colorScheme.error)
        TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("刷新调整状态") }
        recovery?.pendingRevision?.let { candidate ->
            val reason = candidate["reason"]?.jsonPrimitive?.contentOrNull
            if (!reason.isNullOrBlank()) Text(reason)
            val snapshot = candidate["proposed_snapshot"] as? JsonObject
            val changes = ((candidate["change_summary"] as? JsonObject)?.get("adjusted_activities") as? JsonArray).orEmpty()
            val activities = (snapshot?.get("activities") as? JsonArray).orEmpty()
            Text("建议的变化", fontWeight = FontWeight.SemiBold, color = Ink)
            snapshot?.get("explanation")?.jsonPrimitive?.contentOrNull?.let { Text(it, fontSize = 13.sp) }
            changes.forEach { element ->
                val change = element as? JsonObject ?: return@forEach
                val originalId = change["activity_id"]?.jsonPrimitive?.contentOrNull
                val name = change["name"]?.jsonPrimitive?.contentOrNull
                    ?: s.days.flatMap { it.activities }.find { it.id == originalId }?.let { it.display_name.ifBlank { it.name } }
                    ?: "名称待核对"
                val before = change["before_start_time"]?.jsonPrimitive?.contentOrNull.orEmpty().take(5)
                val after = change["after_start_time"]?.jsonPrimitive?.contentOrNull.orEmpty().take(5)
                val beforeDuration = change["before_duration_minutes"]?.jsonPrimitive?.intOrNull
                val afterDuration = change["after_duration_minutes"]?.jsonPrimitive?.intOrNull
                Text("$name：$before → $after${if (beforeDuration != null && afterDuration != null && beforeDuration != afterDuration) "，停留$beforeDuration → $afterDuration 分钟" else ""}", fontSize = 13.sp)
            }
            val proposedDates = activities.mapNotNull { (it as? JsonObject)?.get("day_date")?.jsonPrimitive?.contentOrNull }.distinct().sorted()
            proposedDates.forEach { date ->
                Text(date, fontWeight = FontWeight.SemiBold, color = Teal)
                Text("当前已确认", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                val before = s.days.firstOrNull { it.date == date }?.activities.orEmpty()
                if (before.isEmpty()) Text("尚无活动", fontSize = 12.sp)
                before.forEach { Text("${it.scheduled_time.take(5)} · ${it.display_name.ifBlank { it.name }} · ${it.duration_minutes}分钟", fontSize = 12.sp) }
                Text("候选安排", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                activities.mapNotNull { it as? JsonObject }.filter { it["day_date"]?.jsonPrimitive?.contentOrNull == date }.forEach { activity ->
                    val replacementId = activity["replaces_activity_id"]?.jsonPrimitive?.contentOrNull
                    val name = activity["place_name"]?.jsonPrimitive?.contentOrNull
                        ?: before.find { it.id == replacementId }?.let { it.display_name.ifBlank { it.name } }
                        ?: "地点名称暂不可读，请刷新后核对"
                    Text("${activity["planned_start_time"]?.jsonPrimitive?.contentOrNull.orEmpty().take(5)} · $name · ${activity["duration_minutes"]?.jsonPrimitive?.intOrNull ?: 0}分钟", fontSize = 12.sp)
                }
            }
            if (activities.isEmpty()) Text("候选未提供可核对活动，请刷新状态后再决定。", color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
            if (recovery.status == "awaiting_confirmation") Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val readable = activities.isNotEmpty() && activities.all { element ->
                    val activity = element as? JsonObject ?: return@all false
                    activity["place_name"]?.jsonPrimitive?.contentOrNull?.isNotBlank() == true ||
                        s.days.flatMap { it.activities }.any { it.id == activity["replaces_activity_id"]?.jsonPrimitive?.contentOrNull }
                }
                Button(onClick = { vm.decideRecovery(true) }, enabled = !s.busy && readable && s.pendingDecision == null, modifier = Modifier.weight(1f)) { Text("确认采用调整") }
                OutlinedButton(onClick = { vm.decideRecovery(false) }, enabled = !s.busy && s.pendingDecision == null, modifier = Modifier.weight(1f)) { Text("保留原日程") }
            }
        }
        TextButton(onClick = { onAskAssistant("解释当前旅行受到的实际影响，以及可以怎样选择。", false) }) { Text("请 AI 解释影响") }
    }
}

@Composable
private fun ConfirmedAgendaCard(s: RoamSyncUiState, vm: RoamSyncViewModel, day: DayPlan) {
    AppCard {
        Text(day.theme.ifBlank { day.label.ifBlank { day.date } }, style = MaterialTheme.typography.titleLarge, color = Ink)
        if (day.activities.isEmpty()) Text("这一天尚未采用活动方案。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        day.activities.forEachIndexed { index, activity ->
            if (index > 0) HorizontalDivider(color = Color(0xFFE9E7DF))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(activity.scheduled_time.take(5), color = Teal, fontWeight = FontWeight.Bold)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(activity.display_name.ifBlank { activity.name }, fontWeight = FontWeight.SemiBold, color = Ink)
                    val actual = executionActivityStatus(s.executionProgress, activity.id)
                    Text("停留${activity.duration_minutes}分钟 · 预计${formatFen(activity.estimated_cost_fen)}${if (activity.schedule_locked) " · 时间已锁定" else ""}${if (actual != null) " · ${executionStatusLabel(actual)}" else ""}", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    activity.note?.takeIf(String::isNotBlank)?.let { Text(it, fontSize = 13.sp) }
                }
            }
            day.route_legs.filter { it.from_activity_id == activity.id }.forEach { leg ->
                Text("前往下一站 · ${modeName(leg.mode)}${leg.duration_minutes}分钟 · ${"%.1f".format(leg.distance_meters / 1000.0)}公里${if (leg.is_estimated) "（估算）" else ""}", color = Teal, fontSize = 12.sp)
            }
        }
        day.conflicts.forEach { Text(it.message, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
        TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("刷新已确认日程") }
    }
}

@Composable
private fun JourneyPreparationCard(s: RoamSyncUiState, onAskAssistant: (String, Boolean) -> Unit) {
    val trip = s.trip
    AppCard(color = Color(0xFFF0F1E9)) {
        Text(if (trip != null && trip.startDate > LocalDate.now(ZoneId.of(trip.timezone)).toString()) "出发前核对" else "随身需要的信息", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text(trip?.accommodation?.takeIf { it.isNotBlank() }?.let { "住宿记录：$it" } ?: "尚未记录住宿，请在出发前自行确认。", fontSize = 13.sp)
        val budget = s.budget
        if (budget != null) Text("总预算 ${formatFen(budget.totalBudgetFen)} · 已消费 ${formatFen(budget.totalSpentFen)} · 剩余 ${formatFen(budget.totalRemainingFen)}", fontSize = 13.sp)
        Text("营业时间、门票和预约需再次核实；这里没有实时库存或预订确认。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        OutlinedButton(onClick = { onAskAssistant("结合这趟正式旅行，帮我检查出发前还需要准备什么。", false) }) { Text("聊聊出行准备") }
    }
}

@Composable
private fun JourneyAdjustmentCard(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var request by rememberSaveable(s.trip?.id) { mutableStateOf("") }
    var scoped by rememberSaveable(s.trip?.id) { mutableStateOf(false) }
    AppCard {
        Text("想调整已经确认的安排？", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text("写下具体要求，先生成候选方案。正式日程会保持原样，直到你明确确认采用。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(scoped, { scoped = it }, enabled = s.day != null)
            Text(if (scoped) "仅第${s.days.indexOfFirst { it.id == s.day?.id } + 1}天 · ${s.day?.date}" else "整段旅行", Modifier.padding(start = 10.dp))
        }
        OutlinedTextField(request, { request = it.take(3000) }, modifier = Modifier.fillMaxWidth(), label = { Text("希望怎样调整") }, minLines = 3, maxLines = 6)
        Button(onClick = { vm.requestTripPlan(request, scoped) }, enabled = !s.busy && s.pendingDecision == null && request.isNotBlank() && s.run?.working != true && s.run?.status != "awaiting_confirmation", modifier = Modifier.fillMaxWidth()) { Text("准备候选方案") }
        JourneyPlanProposalCard(s, vm)
        TextButton(onClick = vm::refreshTripPlan, enabled = !s.busy) { Text("刷新候选状态") }
    }
}

@Composable internal fun ErrorNotice(message: String, enabled: Boolean, retry: () -> Unit) {
    AppCard(color = MaterialTheme.colorScheme.errorContainer) {
        Text(message, color = MaterialTheme.colorScheme.onErrorContainer)
        TextButton(onClick = retry, enabled = enabled) { Text("重试") }
    }
}

private fun executionStatusLabel(status: String) = when (status) {
    "not_started" -> "尚未开始"; "in_progress" -> "正在体验"; "paused" -> "已暂停"; "completed" -> "已完成"; "pending" -> "待前往"; "arrived" -> "已到达"; "skipped" -> "已跳过"; else -> status
}

fun modeName(mode: String) = when (mode) { "transit" -> "公交"; "driving" -> "驾车"; else -> "步行" }
