package com.roamsync.app.ui

import android.app.DatePickerDialog
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.roamsync.app.navigation.NavigationLifecycle
import com.roamsync.app.navigation.DelayScenario
import com.roamsync.app.R
import com.roamsync.app.data.remote.*
import java.time.LocalDate
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.serialization.json.*

private val Navy = Color(0xFF11243F)
private val Teal = Color(0xFF218F84)
private val Mint = Color(0xFFD9EFEA)

@Composable
fun MobileApp(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    BackHandler(s.screen != AppScreen.TRIPS) { vm.back() }
    val snack = remember { SnackbarHostState() }
    LaunchedEffect(s.notice) { s.notice?.let { snack.showSnackbar(it); vm.clearNotice() } }
    Scaffold(
        snackbarHost = { SnackbarHost(snack) },
        topBar = { Column(Modifier.statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                if (s.screen != AppScreen.TRIPS) TextButton(onClick = vm::back, enabled = !s.busy || s.screen == AppScreen.ASSISTANT) { Text("‹ 返回") }
                else Image(painterResource(R.drawable.roamsync_launcher), "RoamSync", Modifier.size(38.dp).clip(RoundedCornerShape(13.dp)))
                Column(Modifier.weight(1f).padding(start = 10.dp)) {
                    Text(when (s.screen) { AppScreen.TRIPS -> "RoamSync"; AppScreen.ASSISTANT -> "旅程总管"; AppScreen.CREATE -> "创建旅行"; AppScreen.NAVIGATION -> "行程执行"; else -> s.trip?.destination.orEmpty() }, fontWeight = FontWeight.Bold, fontSize = 19.sp)
                    if (s.screen == AppScreen.ASSISTANT) Text(s.trip?.title ?: "一起计划下一次出发", fontSize = 11.sp, color = Teal, maxLines = 1)
                }
                TextButton(onClick = vm::refresh, enabled = !s.busy) { Text("刷新") }
            }
            if (s.busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Teal)
        } },
        bottomBar = {
            if (s.screen == AppScreen.DETAIL) NavigationBar(containerColor = Color.White) {
                listOf("行程", "地图", "预算", "总管").forEachIndexed { index, label ->
                    NavigationBarItem(selected = s.tab == index, onClick = { if (index == 3) vm.openAssistant() else vm.selectTab(index) },
                        enabled = !s.busy, icon = { NavGlyph(index) }, label = { Text(label) })
                }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            s.error?.let { ErrorNotice(it, !s.busy, vm::refresh) }
            when (s.screen) {
                AppScreen.TRIPS -> TripsHome(s, vm)
                AppScreen.DETAIL -> TripDetail(s, vm)
                AppScreen.ASSISTANT -> AssistantScreen(s, vm)
                AppScreen.CREATE -> CreateTripScreen(s, vm)
                AppScreen.NAVIGATION -> NavigationExecutionScreen(s, vm)
            }
        }
    }
}

