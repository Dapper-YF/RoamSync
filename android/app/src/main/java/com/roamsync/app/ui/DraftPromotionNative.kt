package com.roamsync.app.ui

import android.app.DatePickerDialog
import androidx.compose.foundation.layout.*
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
import com.roamsync.app.data.*
import java.math.BigDecimal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.serialization.json.*

@Composable
internal fun DraftPromotionNative(
    s: TourismState,
    vm: TourismViewModel,
    draft: JsonObject,
    disabled: Boolean,
    onOpenTrip: (String) -> Unit,
) {
    val draftId = draft.text("id")
    var startDate by rememberSaveable(draftId) { mutableStateOf("") }
    var totalBudget by rememberSaveable(draftId) { mutableStateOf("") }
    var dailyBudget by rememberSaveable(draftId) { mutableStateOf("") }
    var mode by rememberSaveable(draftId) { mutableStateOf("walk") }
    var duration by rememberSaveable(draftId) { mutableStateOf("90") }
    var unknownEstimate by rememberSaveable(draftId) { mutableStateOf("100") }
    var dailyStart by rememberSaveable(draftId) { mutableStateOf("09:00") }
    var dailyEnd by rememberSaveable(draftId) { mutableStateOf("21:00") }
    var maxWalking by rememberSaveable(draftId) { mutableStateOf("60") }
    var validationMessage by rememberSaveable(draftId) { mutableStateOf("") }
    var confirmAction by rememberSaveable(draftId) { mutableStateOf("") }
    val context = LocalContext.current
    val prepared = s.promotionPreview
    val activities = prepared?.rows("activities").orEmpty()
    val routes = prepared?.rows("routes").orEmpty()
    val coverage = prepared?.obj("coverage")
    val blockers = coverage?.stringArray("blockers").orEmpty()
    val checked = coverage?.stringArray("checked").orEmpty()
    val missing = coverage?.stringArray("missing").orEmpty()
    val coverageComplete = coverage != null && coverage["checked"] is JsonArray && coverage["missing"] is JsonArray && coverage["blockers"] is JsonArray
    val preparedId = prepared?.text("id").orEmpty()
    val matchingOperation = s.promotionOperations.firstOrNull { it.text("prepared_id") == preparedId && preparedId.isNotBlank() }
    val staleVersion = prepared != null && prepared["draft_version"]?.jsonPrimitive?.intOrNull != (draft["version"]?.jsonPrimitive?.intOrNull ?: 0)
    val expired = prepared?.text("expires_at")?.let { runCatching { Instant.parse(it).isBefore(Instant.now()) }.getOrDefault(false) } ?: false
    val stale = staleVersion || expired
    val budgetNumbersValid = (totalBudget.isBlank() && dailyBudget.isBlank()) || (totalBudget.isNotBlank() && dailyBudget.isNotBlank())
    val durationValue = duration.toIntOrNull()
    val estimateFen = amountFen(unknownEstimate)
    val dailyStartValid = validTime(dailyStart)
    val dailyEndValid = validTime(dailyEnd) && dailyEnd > dailyStart
    val walkingValue = maxWalking.toIntOrNull()
    val today = LocalDate.now()
    val parsedStartDate = runCatching { LocalDate.parse(startDate) }.getOrNull()
    val startDateValid = parsedStartDate != null && !parsedStartDate.isBefore(today)
    val canPreview = !s.busy && !disabled && startDateValid && budgetNumbersValid &&
        (totalBudget.isBlank() || amountFen(totalBudget) != null && amountFen(dailyBudget) != null && requireNotNull(amountFen(dailyBudget)) <= requireNotNull(amountFen(totalBudget))) &&
        durationValue != null && durationValue in 15..480 && estimateFen != null && dailyStartValid && dailyEndValid && walkingValue != null && walkingValue in 1..480

    fun preview() {
        validationMessage = ""
        val total = amountFen(totalBudget)
        val daily = amountFen(dailyBudget)
        val stay = duration.toIntOrNull()
        val estimate = amountFen(unknownEstimate)
        val walkLimit = maxWalking.toIntOrNull()
        if (!canPreview || stay == null || estimate == null || walkLimit == null) {
            validationMessage = when {
                startDate.isBlank() -> "请先选择出发日期。"
                !startDateValid -> "出发日期不能早于今天，请重新选择日期。"
                !budgetNumbersValid -> "总预算和每日预算请同时填写，或都留空。"
                !dailyStartValid || !dailyEndValid -> "请检查每日开始和结束时间，格式为 24 小时 HH:MM。"
                else -> "请检查预算、停留时长和步行上限（每日步行上限为 1–480 分钟）。"
            }
            return
        }
        vm.previewDraftPromotion(
            startDate = startDate,
            totalBudgetFen = total,
            dailyBudgetFen = daily,
            transportMode = mode,
            durationMinutes = stay,
            unknownCostEstimateFen = estimate,
            dailyStartTime = dailyStart,
            dailyEndTime = dailyEnd,
            maxWalkingMinutes = walkLimit,
        )
    }

    AppCard {
        Text("WHEN YOU ARE READY", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp)
        Text("日期确定了，再准备正式旅行", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text("填写日期和约束后，服务会核对地点、活动时间、路线与费用。生成预览不会创建旅行。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(startDate, { }, readOnly = true, label = { Text("出发日期") }, placeholder = { Text("选择日期") }, modifier = Modifier.weight(1f))
            OutlinedButton(onClick = {
                val initial = runCatching { LocalDate.parse(startDate) }.getOrElse { today }.coerceAtLeast(today)
                DatePickerDialog(context, { _, year, month, day -> startDate = "%04d-%02d-%02d".format(year, month + 1, day); vm.clearDraftPromotionPreview() }, initial.year, initial.monthValue - 1, initial.dayOfMonth).apply {
                    datePicker.minDate = today.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
                    show()
                }
            }, enabled = !s.busy && !disabled) { Text("选择日期") }
        }
        Text("如有预算，请同时设置总预算和每日预算；留空表示不设上限。金额以人民币元填写。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(totalBudget, { totalBudget = it.take(12); prepared?.let { vm.clearDraftPromotionPreview() } }, enabled = !s.busy && !disabled, label = { Text("总预算（元）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(dailyBudget, { dailyBudget = it.take(12); prepared?.let { vm.clearDraftPromotionPreview() } }, enabled = !s.busy && !disabled, label = { Text("每日预算（元）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true, modifier = Modifier.weight(1f))
        }
        Text("交通方式", color = Ink, fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = mode == "walk", onClick = { mode = "walk"; vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("步行") })
            FilterChip(selected = mode == "driving", onClick = { mode = "driving"; vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("驾车") })
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(duration, { duration = it.filter(Char::isDigit).take(3); vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("单处停留（分钟）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(unknownEstimate, { unknownEstimate = it.take(12); vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("未知费用估算（元/处）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true, modifier = Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(dailyStart, { dailyStart = it.take(5); vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("每日开始") }, placeholder = { Text("09:00") }, singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(dailyEnd, { dailyEnd = it.take(5); vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("每日结束") }, placeholder = { Text("21:00") }, singleLine = true, modifier = Modifier.weight(1f))
        }
        OutlinedTextField(maxWalking, { maxWalking = it.filter(Char::isDigit).take(3); vm.clearDraftPromotionPreview() }, enabled = !s.busy && !disabled, label = { Text("每日最大步行时间（分钟）") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.fillMaxWidth())
        Text("费用为服务端参考或规划估算，不能用于预订；正式采用前还要核对营业、预约和实时情况。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        if (validationMessage.isNotBlank()) Text(validationMessage, color = SoftOrange, fontSize = 12.sp)
        Button(onClick = ::preview, enabled = canPreview && startDate.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text(if (s.busy) "正在核对…" else "查看日期和完整安排") }
        if (!budgetNumbersValid) Text("预算需要同时填写，或同时留空。", color = SoftOrange, fontSize = 12.sp)
    }

    if (s.error != null) AppCard(color = Color(0xFFFFF1E6)) { Text(s.error, color = Ink) }

    if (prepared != null) {
        AppCard {
            Text("待确认的正式安排", style = MaterialTheme.typography.titleLarge, color = Ink)
            Text(prepared.text("title"), style = MaterialTheme.typography.titleMedium, color = DeepTeal)
            Text("${prepared.text("city")} · ${prepared.obj("constraints").text("start_date")} — ${prepared.text("end_date")}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("总预算 ${money(prepared.obj("constraints").number("total_budget_fen"))} · 每日预算 ${money(prepared.obj("constraints").number("daily_budget_fen"))}", color = Ink)
            Text("${if (prepared.obj("constraints").text("transport_mode") == "walk") "步行" else "驾车"} · 每处停留 ${prepared.obj("constraints").text("duration_minutes")} 分钟 · ${prepared.obj("constraints").text("daily_start_time")}–${prepared.obj("constraints").text("daily_end_time")} · 每日步行上限 ${prepared.obj("constraints").text("max_walking_minutes")} 分钟", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            if (prepared.text("requirements").isNotBlank()) Text("保留要求：${prepared.text("requirements")}", color = Ink)
            if (activities.isEmpty()) Text("预览没有返回活动。请读取错误或调整草稿后重新核对。", color = SoftOrange)
            activities.groupBy { it.text("day_date") }.toSortedMap().forEach { (date, rows) ->
                HorizontalDivider(color = Mist)
                Text(date, style = MaterialTheme.typography.titleMedium, color = Ink, fontWeight = FontWeight.SemiBold)
                rows.sortedBy { it["position"]?.jsonPrimitive?.intOrNull ?: Int.MAX_VALUE }.forEachIndexed { index, activity ->
                    val placeId = activity.text("place_id")
                    val exactPlace = s.draftPlaceDetails[placeId]?.takeIf { it.placeId() == placeId }
                    Surface(shape = RoundedCornerShape(16.dp), color = Color(0xFFF7F4EB)) {
                        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text("${activity.text("planned_start_time").take(5)} · ${activity.text("name")}", color = Ink, fontWeight = FontWeight.SemiBold)
                            Text("停留 ${activity.text("duration_minutes")} 分钟 · ${if (activity.text("cost_nature") == "provider_reference") "地点参考" else "规划估算"} ${money(activity.number("estimated_cost_fen"))}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                            if (activity.text("note").isNotBlank()) Text(activity.text("note"), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                            if (placeId.isBlank()) Text("地点尚待确认", color = SoftOrange, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                            else {
                                Text("已核对真实地点身份", color = DeepTeal, fontSize = 11.sp)
                                if (exactPlace != null && approvedPhotos(exactPlace).isNotEmpty()) DraftReviewedPhoto(exactPlace, vm::reviewedImageBytes)
                                else Text("地点照片未收录或尚未读取，不影响身份和安排复核。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                            }
                            if (placeId.isNotBlank() && exactPlace == null) TextButton(onClick = { vm.loadDraftPlaceDetail(placeId) }, enabled = !s.busy) { Text("读取该地点真实资料") }
                        }
                    }
                }
            }
            if (routes.isNotEmpty()) {
                Text("路线检查", style = MaterialTheme.typography.titleMedium, color = Ink)
                routes.forEach { route ->
                    val routeData = route.obj("route")
                    val from = activities.firstOrNull { it.text("ref") == route.text("from_ref") }?.text("name") ?: route.text("from_ref")
                    val to = activities.firstOrNull { it.text("ref") == route.text("to_ref") }?.text("name") ?: route.text("to_ref")
                    Text("$from → $to · ${routeData.text("mode")} · ${routeData.text("distance_meters")} 米 · 约 ${routeData.number("duration_seconds")?.div(60) ?: 0} 分钟", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
            }
            val listedCost = activities.sumOf { it.number("estimated_cost_fen") ?: 0L }
            Text("预览所列活动费用合计：${money(listedCost)}", color = Ink, fontWeight = FontWeight.SemiBold)
            Text("核对结果", style = MaterialTheme.typography.titleMedium, color = Ink)
            if (checked.isNotEmpty()) {
                Text("已检查", color = DeepTeal, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                checked.forEach { Text("• ${it.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
            }
            if (missing.isNotEmpty()) {
                Text("仍需核实", color = SoftOrange, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                missing.forEach { Text("• ${it.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
            }
            if (blockers.isNotEmpty()) {
                Text("采用前需要解决", color = SoftOrange, fontWeight = FontWeight.SemiBold)
                blockers.forEach { Text("• ${it.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
            }
            if (stale) Text("这份预览已过期或草稿版本变化，请重新核对。", color = SoftOrange, fontWeight = FontWeight.SemiBold)
            if (matchingOperation != null) Text("这份预览已有确认操作：${operationStatus(matchingOperation.text("status"))}。请读取或恢复原操作，不要重复创建。", color = SoftOrange, fontWeight = FontWeight.SemiBold)
            Text("确认只授权上面显示的内容。服务端会在正式采用时再次检查整份日程。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            Button(onClick = { confirmAction = "create_and_adopt"; vm.confirmDraftPromotion("create_and_adopt") }, enabled = !s.busy && !disabled && !stale && coverageComplete && blockers.isEmpty() && matchingOperation == null && activities.isNotEmpty() && confirmAction.isBlank(), modifier = Modifier.fillMaxWidth()) {
                Text("确认创建并采用这份日程")
            }
            OutlinedButton(onClick = { confirmAction = "create_only"; vm.confirmDraftPromotion("create_only") }, enabled = !s.busy && !disabled && !stale && coverageComplete && blockers.isEmpty() && matchingOperation == null && activities.isNotEmpty() && confirmAction.isBlank(), modifier = Modifier.fillMaxWidth()) {
                Text("只创建旅行，日程稍后确认")
            }
            TextButton(onClick = { vm.clearDraftPromotionPreview(); confirmAction = "" }, enabled = !s.busy && confirmAction.isBlank(), modifier = Modifier.fillMaxWidth()) { Text("返回修改日期或草稿") }
            if (confirmAction.isNotBlank()) {
                Text("确认已提交。先读取同一项操作状态；不要创建新的确认操作。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                OutlinedButton(onClick = { vm.refreshDraftPromotions(); confirmAction = "" }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("读取原操作状态") }
            }
        }
    }

    if (s.promotionOperations.isNotEmpty()) {
        AppCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("正式化进度", style = MaterialTheme.typography.titleLarge, color = Ink, modifier = Modifier.weight(1f))
                TextButton(onClick = { confirmAction = ""; vm.refreshDraftPromotions() }, enabled = !s.busy) { Text("读取状态") }
            }
            s.promotionOperations.forEach { operation ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                    Text(operationStatus(operation.text("status")), color = DeepTeal, fontWeight = FontWeight.SemiBold)
                    if (operation.text("error").isNotBlank()) Text(operation.text("error"), color = SoftOrange, fontSize = 12.sp)
                    operation.obj("validation").rows("errors").forEach { Text(it.text("message"), color = SoftOrange, fontSize = 12.sp) }
                    val tripId = operation.text("target_trip_id")
                    if (tripId.isNotBlank()) {
                        Text("正式旅行已创建", color = Ink, fontSize = 12.sp)
                        Button(onClick = { onOpenTrip(tripId) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("打开正式旅行") }
                    }
                    if (s.activePromotion?.text("id") == operation.text("id") && operation.text("status") in setOf("requested", "trip_created", "awaiting_apply", "failed")) {
                        OutlinedButton(onClick = { confirmAction = ""; vm.resumeDraftPromotion() }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("恢复这次原操作") }
                    }
                    HorizontalDivider(color = Mist)
                }
            }
        }
    } else if (prepared == null) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = vm::refreshDraftPromotions, enabled = !s.busy) { Text("读取已有正式化操作") }
        }
    }
}

private fun amountFen(value: String): Long? = if (value.isBlank()) null else runCatching {
    val decimal = BigDecimal(value.trim())
    require(decimal.signum() >= 0)
    decimal.movePointRight(2).longValueExact()
}.getOrNull()

private fun validTime(value: String): Boolean = value.matches(Regex("(?:[01]\\d|2[0-3]):[0-5]\\d"))
private fun money(value: Long?): String = value?.let { "¥${BigDecimal(it).movePointLeft(2).setScale(2)}" } ?: "未设上限"
private fun JsonObject.number(key: String): Long? = this[key]?.jsonPrimitive?.longOrNull
private fun JsonObject.stringArray(key: String): List<String> = (this[key] as? JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
private fun operationStatus(value: String): String = when (value) {
    "requested" -> "已确认，正在准备旅行"
    "trip_created" -> "旅行已创建，等待采用日程"
    "awaiting_apply" -> "旅行已创建，日程待采用"
    "needs_review" -> "情况有变化，需要重新核对"
    "applied" -> "旅行和日程已确认"
    "created" -> "旅行已创建，日程尚未采用"
    "failed" -> "处理未完成，可以恢复"
    "cancelled" -> "本次授权已撤回"
    else -> "状态未知"
}
