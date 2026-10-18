package com.roamsync.app.ui

import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.roamsync.app.BuildConfig
import com.roamsync.app.data.*
import kotlinx.serialization.json.*

@Composable
fun TourismApp(
    s: TourismState,
    vm: TourismViewModel,
    journey: RoamSyncUiState,
    journeyVm: RoamSyncViewModel,
) {
    var tab by rememberSaveable { mutableStateOf("explore") }
    var journeySection by rememberSaveable { mutableStateOf("drafts") }
    var journeyMode by rememberSaveable { mutableStateOf("collection") }
    var journeyDetail by rememberSaveable { mutableStateOf(false) }
    var selectedFormalTripId by rememberSaveable { mutableStateOf<String?>(null) }
    var assistantScopedDay by rememberSaveable { mutableStateOf(false) }
    var placeDrillReturnTab by rememberSaveable { mutableStateOf<String?>(null) }
    var placeDrillDepth by rememberSaveable { mutableIntStateOf(0) }
    var placeDrillPending by rememberSaveable { mutableStateOf(false) }
    val screenStateHolder = rememberSaveableStateHolder()
    val assistantOpen = s.screen == "assistant"
    val placeDrillOverlay = placeDrillDepth > 0 && s.screen in setOf("detail", "map", "route")
    val formalTripOpen = journeyDetail || journey.screen in setOf(AppScreen.DETAIL, AppScreen.NAVIGATION)
    val formalTripReady = formalTripOpen && journey.trip != null &&
        (selectedFormalTripId == null || journey.trip.id == selectedFormalTripId)

    LaunchedEffect(tab, s.screen, s.busy) {
        if (tab == "journeys" && !s.busy && s.screen !in setOf("drafts", "draft-detail", "assistant")) {
            vm.drafts()
        }
    }
    LaunchedEffect(tab, journey.screen, journey.busy, journey.loaded) {
        if (tab == "journeys" && journey.screen == AppScreen.TRIPS && !journey.busy && !journey.loaded) {
            journeyVm.refresh()
        }
    }
    LaunchedEffect(tab, journeyMode, s.screen) {
        if (tab == "journeys" && journeyMode == "draft-create" && s.screen == "draft-detail") {
            journeyMode = "draft-edit"
        } else if (tab == "journeys" && journeyMode == "draft-edit" && s.screen == "drafts") {
            journeyMode = "collection"
        }
    }
    LaunchedEffect(placeDrillPending, s.screen) {
        if (placeDrillPending && s.screen == "detail") placeDrillPending = false
    }

    fun openPlaceDrillIn(id: String) {
        if (placeDrillDepth == 0) placeDrillReturnTab = tab
        placeDrillDepth += 1
        placeDrillPending = true
        vm.openPlace(id)
    }

    fun openAssistant(prompt: String? = null, scopedDay: Boolean = false) {
        assistantScopedDay = scopedDay
        when {
            tab == "journeys" && formalTripReady -> {
                val trip = requireNotNull(journey.trip)
                vm.assistantForTrip(trip.id, trip.destination, if (journey.tab == 3) "execution" else "trip")
            }
            tab == "journeys" && s.screen == "draft-detail" && s.travelDraft != null ->
                vm.assistantForDraft(s.travelDraft.text("id"))
            tab == "explore" && s.screen == "detail" -> vm.assistant(s.place)
            tab == "nearby" && s.nearbySelectedPlace != null -> vm.assistant(s.nearbySelectedPlace)
            else -> vm.assistant()
        }
        if (!prompt.isNullOrBlank()) vm.editDraft(prompt)
    }
    fun closeAssistant() {
        vm.back()
    }

    fun goBack() {
        when {
            assistantOpen -> {
                if (placeDrillPending) {
                    placeDrillDepth = (placeDrillDepth - 1).coerceAtLeast(0)
                    placeDrillPending = false
                    if (placeDrillDepth == 0) {
                        tab = placeDrillReturnTab ?: tab
                        placeDrillReturnTab = null
                    }
                }
                closeAssistant()
            }
            placeDrillDepth > 0 && s.screen in setOf("map", "route") -> vm.back()
            placeDrillDepth > 0 && s.screen == "detail" -> {
                vm.back()
                placeDrillDepth = (placeDrillDepth - 1).coerceAtLeast(0)
                if (placeDrillDepth == 0) {
                    tab = placeDrillReturnTab ?: tab
                    placeDrillReturnTab = null
                }
            }
            tab == "journeys" && s.screen == "draft-detail" -> {
                vm.back()
                if (journeyMode == "draft-edit") journeyMode = "collection"
            }
            tab == "journeys" && journeyMode == "draft-create" -> journeyMode = "collection"
            tab == "journeys" && formalTripOpen -> {
                journeyVm.back()
                if (journey.screen == AppScreen.DETAIL || journey.screen == AppScreen.TRIPS) {
                    journeyDetail = false
                    selectedFormalTripId = null
                }
            }
            tab == "mine" && s.screen in setOf("favorites", "preferences", "settings") -> vm.back()
            tab == "explore" && s.screen != "explore" -> vm.back()
            tab != "explore" -> tab = "explore"
        }
    }

    BackHandler(enabled = true) {
        goBack()
    }

    Scaffold(
        containerColor = Cream,
        topBar = {
            Column(Modifier.statusBarsPadding()) {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 9.dp),
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                ) {
                    val showBack = assistantOpen || placeDrillOverlay ||
                        (tab == "explore" && s.screen !in setOf("explore", "assistant")) ||
                        (tab == "mine" && s.screen in setOf("favorites", "preferences", "settings")) ||
                        (tab == "journeys" && (s.screen == "draft-detail" || formalTripOpen || journeyMode == "draft-create"))
                    if (showBack) {
                        TextButton(onClick = ::goBack) { Text("‹", fontSize = 28.sp, color = DeepTeal) }
                    } else {
                        CompassMark()
                    }
                    Column(Modifier.weight(1f).padding(start = 8.dp)) {
                        Text(
                            when {
                                assistantOpen -> "旅行助手"
                                placeDrillOverlay && s.screen == "detail" -> s.place?.text("name") ?: "地点详情"
                                placeDrillOverlay && s.screen == "map" -> "地点地图"
                                placeDrillOverlay && s.screen == "route" -> "路线预览"
                                tab == "journeys" && formalTripOpen -> if (formalTripReady) "正式旅行" else "正在读取正式行程"
                                tab == "journeys" && s.screen == "draft-detail" -> s.travelDraft?.text("title") ?: "正在筹划"
                                tab == "mine" && s.screen == "favorites" -> "收藏的地点"
                                tab == "mine" && s.screen == "preferences" -> "旅行偏好"
                                tab == "mine" && s.screen == "settings" -> "连接与隐私"
                                tab == "explore" && s.screen == "detail" -> s.place?.text("name") ?: "地点详情"
                                else -> "RoamSync"
                            },
                            fontWeight = FontWeight.SemiBold,
                            color = Ink,
                            fontSize = 17.sp,
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Serif,
                        )
                        Text(
                            when {
                                assistantOpen -> "围绕当前地点、草稿或正式行程继续讨论"
                                placeDrillOverlay && s.screen == "route" -> "路线预览"
                                placeDrillOverlay && s.screen == "map" -> "地点地图"
                                placeDrillOverlay -> "地点详情 · 返回以继续原来的旅程"
                                tab == "explore" && s.screen == "route" -> "路线预览"
                                tab == "explore" && s.screen == "map" -> "地点地图"
                                tab == "explore" -> "TRAVEL, AT YOUR PACE · 探索城市与真实地点"
                                tab == "nearby" -> s.nearbyCenter?.label?.let { "以 $it 为中心，发现附近地点" } ?: "选择地点后查看周边"
                                tab == "journeys" && formalTripOpen -> "此刻和下一站 · 已确认的日程"
                                tab == "journeys" && s.screen == "draft-detail" -> "继续整理这次旅行"
                                tab == "journeys" -> "正在筹划 · 即将出发 · 正在旅行 · 历史旅行"
                                else -> "收藏、偏好与连接"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            maxLines = 1,
                        )
                    }
                    if (assistantOpen) TextButton(onClick = ::goBack, enabled = !s.busy) { Text("完成") }
                    else TextButton(onClick = { openAssistant() }, enabled = !journey.busy && !s.busy) {
                        Text("✧ 旅行助手", color = DeepTeal, fontWeight = FontWeight.SemiBold)
                    }
                }
                if ((!assistantOpen && (s.busy || journey.busy))) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Teal)
            }
        },
        bottomBar = {
            if (!assistantOpen && !placeDrillOverlay) NavigationBar(containerColor = Paper) {
                listOf("explore" to "探索", "nearby" to "附近", "journeys" to "旅程", "mine" to "我的").forEach { (id, label) ->
                    NavigationBarItem(
                        selected = tab == id,
                        onClick = {
                            tab = id
                            if (id == "journeys" && journey.screen == AppScreen.TRIPS) journeyVm.refresh()
                        },
                        icon = { if (id == "explore") CompassMark(markSize = 24.dp, background = Color.Transparent, foreground = if (tab == id) DeepTeal else MaterialTheme.colorScheme.onSurfaceVariant) else Text(when (id) { "nearby" -> "◎"; "journeys" -> "◷"; else -> "○" }, fontSize = 18.sp) },
                        label = { Text(label) },
                        colors = NavigationBarItemDefaults.colors(selectedIconColor = DeepTeal, selectedTextColor = DeepTeal, indicatorColor = Mist),
                    )
                }
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (placeDrillOverlay) {
                when (s.screen) {
                    "detail" -> PlaceNative(s, vm)
                    "route", "map" -> TourismMap(s, vm)
                }
            } else if (assistantOpen) {
                screenStateHolder.SaveableStateProvider("shared-assistant") {
                    AssistantNative(s, vm, journey, journeyVm, assistantScopedDay, onOpenPlace = ::openPlaceDrillIn)
                }
            } else when (tab) {
                    "explore" -> screenStateHolder.SaveableStateProvider("explore") {
                        if (s.screen != "explore") s.error?.let { ErrorNotice(it, !s.busy, vm::retry) }
                        when (s.screen) {
                            "detail" -> PlaceNative(s, vm)
                            "route", "map" -> TourismMap(s, vm)
                            else -> ExploreNative(s, vm)
                        }
                    }
                    "nearby" -> screenStateHolder.SaveableStateProvider("nearby") { NearbyNative(s, vm, onOpenPlace = ::openPlaceDrillIn) }
                    "journeys" -> {
                        screenStateHolder.SaveableStateProvider("journeys") {
                            when {
                                formalTripReady -> FormalJourneyNative(
                                    journey,
                                    journeyVm,
                                    onAskAssistant = { prompt, scopedDay -> openAssistant(prompt, scopedDay) },
                                )
                                formalTripOpen -> QuietState("正在打开正式行程", "正在读取已保存的旅行安排。", Modifier.padding(18.dp))
                                s.screen == "draft-detail" -> DraftNative(s, vm, onOpenTrip = { id ->
                                    journeyVm.openTrip(id)
                                    journeyDetail = true
                                    selectedFormalTripId = id
                                    tab = "journeys"
                                })
                                journeyMode == "draft-create" -> JourneyDraftCreationNative(s, vm) {
                                    journeyMode = "collection"
                                    journeySection = "drafts"
                                }
                                else -> JourneyCollectionNative(
                                    tourism = s,
                                    journey = journey,
                                    section = journeySection,
                                    onSectionChange = { journeySection = it },
                                    onCreateDraft = { journeyMode = "draft-create" },
                                    onOpenDraft = { id -> journeyMode = "collection"; vm.openDraft(id) },
                                    onOpenTrip = { id -> journeyVm.openTrip(id); journeyDetail = true; selectedFormalTripId = id },
                                    onRefresh = { if (!s.busy) vm.drafts(); if (!journey.busy) journeyVm.refresh() },
                                )
                            }
                        }
                    }
                    else -> screenStateHolder.SaveableStateProvider("mine") {
                        when (s.screen) {
                            "favorites" -> FavoritesNative(s, vm, onOpenPlace = ::openPlaceDrillIn)
                            "preferences" -> PreferencesNative(s, vm)
                            "settings" -> ConnectionNative(s, vm)
                            else -> MineNative(s, vm, onJourneys = {
                                tab = "journeys"
                                journeySection = "drafts"
                                journeyMode = "collection"
                                if (journey.screen == AppScreen.TRIPS) journeyVm.refresh()
                            })
                        }
                    }
                }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun ExploreNative(s: TourismState, vm: TourismViewModel) {
    var category by rememberSaveable { mutableStateOf(s.category) }
    var locationSheetOpen by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(s.category) { category = s.category }
    val hasSearchInput = s.city.isNotBlank() || s.query.isNotBlank()
    Box(Modifier.fillMaxSize()) {
        LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp), modifier = Modifier.padding(top = 2.dp)) {
                    Text("GO WHERE CURIOSITY LEADS", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.5.sp)
                    Text("下一站，慢慢找。", style = MaterialTheme.typography.headlineMedium, color = Ink)
                }
            }
            item {
                AppCard {
                    OutlinedTextField(
                        value = s.query,
                        onValueChange = vm::editQuery,
                        label = { Text("想去哪里") },
                        placeholder = { Text("输入城市，或具体地点名称") },
                        leadingIcon = { Text("⌕", color = DeepTeal, fontSize = 20.sp) },
                        singleLine = true,
                        enabled = !s.busy,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        OutlinedButton(onClick = { locationSheetOpen = true }, enabled = !s.busy, modifier = Modifier.weight(1f)) {
                            Text(if (s.city.isBlank()) "＋ 添加所在城市" else "所在城市 · ${s.city}", maxLines = 1)
                        }
                        Button(
                            onClick = { if (category != s.category) vm.category(category) else vm.search() },
                            enabled = !s.busy,
                        ) { Text(if (s.busy) "寻找中" else "搜索") }
                    }
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("" to "全部", "attraction" to "景点", "food" to "餐饮", "lodging" to "住宿").forEach { (value, label) ->
                            FilterChip(selected = category == value, onClick = {
                                category = value
                                if (hasSearchInput) vm.category(value)
                            }, enabled = !s.busy, label = { Text(label) })
                        }
                    }
                    Text("地点来自真实地图搜索；未输入城市时，可直接搜索唯一城市名。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
            }
            s.error?.let { item { ErrorNotice(it, !s.busy, vm::retry) } }
            if (s.notice != null) item { Text(s.notice, color = DeepTeal) }
            if (s.places.isNotEmpty()) item {
                PageHeading("YOUR EXPLORATION", "找到 ${s.places.size} 个地点", "地点来自高德真实搜索；缺少的信息会保留为未知。")
            }
            if (s.places.isEmpty() && !s.busy) item {
                QuietState(
                    "从好奇开始",
                    "先输入城市名，或补充地点所在城市，再搜索真实地点。",
                )
            }
            items(s.places, key = { it.placeId() }) { place -> PlaceTile(place, vm) { vm.openPlace(place.placeId()) } }
            if (s.places.isNotEmpty()) item { Text("酒店实时库存与房价暂不支持；价格与路线均为参考信息。", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        if (locationSheetOpen) ModalBottomSheet(onDismissRequest = { locationSheetOpen = false }) {
            Column(Modifier.fillMaxWidth().imePadding().padding(horizontal = 20.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("搜索城市", style = MaterialTheme.typography.titleLarge, color = Ink)
                Text("搜索具体地点时填写所在城市；如果只输入城市名，也可以直接搜索。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                OutlinedTextField(
                    value = s.city,
                    onValueChange = vm::editCity,
                    label = { Text("所在城市") },
                    placeholder = { Text("例如：成都") },
                    singleLine = true,
                    enabled = !s.busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(onClick = { locationSheetOpen = false }, modifier = Modifier.fillMaxWidth()) { Text("完成") }
                Spacer(Modifier.height(12.dp))
            }
        }
    }
}

@Composable internal fun PlaceTile(place: JsonObject, vm: TourismViewModel, open: () -> Unit) {
    AppCard(Modifier.clickable(onClick = open)) {
        ReviewedPlacePhotos(place, vm::reviewedImageBytes)
        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(place.text("name"), style = MaterialTheme.typography.titleLarge, color = Ink)
                Text("${place.text("city")} · ${categoryName(place.text("category"))}", fontSize = 12.sp, color = DeepTeal)
            }
            Text("查看  →", color = DeepTeal, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
        }
        Text(place.text("address").ifBlank { "地址暂缺" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Text("高德地点 · ${if (place.obj("source").text("freshness") == "stale") "缓存信息" else "当前查询"}", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
internal fun categoryName(value: String) = when(value) { "attraction" -> "景点"; "food" -> "餐饮"; "lodging" -> "住宿"; else -> "地点" }

@Composable private fun FavoritesNative(s: TourismState, vm: TourismViewModel, onOpenPlace: (String) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { PageHeading("Saved places", "留住喜欢的地方。", "收藏已保存，下次打开可以继续查看。") }
        if (s.favorites.isEmpty() && !s.busy) item { QuietState("这里还没有收藏", "探索地点后，打开详情并点按“收藏地点”。") }
        items(s.favorites, key = { it.placeId() }) { place -> PlaceTile(place, vm) { onOpenPlace(place.placeId()) } }
    }
}

@Composable private fun PreferencesNative(s: TourismState, vm: TourismViewModel) {
    val categories = listOf("attraction" to "风景名胜", "food" to "餐饮美食", "lodging" to "住宿")
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("我的旅行偏好", fontSize = 26.sp, fontWeight = FontWeight.Bold) }
        item { Text("只使用你在这里明确保存的选择，按地点名称与类别匹配排序。") }
        item {
            OutlinedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    categories.forEach { (value, label) ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Checkbox(
                                checked = value in s.preferences.preferredCategories,
                                onCheckedChange = { vm.togglePreferenceCategory(value, it) },
                                enabled = !s.busy,
                            )
                            Text(label)
                        }
                    }
                }
            }
        }
        item { OutlinedTextField(
            value = s.preferenceInterests,
            onValueChange = vm::editPreferenceInterests,
            label = { Text("兴趣关键词（逗号分隔）") },
            placeholder = { Text("例如：博物馆，茶馆") },
            supportingText = { Text("最多8个，每个不超过30字") },
            enabled = !s.busy,
            modifier = Modifier.fillMaxWidth(),
        ) }
        item { Button(onClick = vm::savePreferences, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("保存旅行偏好") } }
        s.notice?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
        item { Text("保存后使用顶部“刷新”从服务重新读取，或离开此页后重新打开。", fontSize = 12.sp, color = MaterialTheme.colorScheme.secondary) }
    }
}

@Composable private fun PlaceNative(s: TourismState, vm: TourismViewModel) {
    val place = s.place ?: return
    LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { PageHeading("A place to remember", place.text("name"), "${place.text("city")} · ${categoryName(place.text("category"))}") }
        item { ReviewedPlacePhotos(place, vm::reviewedImageBytes, gallery = true) }
        item { AppCard {
            Text(place.text("address").ifBlank { "地址暂无" }, style = MaterialTheme.typography.titleMedium, color = Ink)
            HorizontalDivider(color = Color(0xFFE8E6DC))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column { Text("评分", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp); Text(place.text("rating").ifBlank { "未知" }, fontWeight = FontWeight.SemiBold) }
                Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                    Text(if (place.text("category") == "lodging") "价格" else "人均参考", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                    Text(if (place.text("category") == "lodging") "实时房价暂不支持" else place.obj("price").text("amount").ifBlank { "未知" } + " 元", fontWeight = FontWeight.SemiBold)
                }
            }
            Text("价格为地点参考信息，不是实时报价。", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } }
        item { PlaceExperienceCard(place) }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::toggleFavorite, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text(if (s.favorite) "已收藏 · 取消" else "收藏地点") }
            OutlinedButton(onClick = { vm.assistant(place) }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("围绕此地问 AI") }
        } }
        item { AppCard {
            Text("去这里，或从这里出发", style = MaterialTheme.typography.titleLarge, color = Ink)
            OutlinedButton(onClick = vm::map, modifier = Modifier.fillMaxWidth()) { Text("查看地图") }
            OutlinedButton(onClick = { vm.setOrigin(place) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text(if (s.origin?.placeId() == place.placeId()) "已设为路线起点" else "设为路线起点") }
            Text("路线起点：${s.origin?.text("name") ?: "尚未选择"}", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { vm.route("walk") }, enabled = !s.busy && s.origin != null, modifier = Modifier.weight(1f)) { Text("步行路线") }
                OutlinedButton(onClick = { vm.route("driving") }, enabled = !s.busy && s.origin != null, modifier = Modifier.weight(1f)) { Text("驾车路线") }
            }
        } }
        s.notice?.let { item { Text(it, color = DeepTeal) } }
        item { Text("地点资料来自高德；信息可能缺失或过期。已展示照片为逐图审核的 Commons 授权素材。", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun PlaceExperienceCard(place: JsonObject) {
    val experience = place.obj("experience")
    AppCard(color = Color(0xFFF0F4EC)) {
        Text("到访体验", style = MaterialTheme.typography.titleLarge, color = Ink)
        if (experience.text("summary").isNotBlank()) {
            Text(experience.text("summary"), color = Ink, lineHeight = 22.sp)
            val source = experience.text("source_title")
            if (source.isNotBlank()) Text("资料来源：$source${experience.text("reviewed_at").takeIf(String::isNotBlank)?.let { " · 核对于 $it" }.orEmpty()}", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            experience.obj("attributes").forEach { (key, value) ->
                val detail = when (value) { is JsonPrimitive -> value.contentOrNull.orEmpty(); is JsonObject -> value.text("label").ifBlank { value.text("value") }; else -> "" }
                if (detail.isNotBlank()) Text("${experienceLabelText(key)}：$detail", fontSize = 12.sp)
            }
        } else {
            Text("暂无可靠的地点体验资料。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun experienceLabelText(value: String): String = when (value) {
    "outdoor" -> "户外体验"; "indoor" -> "室内体验"; "shaded" -> "遮阴情况"; "accessibility" -> "无障碍"
    "family_friendly" -> "适合家庭"; "crowd_level" -> "人流情况"; "best_time" -> "建议时段"; else -> value.replace('_', ' ')
}

@Composable private fun AssistantNative(
    s: TourismState,
    vm: TourismViewModel,
    journey: RoamSyncUiState,
    journeyVm: RoamSyncViewModel,
    scopedDay: Boolean,
    onOpenPlace: (String) -> Unit,
) {
    LaunchedEffect(s.assistantTripId, journey.trip?.id) {
        if (s.assistantTripId != null && s.assistantTripId == journey.trip?.id) journeyVm.refreshTripPlan()
    }
    Column(Modifier.fillMaxSize().imePadding().padding(horizontal = 16.dp)) {
        Text("统一旅行 AI", fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text("当前讨论：${s.discussing?.text("name") ?: s.travelDraft?.text("title") ?: journey.trip?.title ?: s.city} · AI 提供建议；正式保存需要你明确确认", fontSize = 12.sp)
        val messages = s.session?.rows("messages").orEmpty()
        val scroll = rememberLazyListState()
        LaunchedEffect(messages.size, s.busy) { if (messages.isNotEmpty()) scroll.animateScrollToItem(messages.lastIndex) }
        LazyColumn(Modifier.weight(1f), state = scroll, verticalArrangement = Arrangement.spacedBy(14.dp), contentPadding = PaddingValues(vertical = 16.dp)) {
            if (messages.isEmpty()) item { Text("告诉我你想去哪里，或从地点详情点击“问问这里”。") }
            items(messages, key = { it.text("id") }) { message ->
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("你：${message.text("user")}", fontWeight = FontWeight.Bold)
                    Text(message.text("assistant"))
                    message.rows("place_cards").forEach { card -> val ref = card.obj("place")
                        OutlinedButton(onClick = { onOpenPlace(ref.text("place_id")) }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) { Text("打开地点：${ref.text("name")}") }
                        OutlinedButton(onClick = { vm.assistantRoute(ref.text("place_id")) }, enabled = !s.busy) { Text("从已选起点步行到这里") }
                    }
                    val route = message.obj("read_tools").obj("route")
                    if (route.text("status") == "available") {
                        Text("真实高德路线 · ${route.obj("result").text("distance_meters")}米 · 预计${route.obj("result").text("duration_seconds").toDoubleOrNull()?.div(60)?.toInt() ?: 0}分钟")
                        OutlinedButton(onClick = { vm.openAssistantRoute(message) }, enabled = !s.busy) { Text("打开路线地图") }
                    } else if (route.isNotEmpty()) Text("路线暂不可用，可点击地点的步行快捷入口重试。")
                }
            }
            if (s.busy) item { Text("正在读取真实地点并整理建议…") }
        }
        if (journey.trip != null && s.assistantTripId == journey.trip.id) {
            AppCard(color = Mist) {
                Text("正式行程操作", style = MaterialTheme.typography.titleMedium, color = Ink)
                Text("AI 对话只读当前行程。需要调整时，可在此提交候选方案；只有你确认后才会写入正式行程。", fontSize = 12.sp)
                OutlinedButton(onClick = { journeyVm.requestTripPlan(s.draft, scopedDay) }, enabled = !s.busy && !journey.busy && s.draft.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("准备正式行程候选方案") }
                JourneyPlanProposalCard(journey, journeyVm)
            }
        }
        OutlinedTextField(s.draft, vm::editDraft, label = { Text("聊聊旅行") }, maxLines = 4, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(onClick = vm::send, enabled = !s.busy && s.draft.isNotBlank(), modifier = Modifier.weight(1f)) { Text("发送讨论") }
            if (journey.trip != null && s.assistantTripId == journey.trip.id) OutlinedButton(onClick = { journeyVm.requestTripPlan(s.draft, scopedDay) }, enabled = !s.busy && !journey.busy && s.draft.isNotBlank(), modifier = Modifier.weight(1f)) { Text("生成候选") }
        }
    }
}

@Composable private fun ConnectionNative(s: TourismState, vm: TourismViewModel) {
    var url by rememberSaveable(s.connection) { mutableStateOf(s.connection) }
    var code by remember { mutableStateOf("") }
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("连接统一服务", fontSize = 24.sp, fontWeight = FontWeight.Bold) }
        item { Text("USB：由电脑执行 adb reverse，将手机本机端口连接到隔离服务。无需在 APK 保存服务器密钥。") }
        item { OutlinedTextField(url, { url = it }, label = { Text("服务根地址") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        item { OutlinedTextField(code, { code = it }, label = { Text("一次性配对码（USB Web 代理可留空）") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        item { Button(onClick = { vm.saveConnection(url, code); code = "" }, enabled = !s.busy) { Text("保存并连接") } }
        item { OutlinedButton(onClick = vm::openPreferences, enabled = !s.busy) { Text("管理旅行偏好") } }
        item { OutlinedButton(onClick = vm::disconnect, enabled = !s.busy) { Text("撤销临时授权") } }
        s.notice?.let { item { Text(it) } }
        item { Text("配对授权仅保存在内存，重启或到期后需要重新配对。不要将无可信访问边界的服务公开。") }
    }
}

@android.annotation.SuppressLint("SetJavaScriptEnabled")
@Composable private fun TourismMap(s: TourismState, vm: TourismViewModel) {
    val destination = s.place ?: return
    val route = s.route.takeIf { s.screen == "route" }
    val data = buildJsonObject {
        val location = destination.obj("location")
        put("center", buildJsonArray { add(location["longitude"] ?: JsonPrimitive(120.15)); add(location["latitude"] ?: JsonPrimitive(30.25)) })
        put("points", buildJsonArray { (if (route != null) listOfNotNull(s.origin, destination) else listOf(destination)).forEach { p -> add(buildJsonObject {
            put("name", p.text("name")); put("lng", p.obj("location")["longitude"]!!); put("lat", p.obj("location")["latitude"]!!)
        }) } })
        put("paths", buildJsonArray { if (route != null) add(buildJsonArray { route.rows("path").forEach { p -> add(buildJsonArray { add(p["longitude"]!!); add(p["latitude"]!!) }) } }) })
    }.toString()
    var failed by remember(data) { mutableStateOf(false) }
    Column(Modifier.fillMaxSize()) {
        Text(if (route == null) destination.text("name") else "${s.origin?.text("name")} → ${destination.text("name")}", Modifier.padding(16.dp), fontWeight = FontWeight.Bold)
        if (route != null) Text("${route.text("distance_meters")} 米 · 约 ${(route.text("duration_seconds").toDoubleOrNull()?.div(60)?.toInt()) ?: 0} 分钟 · 高德真实${if (s.routeMode == "walk") "步行" else "驾车"}路线（估计）", Modifier.padding(horizontal = 16.dp))
        if (BuildConfig.AMAP_WEB_KEY.isBlank()) Text("未配置地图公钥；真实路线距离与用时仍可使用。", Modifier.padding(16.dp))
        else if (failed) Column(Modifier.padding(20.dp)) { Text("地图加载失败，请检查网络后重试"); Button(onClick = { failed = false }) { Text("重试地图") } }
        else AndroidView(factory = { ctx -> WebView(ctx).apply {
            settings.javaScriptEnabled = true; settings.domStorageEnabled = true; settings.allowFileAccess = false; settings.allowContentAccess = false
            webViewClient = object : WebViewClient() { override fun onReceivedError(view: WebView?, request: android.webkit.WebResourceRequest?, error: android.webkit.WebResourceError?) { if (request?.isForMainFrame == true) failed = true } }
            loadDataWithBaseURL("https://roamsync.local/", mapDocument(data), "text/html", "UTF-8", null); tag = data
        } }, update = { if (it.tag != data) { it.loadDataWithBaseURL("https://roamsync.local/", mapDocument(data), "text/html", "UTF-8", null); it.tag = data } }, onRelease = { it.stopLoading(); it.destroy() }, modifier = Modifier.fillMaxWidth().weight(1f))
        Text("地点与路线使用 GCJ02 坐标；不是实时 GPS 导航。", Modifier.padding(16.dp), fontSize = 12.sp)
    }
}