@Composable private fun NavGlyph(index: Int) {
    Canvas(Modifier.size(23.dp)) {
        val c = Navy; val w = size.width; val h = size.height; val stroke = 1.8.dp.toPx()
        when (index) {
            0 -> { for (i in 0..2) { val y = h * (.25f + i * .25f); drawCircle(c, stroke, androidx.compose.ui.geometry.Offset(w*.15f,y)); drawLine(c, androidx.compose.ui.geometry.Offset(w*.35f,y), androidx.compose.ui.geometry.Offset(w*.9f,y),stroke) } }
            1 -> { drawCircle(c,w*.33f,androidx.compose.ui.geometry.Offset(w*.5f,h*.4f),style=androidx.compose.ui.graphics.drawscope.Stroke(stroke)); drawLine(c,androidx.compose.ui.geometry.Offset(w*.25f,h*.62f),androidx.compose.ui.geometry.Offset(w*.5f,h*.95f),stroke); drawLine(c,androidx.compose.ui.geometry.Offset(w*.75f,h*.62f),androidx.compose.ui.geometry.Offset(w*.5f,h*.95f),stroke) }
            2 -> { drawRoundRect(c,topLeft=androidx.compose.ui.geometry.Offset(w*.1f,h*.2f),size=androidx.compose.ui.geometry.Size(w*.8f,h*.6f),cornerRadius=androidx.compose.ui.geometry.CornerRadius(4f,4f),style=androidx.compose.ui.graphics.drawscope.Stroke(stroke)); drawLine(c,androidx.compose.ui.geometry.Offset(w*.55f,h*.5f),androidx.compose.ui.geometry.Offset(w*.9f,h*.5f),stroke) }
            else -> { drawCircle(c,w*.43f,style=androidx.compose.ui.graphics.drawscope.Stroke(stroke)); drawLine(c,androidx.compose.ui.geometry.Offset(w*.3f,h*.7f),androidx.compose.ui.geometry.Offset(w*.7f,h*.3f),stroke*1.6f) }
        }
    }
}
@Composable private fun ErrorNotice(message: String, enabled: Boolean, retry: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.errorContainer, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth().padding(12.dp)) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(message, Modifier.weight(1f), fontSize = 13.sp)
            TextButton(onClick = retry, enabled = enabled) { Text("重试") }
        }
    }
}
@Composable private fun Panel(modifier: Modifier = Modifier, color: Color = Color.White, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(24.dp), color = color) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}
private fun tripStatus(trip: TripResponse): String = when {
    trip.status == "archived" -> "已归档"
    LocalDate.now(java.time.ZoneId.of(trip.timezone)).isAfter(LocalDate.parse(trip.endDate)) -> "已结束"
    LocalDate.now(java.time.ZoneId.of(trip.timezone)).isBefore(LocalDate.parse(trip.startDate)) -> "即将出发"
    else -> "旅行中"
}
@Composable private fun Pill(text: String) { Surface(shape = CircleShape, color = Mint) { Text(text, Modifier.padding(horizontal = 12.dp, vertical = 6.dp), color = Color(0xFF135A52), fontSize = 11.sp) } }

@Composable private fun TripsHome(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var filter by rememberSaveable { mutableStateOf("全部") }
    LazyColumn(Modifier.imePadding(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        item { Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(30.dp)).background(Brush.linearGradient(listOf(Navy, Color(0xFF1C625C)))).padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("YOUR NEXT CHAPTER", color = Mint, fontSize = 11.sp, letterSpacing = 2.sp)
            Text("下一站，\n去你想去的地方。", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 29.sp, lineHeight = 40.sp)
            Text("告诉旅程总管你的想法，\n把灵感变成一趟好旅行。", color = Mint, fontSize = 14.sp, lineHeight = 22.sp)
            Button(onClick = { vm.openAssistant() }, enabled = !s.busy, colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Navy), contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp)) { Text("和 AI 计划旅行  ↗", fontWeight = FontWeight.Bold) }
        } }
        item { Row(verticalAlignment = Alignment.CenterVertically) { Text("我的旅行", Modifier.weight(1f), fontSize = 22.sp, fontWeight = FontWeight.Bold); TextButton(onClick = vm::createScreen, enabled = !s.busy) { Text("＋ 手动创建") } } }
        item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf("全部", "即将出发", "旅行中", "已结束").forEach { label -> FilterChip(selected = filter == label, onClick = { filter = label }, label = { Text(label) }, shape = CircleShape) } } }
        val trips = s.trips.filter { it.status != "archived" && (filter == "全部" || tripStatus(it) == filter) }
        if (trips.isEmpty() && s.loaded) item { Panel { Text("还没有${if (filter == "全部") "" else filter}的旅行", fontWeight = FontWeight.Bold); Text("可以从一个目的地、一段假期，或一次与 AI 的对话开始。", color = MaterialTheme.colorScheme.secondary) } }
        items(trips, key = { it.id }) { trip -> Panel(Modifier.clickable(enabled = !s.busy) { vm.openTrip(trip.id) }) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(trip.destination.ifBlank { "旅行" }, color = Teal, fontSize = 13.sp); Pill(tripStatus(trip)) }
            Text(trip.title, fontSize = 21.sp, fontWeight = FontWeight.Bold)
            Text("${trip.startDate} — ${trip.endDate}", fontSize = 13.sp, color = MaterialTheme.colorScheme.secondary)
            HorizontalDivider(color = Mint.copy(alpha = .6f))
            Row { Text("预算 ${formatFen(trip.totalBudgetFen)}", Modifier.weight(1f), fontSize = 13.sp); Text("查看行程  →", color = Teal, fontSize = 13.sp) }
        } }
    }
}

