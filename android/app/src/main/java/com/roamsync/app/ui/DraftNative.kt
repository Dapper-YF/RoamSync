package com.roamsync.app.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import com.roamsync.app.data.*

@Composable
fun DraftNative(s: TourismState, vm: TourismViewModel, onOpenTrip: (String) -> Unit = {}) {
    val draft = s.travelDraft.takeIf { s.screen == "draft-detail" }
    if (draft == null) DraftHome(s, vm) else DraftEditor(s, vm, draft, onOpenTrip)
}

@Composable
private fun DraftHome(s: TourismState, vm: TourismViewModel) {
    var city by rememberSaveable { mutableStateOf(s.city) }
    var title by rememberSaveable { mutableStateOf("") }
    var dayCount by rememberSaveable { mutableIntStateOf(3) }
    var requirements by rememberSaveable { mutableStateOf("") }
    LazyColumn(
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { PageHeading("ROOM FOR IDEAS", "先记下旅行想法。", "日期还没定，也可以从真实地点和自己的要求开始。") }
        s.error?.let { error -> item { DraftErrorNotice(error, !s.busy, vm::retry) } }
        s.notice?.let { item { Text(it, color = DeepTeal, modifier = Modifier.padding(horizontal = 4.dp)) } }
        item {
            AppCard(color = Color(0xFFE9EEE4)) {
                Text("日期未定的草稿", color = DeepTeal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp)
                Text("把期待慢慢排成每天。", style = MaterialTheme.typography.headlineSmall, color = Ink)
                Text("草稿保存、活动建议和正式旅行是分开的。只有核对完整日期安排并明确确认后，服务才会创建正式旅行。", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item {
            AppCard {
                Text("新建一份草稿", style = MaterialTheme.typography.titleLarge, color = Ink)
                OutlinedTextField(city, { city = it.take(100); vm.editCity(it.take(100)) }, label = { Text("城市") }, placeholder = { Text("例如：杭州") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(title, { title = it.take(200) }, label = { Text("草稿名称") }, placeholder = { Text("例如：慢慢走的杭州周末") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text("旅行天数", color = Ink, fontWeight = FontWeight.SemiBold)
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = { dayCount = (dayCount - 1).coerceAtLeast(1) }, enabled = dayCount > 1) { Text("−") }
                    Text("$dayCount 天", style = MaterialTheme.typography.titleMedium, color = Ink)
                    OutlinedButton(onClick = { dayCount = (dayCount + 1).coerceAtMost(14) }, enabled = dayCount < 14) { Text("+") }
                    Text("1–14 天", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                OutlinedTextField(
                    requirements, { requirements = it.take(3000) },
                    label = { Text("这次想怎么玩") },
                    placeholder = { Text("写下同行人、节奏、兴趣和需要避开的安排。") },
                    minLines = 4, maxLines = 8,
                    supportingText = { Text("${requirements.length}/3000") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    onClick = { vm.editCity(city); vm.createDraft(title, dayCount, requirements) },
                    enabled = !s.busy && city.isNotBlank() && requirements.length <= 3000,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (s.busy) "正在创建…" else "创建日期未定草稿") }
            }
        }
        item { PageHeading("YOUR DRAFTS", "继续整理", "已保存的草稿可以重新打开；取消的草稿仍可恢复。") }
        if (s.travelDrafts.isEmpty()) item { QuietState("还没有草稿", "先写下城市、天数和希望怎么安排。") }
        items(s.travelDrafts, key = { it.text("id") }) { value ->
            val cancelled = value.text("status") == "cancelled"
            AppCard(Modifier.fillMaxWidth()) {
                Text(value.text("title").ifBlank { "未命名旅行" }, style = MaterialTheme.typography.titleLarge, color = Ink)
                Text("${value.text("city")} · ${value.text("day_count")} 天 · ${when { cancelled -> "已取消，可恢复"; value.text("saved") == "true" -> "已保存"; else -> "草稿已保留" }}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedButton(onClick = { vm.openDraft(value.text("id")) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text(if (cancelled) "打开并恢复" else "继续整理") }
            }
        }
    }
}

@Composable
private fun DraftEditor(s: TourismState, vm: TourismViewModel, draft: JsonObject, onOpenTrip: (String) -> Unit) {
    val id = draft.text("id")
    var initialized by rememberSaveable(id) { mutableStateOf(false) }
    var title by rememberSaveable(id) { mutableStateOf("") }
    var requirements by rememberSaveable(id) { mutableStateOf("") }
    var planText by rememberSaveable(id) { mutableStateOf("") }
    var baseTitle by rememberSaveable(id) { mutableStateOf("") }
    var baseRequirements by rememberSaveable(id) { mutableStateOf("") }
    var basePlanText by rememberSaveable(id) { mutableStateOf("") }
    var baseVersion by rememberSaveable(id) { mutableIntStateOf(-1) }
    var saveReview by rememberSaveable(id) { mutableStateOf(false) }
    var pendingSave by rememberSaveable(id) { mutableStateOf(false) }
    var pendingSaveVersion by rememberSaveable(id) { mutableIntStateOf(-1) }
    var cancelDraftConfirmation by rememberSaveable(id) { mutableStateOf(false) }
    var generationRequest by rememberSaveable(id) { mutableStateOf("") }
    var generationScope by rememberSaveable(id) { mutableStateOf("all") }
    var placeQuery by rememberSaveable(id) { mutableStateOf("") }
    var pickerDay by rememberSaveable(id) { mutableIntStateOf(-1) }
    var pickerItem by rememberSaveable(id) { mutableIntStateOf(-1) }
    var pickerOpen by rememberSaveable(id) { mutableStateOf(false) }
    val version = draft["version"]?.jsonPrimitive?.intOrNull ?: 1
    val dayCount = draft["day_count"]?.jsonPrimitive?.intOrNull ?: 1
    val active = draft.text("status") != "cancelled"
    val running = draft.rows("runs").any { it.text("status") == "running" }
    val dirty = initialized && (title != baseTitle || requirements != baseRequirements || normalizeJson(planText) != normalizeJson(basePlanText))
    val conflict = dirty && baseVersion != version && !pendingSave
    val locked = s.busy || running || !active

    LaunchedEffect(id) {
        if (!initialized) {
            title = draft.text("title")
            requirements = draft.text("requirements")
            planText = draftPlanText(draft)
            baseTitle = title
            baseRequirements = requirements
            basePlanText = planText
            baseVersion = version
            initialized = true
        }
    }
    LaunchedEffect(version, s.busy, s.error) {
        if (!initialized) return@LaunchedEffect
        if (pendingSave && version > pendingSaveVersion) {
            baseTitle = title; baseRequirements = requirements; basePlanText = normalizeJson(planText); planText = basePlanText
            baseVersion = version; pendingSave = false; saveReview = false
        } else if (!pendingSave && version != baseVersion && !dirty) {
            title = draft.text("title"); requirements = draft.text("requirements"); planText = draftPlanText(draft)
            baseTitle = title; baseRequirements = requirements; basePlanText = planText; baseVersion = version
        }
        if (pendingSave && !s.busy && !s.error.isNullOrBlank()) pendingSave = false
    }
    LaunchedEffect(id, running) {
        if (!running) return@LaunchedEffect
        while (isActive) {
            delay(1800)
            if (!s.busy) vm.openDraft(id)
        }
    }
    LaunchedEffect(id) { if (s.draftEffectiveRequirements == null && !s.busy) vm.refreshDraftRequirements() }

    fun saveChanges() {
        if (!dirty || conflict || locked) return
        val plan = planText.takeIf(String::isNotBlank)?.let { runCatching { Json.parseToJsonElement(it) }.getOrNull() }
        if (planText.isNotBlank() && plan == null) return
        pendingSaveVersion = version
        pendingSave = true
        vm.editSelectedDraft(title, requirements, plan)
    }
    fun generate() {
        if (dirty || conflict || locked || generationRequest.isBlank()) return
        vm.runDraft(generationRequest, generationScope.takeIf { it != "all" }?.toIntOrNull())
    }
    fun editDay(dayIndex: Int, update: (JsonObject) -> JsonObject) {
        planText = updateDraftDay(planText, dayCount, dayIndex, update)
        saveReview = false
    }
    fun selectPlace(place: JsonObject) {
        val placeId = place.placeId()
        val ref = place.obj("ref")
        val provider = ref.obj("external_ref").text("provider")
        val providerPlaceId = ref.obj("external_ref").text("provider_place_id")
        if (placeId.isBlank() || provider.isBlank() || providerPlaceId.isBlank()) return
        val dayIndex = pickerDay
        val itemIndex = pickerItem
        editDay(dayIndex) { day ->
            val items = day.rows("items").toMutableList()
            val selected = buildJsonObject {
                put("name", place.text("name")); put("note", items.getOrNull(itemIndex)?.text("note") ?: "")
                put("place_id", placeId); put("identity_status", "provider_confirmed")
            }
            if (itemIndex in items.indices) items[itemIndex] = selected else items += selected
            JsonObject(day + ("items" to JsonArray(items)))
        }
        pickerOpen = false
        vm.loadDraftPlaceDetail(placeId)
    }

    LazyColumn(
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { PageHeading("ROOM FOR IDEAS", title.ifBlank { draft.text("title") }, "${draft.text("city")} · $dayCount 天 · 日期未定") }
        s.error?.let { error -> item { DraftErrorNotice(error, !s.busy, vm::retry) } }
        s.notice?.let { item { Text(it, color = DeepTeal, modifier = Modifier.padding(horizontal = 4.dp)) } }
        item {
            AppCard(color = Color(0xFFE9EEE4)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("DATES OPEN", color = DeepTeal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.3.sp)
                        Text(if (dirty) "有未保存的修改" else if (draft.text("saved") == "true") "草稿已保存" else "草稿内容已保留", color = Ink, fontWeight = FontWeight.SemiBold)
                    }
                    Text("v$version", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                Text("草稿不会更改正式旅行。活动建议与地点身份需要核对；日期确定后会先生成完整预览，再由你明确确认。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            }
        }
        if (conflict) item {
            AppCard(color = Color(0xFFFFF1E6)) {
                Text("草稿已经在别处更新", style = MaterialTheme.typography.titleMedium, color = Ink)
                Text("本机未保存编辑仍在。先核对最新版本，再选择是否丢弃本机修改。", color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedButton(onClick = {
                    title = draft.text("title"); requirements = draft.text("requirements"); planText = draftPlanText(draft)
                    baseTitle = title; baseRequirements = requirements; basePlanText = planText; baseVersion = version; saveReview = false
                }, enabled = !s.busy) { Text("放弃本机修改，使用最新版本") }
            }
        }
        if (!active) item {
            AppCard {
                Text("这份草稿已取消，内容仍保留。", style = MaterialTheme.typography.titleMedium, color = Ink)
                Button(onClick = { vm.draftAction("restore") }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("恢复草稿并继续") }
            }
        }
        item {
            AppCard {
                Text("这次想怎么玩", style = MaterialTheme.typography.titleLarge, color = Ink)
                OutlinedTextField(title, { title = it.take(200) }, enabled = active && !s.busy, label = { Text("草稿名称") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    requirements, { requirements = it.take(3000) }, enabled = active && !s.busy,
                    label = { Text("整段旅行的要求") }, placeholder = { Text("同行人、节奏、偏好和需要避开的安排") },
                    minLines = 4, maxLines = 9, supportingText = { Text("${requirements.length}/3000") }, modifier = Modifier.fillMaxWidth(),
                )
                Text("已保存要求会进入服务端的要求记录。下面可以单独调整某一天；修改前先保存当前内容。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { if (dirty) saveReview = true else vm.draftAction("save") }, enabled = active && !s.busy && !running && !conflict && title.isNotBlank(), modifier = Modifier.weight(1f)) { Text(if (dirty) "核对并保存" else "保存草稿") }
                    OutlinedButton(onClick = {
                        title = baseTitle; requirements = baseRequirements; planText = basePlanText; saveReview = false
                    }, enabled = dirty && !s.busy, modifier = Modifier.weight(1f)) { Text("放弃本地修改") }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { vm.assistantDraft(id, version, draft.text("city")) }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("和旅行 AI 讨论") }
                    if (active) OutlinedButton(onClick = { cancelDraftConfirmation = true }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("取消这份草稿") }
                }
            }
        }
        item { DraftRequirementsNative(s, vm, id, version, disabled = s.busy || dirty || conflict) }
        item {
            AppCard {
                Text(if (planText.isBlank()) "安排每日活动" else "调整活动建议", style = MaterialTheme.typography.titleLarge, color = Ink)
                OutlinedTextField(
                    generationRequest, { generationRequest = it.take(3000) }, enabled = active && !s.busy,
                    label = { Text("这次希望怎样安排") }, placeholder = { Text("例如：第二天轻松一点，多留时间在湖边") },
                    minLines = 3, maxLines = 7, supportingText = { Text("${generationRequest.length}/3000") }, modifier = Modifier.fillMaxWidth(),
                )
                if (planText.isNotBlank()) {
                    Text("调整范围", color = Ink, fontWeight = FontWeight.SemiBold)
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        FilterChip(selected = generationScope == "all", onClick = { generationScope = "all" }, enabled = active && !s.busy, label = { Text("整段旅行") })
                        (1..dayCount).forEach { index -> FilterChip(selected = generationScope == index.toString(), onClick = { generationScope = index.toString() }, enabled = active && !s.busy, label = { Text("第${index}天") }) }
                    }
                    if (generationScope != "all") Text("本次只调整第${generationScope}天，其余日期由服务端保留。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                Button(onClick = ::generate, enabled = active && !s.busy && !running && !dirty && !conflict && generationRequest.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
                    Text(if (running) "正在整理活动…" else if (planText.isBlank()) "生成每日活动建议" else "按所选范围调整")
                }
                if (dirty) Text("先保存或放弃手动修改，再重新生成活动建议。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                if (running) Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp)); Text("服务仍在整理，离开后可以回来继续查看。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    Spacer(Modifier.weight(1f)); TextButton(onClick = { vm.draftAction("cancel-run") }, enabled = !s.busy) { Text("停止") }
                }
            }
        }
        val parsedPlan = parseDraftPlan(planText)
        if (parsedPlan == null) item { QuietState("每天留一点期待", "写下调整要求，生成活动建议；也可以直接添加待核实的活动想法。") }
        parsedPlan?.rows("days")?.sortedBy { it["day_index"]?.jsonPrimitive?.intOrNull ?: Int.MAX_VALUE }?.forEach { day ->
            val index = day["day_index"]?.jsonPrimitive?.intOrNull ?: return@forEach
            item(key = "draft-day-$index") {
                DraftDayCard(
                    s = s, draftId = id, day = day,
                    disabled = locked || conflict, onDayChange = { update -> editDay(index, update) },
                    onLoadDetail = vm::loadDraftPlaceDetail,
                    loadImageBytes = vm::reviewedImageBytes,
                    onChoosePlace = { activityIndex, query ->
                        pickerDay = index; pickerItem = activityIndex; placeQuery = query; pickerOpen = true
                    },
                )
            }
        }
        if (pickerOpen) item(key = "draft-place-picker") {
            DraftPlacePickerNative(
                s = s, city = draft.text("city"), query = placeQuery,
                onQueryChange = { placeQuery = it.take(200) }, onSearch = { vm.searchDraftPlaces(draft.text("city"), placeQuery) },
                onPick = ::selectPlace, onClose = { pickerOpen = false }, vmImageLoader = vm::reviewedImageBytes,
            )
        }
        if (draft.rows("runs").isNotEmpty()) item {
            DraftRunHistory(draft.rows("runs"))
        }
        if (saveReview && dirty) item {
            AppCard {
                Text("核对并保存修改", style = MaterialTheme.typography.titleLarge, color = Ink)
                if (title != baseTitle) Text("名称：${baseTitle.ifBlank { "未命名" }} → ${title.ifBlank { "未命名" }}")
                if (requirements != baseRequirements) {
                    Text("修改前的要求", color = DeepTeal, fontWeight = FontWeight.SemiBold)
                    Text(baseRequirements.ifBlank { "未填写" })
                    Text("修改后的要求", color = DeepTeal, fontWeight = FontWeight.SemiBold)
                    Text(requirements.ifBlank { "未填写" })
                }
                DraftPlanDifference(basePlanText, planText)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = ::saveChanges, enabled = !locked && !conflict, modifier = Modifier.weight(1f)) { Text("确认保存") }
                    OutlinedButton(onClick = { saveReview = false }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("继续编辑") }
                }
            }
        }
        item { DraftPromotionNative(s, vm, draft, disabled = locked || dirty || conflict, onOpenTrip = onOpenTrip) }
        item {
            AppCard(color = Color(0xFFF1F0E6)) {
                Text("活动与正式安排", style = MaterialTheme.typography.titleMedium, color = Ink)
                Text("未确认的活动想法会清楚标出。已选地点以服务端 Place 身份为准；营业、预约、价格和现场情况仍需出发前核对。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
        }
        if (cancelDraftConfirmation) item {
            AlertDialog(
                onDismissRequest = { cancelDraftConfirmation = false },
                title = { Text("取消这份草稿？") },
                text = { Text("内容会保留，之后可以恢复继续编辑。正式旅行不会因此改变。") },
                confirmButton = { TextButton(onClick = { cancelDraftConfirmation = false; vm.draftAction("cancel") }) { Text("取消草稿") } },
                dismissButton = { TextButton(onClick = { cancelDraftConfirmation = false }) { Text("继续编辑") } },
            )
        }
    }
}

@Composable
private fun DraftDayCard(
    s: TourismState,
    draftId: String,
    day: JsonObject,
    disabled: Boolean,
    onDayChange: ((JsonObject) -> JsonObject) -> Unit,
    onLoadDetail: (String) -> Unit,
    loadImageBytes: suspend (String) -> ByteArray,
    onChoosePlace: (itemIndex: Int, initialQuery: String) -> Unit,
) {
    val dayIndex = day["day_index"]?.jsonPrimitive?.intOrNull ?: 0
    var idea by rememberSaveable(draftId, dayIndex) { mutableStateOf("") }
    val activityItems = day.rows("items")
    AppCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("DAY ${dayIndex.toString().padStart(2, '0')}", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
            Spacer(Modifier.width(10.dp))
            OutlinedTextField(
                value = day.text("title"), onValueChange = { value -> onDayChange { JsonObject(it + ("title" to JsonPrimitive(value.take(200)))) } },
                enabled = !disabled, label = { Text("第${dayIndex}天主题") }, singleLine = true, modifier = Modifier.weight(1f),
            )
        }
        if (activityItems.isEmpty()) Text("这一天还没有活动。你可以添加一个待核实想法，或从真实地点中选择。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        activityItems.forEachIndexed { index, item ->
            DraftActivityCard(
                s = s, draftId = draftId, dayIndex = dayIndex, itemIndex = index, item = item,
                disabled = disabled, onChange = { next -> onDayChange { dayValue ->
                    val values = dayValue.rows("items").toMutableList(); if (index in values.indices) values[index] = next
                    JsonObject(dayValue + ("items" to JsonArray(values)))
                } },
                onChoosePlace = { onChoosePlace(index, item.text("name")) },
                onLoadDetail = onLoadDetail,
                loadImageBytes = loadImageBytes,
                itemCount = activityItems.size,
                onMove = { offset -> onDayChange { dayValue ->
                    val values = dayValue.rows("items").toMutableList(); val target = index + offset
                    if (target in values.indices) { val old = values[index]; values[index] = values[target]; values[target] = old }
                    JsonObject(dayValue + ("items" to JsonArray(values)))
                } },
                onRemove = { onDayChange { dayValue -> JsonObject(dayValue + ("items" to JsonArray(dayValue.rows("items").filterIndexed { i, _ -> i != index }))) } },
            )
            if (index < activityItems.lastIndex) HorizontalDivider(color = Color(0xFFE8E6DC))
        }
        OutlinedTextField(idea, { idea = it.take(200) }, enabled = !disabled, label = { Text("添加待核实的活动想法") }, placeholder = { Text("例如：找一家本地茶馆坐一会儿") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = {
                    val next = buildJsonObject { put("name", idea.trim()); put("note", ""); put("place_id", JsonNull); put("identity_status", "unknown") }
                    onDayChange { d -> JsonObject(d + ("items" to JsonArray(d.rows("items") + next))) }
                    idea = ""
                }, enabled = !disabled && idea.isNotBlank() && activityItems.size < 12, modifier = Modifier.weight(1f),
            ) { Text("添加想法") }
            Button(onClick = { onChoosePlace(-1, "") }, enabled = !disabled && activityItems.size < 12, modifier = Modifier.weight(1f)) { Text("选择真实地点") }
        }
        if (activityItems.size >= 12) Text("每天最多保留 12 项活动。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
    }
}

@Composable
private fun DraftActivityCard(
    s: TourismState,
    draftId: String,
    dayIndex: Int,
    itemIndex: Int,
    item: JsonObject,
    disabled: Boolean,
    onChange: (JsonObject) -> Unit,
    onChoosePlace: () -> Unit,
    onLoadDetail: (String) -> Unit,
    loadImageBytes: suspend (String) -> ByteArray,
    itemCount: Int,
    onMove: (Int) -> Unit,
    onRemove: () -> Unit,
) {
    val placeId = item.text("place_id")
    val identityConfirmed = item.text("identity_status") == "provider_confirmed" && placeId.isNotBlank()
    val detail = s.draftPlaceDetails[placeId]?.takeIf { it.placeId() == placeId }
    var detailsOpen by rememberSaveable(draftId, dayIndex, itemIndex) { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                OutlinedTextField(
                    value = item.text("name"), onValueChange = { onChange(JsonObject(item + ("name" to JsonPrimitive(it.take(200))) + ("place_id" to JsonNull) + ("identity_status" to JsonPrimitive("unknown")))) },
                    enabled = !disabled, label = { Text("活动或地点想法") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
                if (identityConfirmed) {
                    Text("已核实真实地点", color = DeepTeal, fontSize = 11.sp)
                } else {
                    Text("地点待核实 · 这只是活动想法", color = SoftOrange, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        OutlinedTextField(
            value = item.text("note"), onValueChange = { onChange(JsonObject(item + ("note" to JsonPrimitive(it.take(1000))))) },
            enabled = !disabled, label = { Text("活动备注") }, placeholder = { Text("时间偏好、同行人提示或其他补充") },
            minLines = 2, maxLines = 5, modifier = Modifier.fillMaxWidth(),
        )
        if (identityConfirmed) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { detailsOpen = !detailsOpen; if (detail == null) onLoadDetail(placeId) }, enabled = !s.busy, modifier = Modifier.weight(1f)) {
                    Text(if (detailsOpen) "收起地点资料" else "查看地点资料与照片")
                }
                TextButton(onClick = onChoosePlace, enabled = !disabled) { Text("更换地点") }
            }
            if (detailsOpen) {
                if (detail == null) Text(if (s.busy) "正在读取精确地点资料…" else "尚未读取地点详情。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                else {
                    val exactPlace = detail
                    Text("${exactPlace.text("name")} · ${exactPlace.text("city")}", color = Ink, fontWeight = FontWeight.SemiBold)
                    Text(exactPlace.text("address").ifBlank { "地址暂无" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    DraftReviewedPhoto(exactPlace, loadImageBytes)
                }
            }
        } else {
            OutlinedButton(onClick = onChoosePlace, enabled = !disabled, modifier = Modifier.fillMaxWidth()) { Text("从真实地点中核实并选择") }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { onMove(-1) }, enabled = !disabled && itemIndex > 0) { Text("上移") }
            TextButton(onClick = { onMove(1) }, enabled = !disabled && itemIndex < itemCount - 1) { Text("下移") }
            TextButton(onClick = onRemove, enabled = !disabled) { Text("移除") }
        }
    }
}

@Composable
private fun DraftPlacePickerNative(
    s: TourismState,
    city: String,
    query: String,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
    onPick: (JsonObject) -> Unit,
    onClose: () -> Unit,
    vmImageLoader: suspend (String) -> ByteArray,
) {
    AppCard(color = Color(0xFFF1F0E6)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text("选择真实地点", style = MaterialTheme.typography.titleLarge, color = Ink); Text("$city · 搜索结果来自地点服务", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
            TextButton(onClick = onClose) { Text("关闭") }
        }
        OutlinedTextField(query, onQueryChange, label = { Text("地点名称或关键词") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        Button(onClick = onSearch, enabled = !s.busy && query.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text(if (s.busy) "正在查找…" else "搜索地点") }
        if (s.draftPlaces.isEmpty() && !s.busy) Text("输入关键词后搜索。无匹配地点时，活动想法会继续标记为待核实。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        s.draftPlaces.forEach { place ->
            val id = place.placeId()
            val exactProviderIdentity = id.isNotBlank() && place.obj("ref").obj("external_ref").text("provider").isNotBlank() && place.obj("ref").obj("external_ref").text("provider_place_id").isNotBlank()
            Surface(shape = RoundedCornerShape(18.dp), color = Paper, border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE6E3D8))) {
                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (approvedPhotos(place).isNotEmpty()) DraftReviewedPhoto(place, vmImageLoader)
                    Text(place.text("name"), style = MaterialTheme.typography.titleMedium, color = Ink)
                    Text("${place.text("city")} · ${place.text("address").ifBlank { "地址暂无" }}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    Text(if (exactProviderIdentity) "服务端地点身份已确认" else "地点身份不完整，不能关联到草稿", color = if (exactProviderIdentity) DeepTeal else SoftOrange, fontSize = 11.sp)
                    Button(onClick = { onPick(place) }, enabled = !s.busy && exactProviderIdentity, modifier = Modifier.fillMaxWidth()) { Text("选中这个地点") }
                }
            }
        }
    }
}

@Composable
internal fun DraftReviewedPhoto(place: JsonObject, vmImageLoader: suspend (String) -> ByteArray) {
    val photos = approvedPhotos(place)
    if (photos.isEmpty()) {
        Text("此地点暂未收录经审核照片", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        return
    }
    val photo = photos.first()
    var loadError by remember(photo.text("thumbnail_url")) { mutableStateOf(false) }
    val bitmap by produceState<Bitmap?>(null, photo.text("thumbnail_url"), vmImageLoader) {
        value = withContext(Dispatchers.IO) {
            runCatching {
                val bytes = vmImageLoader(photo.text("thumbnail_url"))
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            }.getOrNull()
        }
        loadError = value == null
    }
    if (bitmap != null) androidx.compose.foundation.Image(bitmap!!.asImageBitmap(), contentDescription = photo.text("title").ifBlank { place.text("name") }, modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(16.dp)), contentScale = ContentScale.Crop)
    else if (loadError) Text("经审核照片暂时无法加载", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
    val uriHandler = LocalUriHandler.current
    Text(photo.text("title"), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        TextButton(onClick = { runCatching { uriHandler.openUri(photo.text("source_url")) } }, contentPadding = PaddingValues(horizontal = 2.dp, vertical = 0.dp)) {
            Text("${photo.text("attribution")} · Commons", fontSize = 10.sp)
        }
        Text("·", color = MaterialTheme.colorScheme.outline, fontSize = 10.sp)
        TextButton(onClick = { runCatching { uriHandler.openUri(photo.text("license_url")) } }, contentPadding = PaddingValues(horizontal = 2.dp, vertical = 0.dp)) {
            Text(photo.text("license_name"), fontSize = 10.sp)
        }
    }
}

@Composable
private fun DraftRunHistory(runs: List<JsonObject>) {
    AppCard {
        Text("生成和修改记录", style = MaterialTheme.typography.titleLarge, color = Ink)
        runs.asReversed().forEach { run ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("${draftRunStatus(run.text("status"))} · ${if (run.text("source") == "model") "模型建议" else "演示内容"}", color = DeepTeal, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Text(run.text("requirements").ifBlank { "首次安排" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                if (run.text("error").isNotBlank()) Text(run.text("error"), color = SoftOrange, fontSize = 12.sp)
            }
            if (run != runs.last()) HorizontalDivider(color = Color(0xFFE8E6DC))
        }
    }
}

@Composable
private fun DraftPlanDifference(beforeText: String, afterText: String) {
    val before = parseDraftPlan(beforeText)
    val after = parseDraftPlan(afterText)
    val days = after?.rows("days").orEmpty()
    if (days.isEmpty()) {
        if (beforeText != afterText) Text(if (after == null) "活动安排将被清空。" else "活动安排有修改。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    days.forEach { day ->
        val index = day["day_index"]?.jsonPrimitive?.intOrNull ?: return@forEach
        val old = before?.rows("days")?.firstOrNull { it["day_index"]?.jsonPrimitive?.intOrNull == index }
        if (normalizeJson(old?.toString().orEmpty()) != normalizeJson(day.toString())) {
            Text("第${index}天修改前", color = DeepTeal, fontWeight = FontWeight.SemiBold)
            Text(old?.let(::daySummary) ?: "尚未安排")
            Text("第${index}天修改后", color = DeepTeal, fontWeight = FontWeight.SemiBold)
            Text(daySummary(day))
        }
    }
}

private fun draftPlanText(draft: JsonObject): String = (draft["plan"] as? JsonObject)?.toString().orEmpty()
private fun parseDraftPlan(value: String): JsonObject? = runCatching { Json.parseToJsonElement(value) as? JsonObject }.getOrNull()
private fun normalizeJson(value: String): String = value.ifBlank { "" }
private fun updateDraftDay(planText: String, dayCount: Int, target: Int, update: (JsonObject) -> JsonObject): String {
    val plan = parseDraftPlan(planText)
    val existing = plan?.rows("days").orEmpty().associateBy { it["day_index"]?.jsonPrimitive?.intOrNull }
    val days = (1..dayCount).map { index ->
        val day = existing[index] ?: buildJsonObject { put("day_index", index); put("title", "第${index}天"); put("items", JsonArray(emptyList())) }
        if (index == target) update(day) else day
    }
    return buildJsonObject { put("days", JsonArray(days)) }.toString()
}
private fun daySummary(day: JsonObject): String = buildString {
    append(day.text("title").ifBlank { "未命名主题" })
    day.rows("items").forEachIndexed { index, item ->
        append("\n${index + 1}. ${item.text("name")}")
        if (item.text("note").isNotBlank()) append(" · ${item.text("note")}")
        if (item.text("identity_status") != "provider_confirmed" || item.text("place_id").isBlank()) append("（地点待核实）")
    }
}
private fun draftRunStatus(value: String) = when (value) {
    "running" -> "进行中"; "completed" -> "已完成"; "failed" -> "失败，可重试"; "cancelled" -> "已取消"; "interrupted" -> "已中断，可重新生成"; else -> "状态未知"
}

@Composable
private fun DraftErrorNotice(message: String, enabled: Boolean, retry: () -> Unit) {
    AppCard(color = Color(0xFFFFF1E6)) {
        Text(message, color = Ink)
        OutlinedButton(onClick = retry, enabled = enabled) { Text("重试") }
    }
}