@Composable private fun TripDetail(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    val trip = s.trip ?: return
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) { Text(trip.title, Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 24.sp); Pill(tripStatus(trip)) }
            Text("${trip.startDate} — ${trip.endDate}", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
            val live = s.executionProgress?.navigationSession ?: s.navigationStart?.navigationSession
            Button(onClick = vm::startNavigation, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                Text(if (live != null) "继续执行导航" else "开始执行导航")
            }
            if (s.tab != 2) Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                s.days.forEachIndexed { i, day -> FilterChip(selected = day.id == s.day?.id, onClick = { vm.selectDay(day.id) }, label = { Text("第 ${i+1} 天 · ${day.date.takeLast(5)}") }, shape = RoundedCornerShape(14.dp)) }
            }
        }
        when (s.tab) { 1 -> RouteMap(s, vm); 2 -> BudgetScreen(s, vm); else -> Itinerary(s, vm) }
    }
}
@Composable private fun Itinerary(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var editing by remember { mutableStateOf<PlanActivity?>(null) }
    val day = s.day
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Panel(color = Mint.copy(alpha = .6f)) {
            Text(day?.theme?.ifBlank { "留一点空间，遇见惊喜" } ?: "这趟旅行，等你来安排", fontWeight = FontWeight.Bold)
            Text("${day?.activities?.size ?: 0} 个安排 · 预计 ${formatFen(day?.activities?.sumOf { it.estimated_cost_fen } ?: 0)}", fontSize = 13.sp)
            TextButton(onClick = { vm.openAssistant(if (day?.activities.isNullOrEmpty()) "请根据我的旅行日期、预算和偏好生成完整行程。" else "现在的旅行行程是怎样的，你建议我怎么去这一趟？") }, enabled = !s.busy) { Text("问问旅程总管  ↗") }
        } }
        day?.conflicts?.forEach { conflict -> item { Text(conflict.message, color = MaterialTheme.colorScheme.error, fontSize = 13.sp) } }
        if (day?.activities.isNullOrEmpty()) item { Panel { Text("今天还没有安排", fontSize = 20.sp, fontWeight = FontWeight.Bold); Text("告诉 AI 想去哪里、想怎样度过一天，它会先给出候选方案。", fontSize = 14.sp, lineHeight = 23.sp); Button(onClick = { vm.openAssistant("我想丰富这一天的行程，请给出适合我的建议并说明理由。", true) }, enabled = !s.busy) { Text("一起安排这一天") } } }
        items(day?.activities.orEmpty(), key = { it.id }) { a ->
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Panel(Modifier.clickable(enabled = !s.busy) { editing = a }) {
                    Row { Pill(a.scheduled_time.take(5)); Spacer(Modifier.weight(1f)); Text("${a.duration_minutes} 分钟", fontSize = 12.sp, color = Teal) }
                    Text(a.display_name.ifBlank { a.name }, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(a.neighborhood.ifBlank { "行程地点" }, color = MaterialTheme.colorScheme.secondary, fontSize = 13.sp)
                    if (!a.note.isNullOrBlank()) Text(a.note, fontSize = 14.sp, lineHeight = 22.sp)
                    Row { Text(formatFen(a.estimated_cost_fen), Modifier.weight(1f), fontWeight = FontWeight.Medium); Text(if (a.schedule_locked) "时间已锁定 · 编辑" else "编辑安排  ↗", fontSize = 12.sp, color = Teal) }
                }
                day?.route_legs?.find { it.from_activity_id == a.id }?.let { leg -> Text("↓  ${modeName(leg.mode)} ${leg.duration_minutes} 分钟 · ${"%.1f".format(leg.distance_meters / 1000.0)} km${if (leg.is_estimated) "（估算）" else ""}", Modifier.padding(start = 20.dp), fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary) }
            }
        }
        if (!day?.activities.isNullOrEmpty()) item { OutlinedButton(onClick = { vm.openAssistant("请调整${day?.date}的行程，节奏轻松一点，并说明调整理由。", true) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("让这一天轻松一点") } }
    }
    editing?.let { a -> ActivityEditor(a, s, vm) { editing = null } }
}
fun modeName(mode: String) = when (mode) { "transit" -> "公交"; "driving" -> "驾车"; else -> "步行" }


@Composable private fun NavigationExecutionScreen(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    val nav = s.executionProgress?.navigationSession ?: s.navigationStart?.navigationSession ?: return
    val runtime = s.navigationRuntime
    Column(Modifier.fillMaxSize()) {
        if (runtime.lifecycle in setOf(NavigationLifecycle.ROUTE_READY, NavigationLifecycle.NAVIGATING, NavigationLifecycle.REROUTING, NavigationLifecycle.ARRIVED)) {
            key(nav.id) { AndroidView(factory = { vm.navigationView() ?: android.view.View(it) }, modifier = Modifier.fillMaxWidth().weight(1f), onRelease = { vm.releaseNavigationView() }) }
        } else Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) { Text(when (runtime.lifecycle) { NavigationLifecycle.PRIVACY_REQUIRED -> "需要先同意高德导航隐私说明"; NavigationLifecycle.STOPPED -> "导航已停止"; else -> runtime.error ?: "准备导航引擎…" }) }
        val presentation = selectExecutionPresentation(s.executionProgress, s.serverNavigation.syncDelayed || s.executionStateSyncDelayed)
        LazyColumn(Modifier.heightIn(max = 390.dp), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { ExecutionStatusCard(presentation, nav, runtime) }
            presentation.disruption?.let { disruption -> item { DisruptionCard(disruption, presentation.slack) } }
            presentation.recovery?.let { recovery -> item { RecoveryPlanningCard(recovery) } }
            if (presentation.syncDelayed) item { SyncDelayedCard() }
            if (shouldShowDebugDelayControls(com.roamsync.app.BuildConfig.DEBUG)) item { DebugDelayControls(s, vm) }
            item {
                when (runtime.lifecycle) {
                    NavigationLifecycle.PRIVACY_REQUIRED -> Button(onClick = vm::acceptAmapPrivacy, enabled = !s.busy) { Text("我已阅读并同意高德导航隐私说明") }
                    NavigationLifecycle.ROUTE_READY -> Button(onClick = vm::startSimulation, enabled = !s.busy) { Text("开始模拟导航") }
                    NavigationLifecycle.ARRIVED -> Text("已到达当前目的地。此阶段不会自动推进正式行程。", color = Teal)
                    NavigationLifecycle.FAILED -> OutlinedButton(onClick = vm::acceptAmapPrivacy, enabled = !s.busy) { Text("重试路线规划") }
                    else -> Unit
                }
            }
            item { OutlinedButton(onClick = vm::cancelNavigation, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("结束导航") } }
        }
    }
}

@Composable private fun ExecutionStatusCard(p: ExecutionPresentation, nav: NavigationSession, runtime: com.roamsync.app.navigation.NavigationRuntimeState) {
    val color = when (p.tone) { ExecutionTone.NORMAL -> Color(0xFFE5F5EE); ExecutionTone.WARNING -> Color(0xFFFFF4D7); ExecutionTone.DISRUPTION -> Color(0xFFFFE9E5); ExecutionTone.UNKNOWN -> Color(0xFFF0F3F6) }
    Panel(color = color) {
        Text(p.headline, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = Navy)
        Text(p.detail, fontSize = 13.sp, lineHeight = 20.sp)
        p.targetName?.let { Text("当前目的地：$it", fontWeight = FontWeight.Medium) }
        val eta = nav.currentEta ?: runtime.etaEpochMillis?.let { Instant.ofEpochMilli(it).toString() }
        eta?.let { Text("预计到达：${displayInstant(it)}", fontSize = 13.sp) }
        val distance = nav.remainingDistanceMeters ?: runtime.remainingDistanceMeters
        val duration = nav.remainingDurationSeconds ?: runtime.remainingDurationSeconds
        if (distance != null || duration != null) Text("当前剩余：${distance?.let { "%.1f km".format(it / 1000.0) } ?: "--"}${duration?.let { " · ${it / 60} min" } ?: ""}", fontSize = 13.sp)
        p.slack?.let { Text("行程时间余量：${it.valueText} · ${it.explanation}", color = if (it.value < 0) MaterialTheme.colorScheme.error else Teal, fontWeight = FontWeight.Medium) }
    }
}

@Composable private fun DisruptionCard(disruption: DisruptionPresentation, slack: SlackPresentation?) {
    Panel(color = Color(0xFFFFE9E5)) {
        Text(disruption.headline, fontWeight = FontWeight.Bold, fontSize = 19.sp, color = MaterialTheme.colorScheme.error)
        Text(disruption.explanation, fontSize = 13.sp, lineHeight = 20.sp)
        disruption.impactedActivity?.let { activity -> Text("受影响活动：${activity.scheduledTime?.take(5)?.let { "$it " }.orEmpty()}${activity.name}", fontWeight = FontWeight.Medium) }
        slack?.let { Text("行程时间余量：${it.valueText} · ${it.explanation}", color = MaterialTheme.colorScheme.error) }
        Text("首次发现：${displayInstant(disruption.firstDetectedAt)}", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
        Text("最近确认：${displayInstant(disruption.lastSeenAt)}", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary)
    }
}

@Composable private fun RecoveryPlanningCard(recovery: RecoveryPresentation) {
    Panel(color = if (recovery.isFailure) Color(0xFFF5ECEB) else Mint.copy(alpha = .72f)) {
        Text(recovery.headline, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = if (recovery.isFailure) MaterialTheme.colorScheme.error else Navy)
        recovery.detail?.let { Text(it, fontSize = 13.sp, lineHeight = 20.sp) }
    }
}

@Composable private fun SyncDelayedCard() = Panel(color = Color(0xFFF0F3F6)) {
    Text("行程状态同步延迟", fontWeight = FontWeight.Bold)
    Text("高德导航仍在继续。当前展示的是上一次成功同步的 RoamSync 行程状态。", fontSize = 13.sp, lineHeight = 20.sp)
}

@Composable private fun DebugDelayControls(s: RoamSyncUiState, vm: RoamSyncViewModel) = Panel(color = Color(0xFFF2FAF8)) {
    Text(if (s.delayScenario.minutes == 0) "开发模拟延误：正常" else "开发模拟延误：+${s.delayScenario.minutes} min", fontSize = 12.sp, color = Teal)
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf(DelayScenario.NORMAL, DelayScenario.MINOR, DelayScenario.MAJOR).forEach { scenario -> OutlinedButton(onClick = { vm.selectDelayScenario(scenario) }) { Text(scenario.label) } }
    }
}

private fun displayInstant(value: String): String = runCatching {
    Instant.parse(value).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("HH:mm"))
}.getOrElse { value.replace("T", " ").take(16) }

@Composable private fun ActivityEditor(a: PlanActivity, s: RoamSyncUiState, vm: RoamSyncViewModel, close: () -> Unit) {
    var time by remember(a.id) { mutableStateOf(a.scheduled_time.take(5)) }
    var duration by remember(a.id) { mutableStateOf(a.duration_minutes.toString()) }
    var cost by remember(a.id) { mutableStateOf(java.math.BigDecimal.valueOf(a.estimated_cost_fen, 2).toPlainString()) }
    var note by remember(a.id) { mutableStateOf(a.note.orEmpty()) }
    var locked by remember(a.id) { mutableStateOf(a.schedule_locked) }
    LaunchedEffect(s.notice) { if (s.notice == "活动已更新") close() }
    AlertDialog(onDismissRequest = { if (!s.busy) close() }, title = { Text(a.display_name.ifBlank { a.name }) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            s.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Field(time, { time = it }, "开始时间 HH:mm")
            Field(duration, { duration = it }, "停留分钟", KeyboardType.Number)
            Field(cost, { cost = it }, "预计费用（元）", KeyboardType.Decimal)
            Field(note, { note = it.take(1000) }, "备注")
            Row(verticalAlignment = Alignment.CenterVertically) { Switch(locked, { locked = it }); Text("锁定时间", Modifier.padding(start = 12.dp)) }
        } }, confirmButton = { Button(onClick = { vm.updateActivity(a, time, duration, cost, note, locked) }, enabled = !s.busy) { Text("保存修改") } }, dismissButton = { TextButton(onClick = close, enabled = !s.busy) { Text("取消") } })
}

@Composable private fun BudgetScreen(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var amount by rememberSaveable { mutableStateOf("") }; var note by rememberSaveable { mutableStateOf("") }; var category by rememberSaveable { mutableStateOf("food") }
    val budget = s.budget ?: return
    LaunchedEffect(s.notice) { if (s.notice == "记账成功") { amount = ""; note = "" } }
    LazyColumn(Modifier.imePadding(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        item { Panel(color = Navy) {
            Text("旅行总预算", color = Mint, fontSize = 13.sp)
            Text(formatFen(budget.totalBudgetFen), color = Color.White, fontSize = 34.sp, fontWeight = FontWeight.Bold)
            Text("已消费 ${formatFen(budget.totalSpentFen)}  ·  剩余 ${formatFen(budget.totalRemainingFen)}", color = Mint, fontSize = 13.sp)
            LinearProgressIndicator(progress = { (budget.totalSpentFen.toFloat() / budget.totalBudgetFen.coerceAtLeast(1)).coerceIn(0f,1f) }, modifier = Modifier.fillMaxWidth(), color = Teal, trackColor = Color.White.copy(alpha = .15f))
        } }
        item { Panel { Text("计划与实际", fontWeight = FontWeight.Bold, fontSize = 19.sp); Text("行程预计费用  ${formatFen(s.days.sumOf { d -> d.activities.sumOf { it.estimated_cost_fen } })}"); Text("今日已消费  ${formatFen(budget.todaySpentFen)}"); Text("预计费用来自行程安排；实际消费只统计你保存的账单。", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary) } }
        item { Panel {
            Text("记一笔", fontWeight = FontWeight.Bold, fontSize = 20.sp)
            Field(amount, { amount = it }, "金额（元）", KeyboardType.Decimal)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("food" to "餐饮", "transport" to "交通", "ticket" to "门票", "lodging" to "住宿", "shopping" to "购物", "other" to "其他").forEach { (key,label) -> FilterChip(selected = category == key, onClick = { category = key }, label = { Text(label) }, shape = CircleShape) }
            }
            Field(note, { note = it.take(500) }, "消费说明")
            Button(onClick = { vm.addExpense(amount, category, note) }, enabled = !s.busy && amount.isNotBlank() && note.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("保存账单") }
        } }
        item { TextButton(onClick = { vm.openAssistant("帮我分析当前旅行预算，哪些安排可以省钱？请先给建议并解释原因。") }, enabled = !s.busy) { Text("请旅程总管帮我看看预算  ↗") } }
    }
}

@Composable private fun AssistantScreen(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    val scroll = rememberLazyListState()
    var history by rememberSaveable { mutableStateOf(false) }
    var input by remember { mutableStateOf(TextFieldValue(s.draft)) }
    LaunchedEffect(s.draft) { if (s.draft != input.text) input = TextFieldValue(s.draft, TextRange(s.draft.length)) }
    LaunchedEffect(s.session?.messages?.size, s.run?.status, s.revision?.id) { if (scroll.layoutInfo.totalItemsCount > 0) scroll.animateScrollToItem(scroll.layoutInfo.totalItemsCount - 1) }
    Column(Modifier.fillMaxSize().imePadding()) {
        LazyColumn(Modifier.weight(1f), state = scroll, contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            item { Panel(color = Mint.copy(alpha = .7f)) {
                Text(if (s.trip == null) "从一个想法开始。" else "这趟旅行，我们一起安排。", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                Text(if (s.scopedDay) "正在讨论 ${s.day?.date}。可以提问、比较选择或调整安排。" else "问行程、聊建议，或规划下一次出发。需要修改时，我会先解释方案，等你确认后保存。", fontSize = 14.sp, lineHeight = 23.sp)
            } }
            if (s.runs.size > 1) item { TextButton(onClick = { history = !history }) { Text(if (history) "收起历史方案" else "查看历史方案（${s.runs.size}）") } }
            if (history) items(s.runs.filter { it.id != s.run?.id }, key = { "history-${it.id}" }) { run -> OutlinedButton(onClick = { vm.restoreRun(run) }, enabled = !s.busy && s.run?.working != true) { Text(run.user_request, maxLines = 2) } }
            items(s.session?.messages.orEmpty(), key = { it.id }) { message ->
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Bubble(message.user, true)
                    Bubble(s.runs.find { it.id == message.run_id && it.status == "answered" }?.response_text ?: message.assistant, false)
                }
            }
            s.session?.pending_action?.let { action -> item { Panel(color = Color(0xFFF0F8F4)) {
                Pill("待确认 · ${if (action.tool == "reschedule_trip") "旅行改期" else "创建旅行"}")
                Text(action.title, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text(action.summary, lineHeight = 23.sp)
                Text("${action.city.name} · ${action.start_date} — ${action.end_date}")
                Text("总预算 ${formatFen(action.total_budget_fen)} · 每日 ${formatFen(action.daily_budget_fen)}")
                action.source_title?.let { Text("参考旅行：$it", fontSize = 13.sp) }
                if (action.preferences.isNotBlank()) Text(action.preferences, fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { vm.decideAction(false) }, enabled = !s.busy) { Text("暂不执行") }
                    Button(onClick = { vm.decideAction(true) }, enabled = !s.busy) { Text(if (action.tool == "reschedule_trip") "确认改期" else "确认创建") }
                }
            } } }
            val run = s.run
            if (run != null && s.session?.messages?.none { it.run_id == run.id } != false) item { Bubble(run.user_request, true); if (run.status == "answered") Bubble(run.response_text.orEmpty(), false) }
            if (run?.working == true || s.busy) item { Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) { CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp); Text(if (run?.working == true) "正在查阅行程、准备建议…" else "正在处理…", fontSize = 13.sp) } }
            if (run?.status == "awaiting_clarification") item { Panel { Text("还需要确认一点", fontWeight = FontWeight.Bold); run.pending_interrupt?.questions?.forEach { Text(it, lineHeight = 23.sp) }; Text("在下方补充信息即可继续。", color = Teal, fontSize = 13.sp) } }
            if (run?.status == "failed") item { Panel { Text("这次需求没有处理完成", fontWeight = FontWeight.Bold); Text(planningError(run.error_message)); OutlinedButton(onClick = { vm.editDraft(run.user_request) }, enabled = !s.busy) { Text("重新编辑需求") } } }
            s.revision?.let { revision -> item { Panel(color = Color(0xFFF0F8F4)) {
                Pill(when (revision.status) { "accepted" -> "已保存"; "rejected" -> "未采用"; else -> "候选方案 · 待确认" })
                Text("为什么这样安排", fontSize = 19.sp, fontWeight = FontWeight.Bold)
                Text(revision.proposed_snapshot.explanation.ifBlank { revision.reason }, lineHeight = 24.sp)
                Text("${revision.proposed_snapshot.activities.size} 个活动 · ${revision.source_ids.size} 条参考来源", fontSize = 12.sp, color = Teal)
                revision.proposed_snapshot.activities.forEach { a ->
                    HorizontalDivider(color = Mint)
                    Text("${a.day_date.takeLast(5)}  ${a.planned_start_time.take(5)}", color = Teal, fontSize = 12.sp)
                    Text(s.candidateNames[a.place_candidate_id] ?: s.days.flatMap { it.activities }.find { it.place_id == a.place_candidate_id }?.name ?: "地点资料待加载", fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text("${a.duration_minutes} 分钟 · ${formatFen(a.estimated_cost_fen)}", fontSize = 12.sp)
                    if (a.reason.isNotBlank()) Text(a.reason, fontSize = 13.sp, lineHeight = 21.sp)
                }
                if (run?.status == "awaiting_confirmation") {
                    Text("确认后会更新正式行程；你也可以继续提问或修改需求。", fontSize = 12.sp, color = Teal)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { vm.decidePlan(false) }, enabled = !s.busy) { Text("暂不采用") }
                        Button(onClick = { vm.decidePlan(true) }, enabled = !s.busy) { Text("保存到正式行程") }
                    }
                }
                if (revision.status == "accepted") Button(onClick = vm::back, enabled = !s.busy) { Text("查看正式行程  →") }
            } } }
        }
        Surface(color = Color.White, shadowElevation = 12.dp) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (s.session?.messages.isNullOrEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    (if (s.trip == null) listOf("帮我规划一趟周末旅行", "参考之前的旅行安排新的出行") else listOf("现在的行程怎么样？", "我希望这次旅行丰富一些", "我想把旅行改到未来的日期")).forEach { text -> SuggestionChip(onClick = { vm.editDraft(text) }, label = { Text(text, fontSize = 12.sp) }, shape = CircleShape) }
                }
                OutlinedTextField(value = input, onValueChange = { input = it; vm.editDraft(it.text) }, modifier = Modifier.fillMaxWidth().onPreviewKeyEvent {
                    if (it.key == Key.Enter && !it.isShiftPressed && input.composition == null && it.type == KeyEventType.KeyDown) { if (it.nativeKeyEvent.repeatCount == 0) vm.send(); true } else false
                }, placeholder = { Text(if (s.run?.status == "awaiting_clarification") "补充信息，继续讨论…" else "想了解什么，或想怎样调整？") }, shape = RoundedCornerShape(22.dp), minLines = 2, maxLines = 5,
                    enabled = !s.busy && s.run?.working != true && s.assistantReady,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send), keyboardActions = KeyboardActions(onSend = { vm.send() }))
                Row(verticalAlignment = Alignment.CenterVertically) { Text("确认后才保存", Modifier.weight(1f), fontSize = 11.sp, color = MaterialTheme.colorScheme.secondary); Button(onClick = vm::send, enabled = !s.busy && s.assistantReady && s.run?.working != true && s.draft.isNotBlank()) { Text("发送需求  ↑") } }
            }
        }
    }
}
@Composable private fun Bubble(text: String, user: Boolean) {
    if (text.isBlank()) return
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (user) Arrangement.End else Arrangement.Start) {
        Surface(Modifier.widthIn(max = if (user) 310.dp else 380.dp), color = if (user) Navy else Color.White, shape = RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp, bottomStart = if (user) 22.dp else 6.dp, bottomEnd = if (user) 6.dp else 22.dp)) {
            androidx.compose.foundation.text.selection.SelectionContainer { Text(text.replace("**", ""), Modifier.padding(18.dp), color = if (user) Color.White else Navy, fontSize = 15.sp, lineHeight = 25.sp) }
        }
    }
}
@Composable private fun Field(value: String, change: (String) -> Unit, label: String, type: KeyboardType = KeyboardType.Text) {
    OutlinedTextField(value, change, Modifier.fillMaxWidth(), label = { Text(label) }, shape = RoundedCornerShape(16.dp), keyboardOptions = KeyboardOptions(keyboardType = type), singleLine = true)
}
@Composable private fun CreateTripScreen(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    var title by rememberSaveable { mutableStateOf("") }; var city by rememberSaveable { mutableStateOf("") }
    var start by rememberSaveable { mutableStateOf(LocalDate.now().toString()) }; var end by rememberSaveable { mutableStateOf(LocalDate.now().plusDays(2).toString()) }; var budget by rememberSaveable { mutableStateOf("") }
    val context = LocalContext.current
    fun pick(value: String, onPick: (String) -> Unit) { val date = LocalDate.parse(value); DatePickerDialog(context, { _, y,m,d -> onPick(LocalDate.of(y,m+1,d).toString()) }, date.year,date.monthValue-1,date.dayOfMonth).show() }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Text("先定下出发的方向。", fontSize = 28.sp, fontWeight = FontWeight.Bold)
        Text("保存旅行信息后，可以继续与旅程总管安排每天的内容。", fontSize = 14.sp, color = MaterialTheme.colorScheme.secondary)
        Panel {
            Field(title, { title = it.take(120) }, "旅行名称")
            Field(city, { city = it.take(40) }, "目的地城市，例如杭州市")
            OutlinedButton(onClick = { pick(start) { start = it } }, modifier = Modifier.fillMaxWidth()) { Text("出发日期  $start") }
            OutlinedButton(onClick = { pick(end) { end = it } }, modifier = Modifier.fillMaxWidth()) { Text("结束日期  $end") }
            Field(budget, { budget = it }, "旅行总预算（元）", KeyboardType.Decimal)
            Button(onClick = { vm.createTrip(title, city, start, end, budget) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("创建旅行") }
        }
    }
}
