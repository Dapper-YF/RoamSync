package com.roamsync.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.roamsync.app.data.*
import com.roamsync.app.data.remote.TravelPreferences
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.json.*
import java.util.UUID

internal fun draftActionNotice(action: String, value: JsonObject, requestId: String): String = when (action) {
    "save" -> "草稿已保存"
    "cancel" -> "草稿已取消，可恢复"
    "restore" -> "草稿已恢复"
    "cancel-run" -> "生成已取消，原方案保留"
    else -> when (value.rows("runs").firstOrNull { it.text("request_id") == requestId }?.text("status")) {
        "completed" -> "草稿内容已更新，请查看生成记录"
        "failed", "interrupted" -> "本次生成未完成，原方案保留；可重试或修改要求。"
        "cancelled" -> "生成已取消，原方案保留"
        else -> "生成进行中，可刷新查看状态。"
    }
}

data class TourismState(
    val screen: String = "explore", val city: String = "", val query: String = "", val category: String = "",
    val places: List<JsonObject> = emptyList(), val favorites: List<JsonObject> = emptyList(),
    val preferences: TravelPreferences = TravelPreferences(), val preferenceInterests: String = "",
    val place: JsonObject? = null, val favorite: Boolean = false, val origin: JsonObject? = null,
    val route: JsonObject? = null, val routeMode: String = "walk", val session: JsonObject? = null,
    val discussing: JsonObject? = null, val draft: String = "", val busy: Boolean = false,
    val error: String? = null, val notice: String? = null, val connection: String = "",
    val travelDrafts: List<JsonObject> = emptyList(), val travelDraft: JsonObject? = null,
    val draftRequirements: String = "",
    val draftTitle: String = "", val draftDayCount: Int = 3,
    val promotionPreview: JsonObject? = null, val promotionOperations: List<JsonObject> = emptyList(),
    val activePromotion: JsonObject? = null,
    val draftEffectiveRequirements: JsonObject? = null,
    val draftPlaces: List<JsonObject> = emptyList(),
    val draftPlaceDetails: Map<String, JsonObject> = emptyMap(),
    val assistantTripId: String? = null, val assistantDraftId: String? = null,
    val assistantDraftVersion: Int? = null, val assistantSurface: String = "assistant",
    val nearbyCenter: NearbyCenter? = null, val nearbyCenterCandidates: List<JsonObject> = emptyList(),
    val nearbyPlaces: List<JsonObject> = emptyList(), val nearbySelectedPlace: JsonObject? = null,
    val nearbyQuery: String = "", val nearbyCategory: String = "", val nearbyRadiusMeters: Int = 3000,
    val nearbyMinRating: Double? = null, val nearbyMaxFoodPriceYuan: Double? = null,
    val nearbyIncludeUnknown: Boolean = true, val nearbyRoute: JsonObject? = null,
    val nearbyRouteMode: String = "walk", val comparePlaceIds: Set<String> = emptySet(),
    val comparedPlaces: List<JsonObject> = emptyList(),
)

/** User-selected GCJ02 point. The source records how the point was selected. */
data class NearbyCenter(val longitude: Double, val latitude: Double, val label: String, val source: String)

@HiltViewModel class TourismViewModel @Inject constructor(private val repo: TourismRepository,
    private val endpoint: TourismEndpoint, private val saved: SavedStateHandle) : ViewModel() {
    private val mutable = MutableStateFlow(TourismState(
        connection = endpoint.url(),
        city = saved["city"] ?: "", query = saved["query"] ?: "", category = saved["category"] ?: "",
        draft = saved["assistantDraftText"] ?: "", draftRequirements = saved["draftRequirements"] ?: "",
        draftTitle = saved["draftTitle"] ?: "", draftDayCount = saved["draftDayCount"] ?: 3,
        nearbyQuery = saved["nearbyQuery"] ?: "", nearbyCategory = saved["nearbyCategory"] ?: "",
        nearbyRadiusMeters = saved["nearbyRadiusMeters"] ?: 3000,
        nearbyMinRating = saved["nearbyMinRating"], nearbyMaxFoodPriceYuan = saved["nearbyMaxFoodPriceYuan"],
        nearbyIncludeUnknown = saved["nearbyIncludeUnknown"] ?: true,
        nearbyCenter = saved.get<String>("nearbyCenter")?.let { runCatching {
            val parts = it.split('|', limit = 4)
            if (parts.size != 4 || parts[3] !in setOf("verified_place", "manual_map")) null
            else NearbyCenter(parts[0].toDouble(), parts[1].toDouble(), parts[2], parts[3])
        }.getOrNull() },
    ))
    val state = mutable.asStateFlow()
    private val history = mutableListOf<String>()
    private var retry: (() -> Unit)? = null
    private var pendingMessage: Pair<String, String>? = null
    private var pendingPromotion: Pair<String, String>? = null
    private var pendingDraftRun: Pair<String, String>? = null
    init {
        viewModelScope.launch {
            state.collect { s ->
                saved["city"] = s.city; saved["query"] = s.query; saved["category"] = s.category
                saved["assistantDraftText"] = s.draft.take(4000)
                saved["draftRequirements"] = s.draftRequirements.take(3000)
                saved["draftTitle"] = s.draftTitle.take(200); saved["draftDayCount"] = s.draftDayCount
                saved["nearbyQuery"] = s.nearbyQuery; saved["nearbyCategory"] = s.nearbyCategory
                saved["nearbyRadiusMeters"] = s.nearbyRadiusMeters
                saved["nearbyMinRating"] = s.nearbyMinRating; saved["nearbyMaxFoodPriceYuan"] = s.nearbyMaxFoodPriceYuan
                saved["nearbyIncludeUnknown"] = s.nearbyIncludeUnknown
                saved["nearbyCenter"] = s.nearbyCenter?.takeIf { it.source != "foreground_location" }
                    ?.let { "${it.longitude}|${it.latitude}|${it.label.replace('|', ' ').take(100)}|${it.source}" }
                s.place?.placeId()?.takeIf(String::isNotBlank)?.let { saved["selectedPlaceId"] = it }
                s.nearbySelectedPlace?.placeId()?.takeIf(String::isNotBlank)?.let { saved["nearbySelectedPlaceId"] = it }
                saved["comparedPlaceIds"] = s.comparedPlaces.map { it.placeId() }.filter(String::isNotBlank).joinToString(",")
                s.travelDraft?.text("id")?.takeIf(String::isNotBlank)?.let { saved["selectedDraftId"] = it }
            }
        }
        // Opening exploration is local and does not force pairing, a preset
        // destination, a Trip or a location request. Search starts on user action.
    }
    private fun work(action: suspend () -> Unit) {
        if (mutable.value.busy) return
        viewModelScope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            try { action() } catch (e: Exception) { mutable.update { it.copy(error = e.message ?: "连接失败，请重试") } }
            finally { mutable.update { it.copy(busy = false) } }
        }
    }
    fun editCity(value: String) { mutable.update { it.copy(city = value) } }
    suspend fun reviewedImageBytes(relativeUrl: String): ByteArray = repo.reviewedImageBytes(relativeUrl)
    fun editQuery(value: String) { mutable.update { it.copy(query = value) } }
    fun editDraft(value: String) { mutable.update { it.copy(draft = value) } }
    fun editDraftRequirements(value: String) { mutable.update { it.copy(draftRequirements = value.take(3000)) } }
    fun editDraftTitle(value: String) { mutable.update { it.copy(draftTitle = value.take(200)) } }
    fun editDraftDayCount(value: Int) { mutable.update { it.copy(draftDayCount = value.coerceIn(1, 14)) } }
    fun drafts() { retry = ::drafts; work {
        val values = repo.drafts(); go("drafts"); mutable.update { it.copy(travelDrafts = values) }
    } }
    fun openDraft(id: String) { retry = { openDraft(id) }; work {
        val value = repo.draft(id); val operations = repo.draftPromotions(id)
        val effective = repo.draftRequirements(id); go("draft-detail")
        mutable.update { it.copy(travelDraft = value, travelDrafts = cachedDrafts(it.travelDrafts, value),
            draftRequirements = value.text("requirements"), draftTitle = value.text("title"),
            draftDayCount = value["day_count"]?.jsonPrimitive?.intOrNull ?: 3,
            promotionOperations = operations, activePromotion = operations.firstOrNull(), promotionPreview = null,
            draftEffectiveRequirements = effective) }
    } }
    fun createDraft() = createDraft(mutable.value.draftTitle, mutable.value.draftDayCount, mutable.value.draftRequirements)
    fun createDraft(title: String, dayCount: Int) = createDraft(title, dayCount, mutable.value.draftRequirements)
    fun createDraft(title: String, dayCount: Int, requirements: String) { retry = { createDraft(title, dayCount, requirements) }; work {
        val s = mutable.value; require(s.city.isNotBlank()) { "请填写城市" }
        require(dayCount in 1..14) { "草稿天数须在 1–14 天之间" }
        val finalTitle = title.trim().ifBlank { "${s.city.trim()}${dayCount}日自由草稿" }
        require(finalTitle.length <= 200) { "草稿标题不能超过 200 字" }
        val value = repo.createDraft(s.city, finalTitle, dayCount, requirements); go("draft-detail")
        mutable.update { it.copy(travelDraft = value, travelDrafts = cachedDrafts(it.travelDrafts, value),
            draftTitle = finalTitle, draftDayCount = dayCount, draftRequirements = requirements,
            notice = "草稿已创建，可生成内容；尚未创建正式旅行。") }
    } }
    fun refreshDraftRequirements() { retry = ::refreshDraftRequirements; work {
        val source = requireNotNull(mutable.value.travelDraft) { "请先打开草稿" }
        val effective = repo.draftRequirements(source.text("id"))
        mutable.update { it.copy(draftEffectiveRequirements = effective) }
    } }
    fun revokeDraftRequirement(requirementId: String, dayIndex: Int? = null) {
        retry = { refreshDraftRequirements() }
        work {
            val source = requireNotNull(mutable.value.travelDraft) { "请先打开草稿" }
            val updated = repo.revokeDraftRequirement(source, requirementId, dayIndex)
            val effective = repo.draftRequirements(updated.text("id"))
            mutable.update { it.copy(travelDraft = updated,
                travelDrafts = cachedDrafts(it.travelDrafts, updated), draftEffectiveRequirements = effective,
                promotionPreview = null, notice = "已撤销所选要求，草稿版本已刷新") }
        }
    }
    fun searchDraftPlaces(city: String, query: String) { retry = { searchDraftPlaces(city, query) }; work {
        require(city.isNotBlank() && query.isNotBlank()) { "请填写城市和地点关键词" }
        val places = repo.search(city.trim(), query.trim(), "")
        mutable.update { it.copy(draftPlaces = places) }
    } }
    fun loadDraftPlaceDetail(placeId: String) { retry = { loadDraftPlaceDetail(placeId) }; work {
        require(placeId.isNotBlank()) { "地点身份缺失" }
        val place = repo.detail(placeId)
        require(place.placeId() == placeId) { "地点身份与详情不一致" }
        mutable.update { it.copy(draftPlaceDetails = it.draftPlaceDetails + (placeId to place)) }
    } }
    fun draftAction(action: String) {
        val source = mutable.value.travelDraft ?: return
        val requirements = mutable.value.draftRequirements
        val requestId = UUID.randomUUID().toString()
        fun execute() { work {
            val value = repo.draftAction(source, action, requirements, requestId)
            mutable.update { it.copy(travelDraft = value, travelDrafts = cachedDrafts(it.travelDrafts, value), draftRequirements = value.text("requirements"), notice = draftActionNotice(action, value, requestId)) }
        } }
        retry = ::execute
        execute()
    }
    fun runDraft(requirements: String, targetDayIndex: Int? = null) {
        retry = { runDraft(requirements, targetDayIndex) }
        work {
            val source = requireNotNull(mutable.value.travelDraft) { "请先打开草稿" }
            val dayCount = source["day_count"]?.jsonPrimitive?.intOrNull ?: error("草稿天数缺失")
            require(targetDayIndex == null || targetDayIndex in 1..dayCount) { "目标日期超出草稿范围" }
            val fingerprint = "${source.text("id")}|${source["version"]}|$targetDayIndex|${requirements.trim()}"
            if (pendingDraftRun?.first != fingerprint) pendingDraftRun = fingerprint to UUID.randomUUID().toString()
            val requestId = requireNotNull(pendingDraftRun).second
            val updated = try { repo.runDraft(source, requirements, targetDayIndex, requestId) }
                catch (e: Exception) {
                    val observed = runCatching { repo.draft(source.text("id")) }.getOrNull()
                    if (observed == null || observed.rows("runs").none { it.text("request_id") == requestId }) throw e
                    observed
                }
            pendingDraftRun = null
            mutable.update { it.copy(travelDraft = updated, travelDrafts = cachedDrafts(it.travelDrafts, updated),
                draftRequirements = updated.text("requirements"), promotionPreview = null,
                notice = draftActionNotice("runs", updated, requestId)) }
        }
    }
    fun editSelectedDraft(title: String, requirements: String, plan: JsonElement?) {
        val source = mutable.value.travelDraft ?: return
        retry = { editSelectedDraft(title, requirements, plan) }
        work {
            val updated = repo.editDraft(source, title, requirements, plan)
            mutable.update { it.copy(travelDraft = updated, travelDrafts = cachedDrafts(it.travelDrafts, updated),
                draftTitle = updated.text("title"), draftRequirements = updated.text("requirements"),
                promotionPreview = null, notice = "草稿修改已保存；正式旅行尚未变化") }
        }
    }
    fun previewDraftPromotion(startDate: String, totalBudgetFen: Long?, dailyBudgetFen: Long?,
        transportMode: String = "walk", durationMinutes: Int = 90, unknownCostEstimateFen: Long = 10000,
        dailyStartTime: String = "09:00", dailyEndTime: String = "21:00", maxWalkingMinutes: Int = 60) {
        retry = { previewDraftPromotion(startDate, totalBudgetFen, dailyBudgetFen, transportMode,
            durationMinutes, unknownCostEstimateFen, dailyStartTime, dailyEndTime, maxWalkingMinutes) }
        work {
            val source = requireNotNull(mutable.value.travelDraft) { "请先打开草稿" }
            require(transportMode in setOf("walk", "driving")) { "交通方式无效" }
            require(totalBudgetFen == null && dailyBudgetFen == null ||
                totalBudgetFen != null && dailyBudgetFen != null && totalBudgetFen > 0 &&
                    dailyBudgetFen > 0 && dailyBudgetFen <= totalBudgetFen) {
                "总预算和每日预算须一起填写，且每日预算不能超过总预算"
            }
            val options = buildJsonObject {
                put("start_date", startDate); put("total_budget_fen", totalBudgetFen?.let(::JsonPrimitive) ?: JsonNull)
                put("daily_budget_fen", dailyBudgetFen?.let(::JsonPrimitive) ?: JsonNull)
                put("transport_mode", transportMode); put("duration_minutes", durationMinutes)
                put("unknown_cost_estimate_fen", unknownCostEstimateFen)
                put("daily_start_time", dailyStartTime); put("daily_end_time", dailyEndTime)
                put("max_walking_minutes", maxWalkingMinutes)
            }
            val prepared = repo.previewDraftPromotion(source, options)
            mutable.update { it.copy(promotionPreview = prepared, notice = "正式旅行预览已生成；请核对覆盖情况后明确确认") }
        }
    }
    fun clearDraftPromotionPreview() { mutable.update { it.copy(promotionPreview = null) } }
    fun refreshDraftPromotions() { retry = ::refreshDraftPromotions; work {
        val source = requireNotNull(mutable.value.travelDraft) { "请先打开草稿" }
        val operations = repo.draftPromotions(source.text("id"))
        mutable.update { it.copy(promotionOperations = operations, activePromotion = operations.firstOrNull()) }
    } }
    fun confirmDraftPromotion(action: String) { retry = { resolvePromotionBeforeRetry(action) }; work {
        require(action in setOf("create_only", "create_and_adopt")) { "请选择明确的正式化方式" }
        val prepared = requireNotNull(mutable.value.promotionPreview) { "请先生成正式旅行预览" }
        val coverage = prepared.obj("coverage")
        require((coverage["blockers"] as? JsonArray).orEmpty().isEmpty()) { "预览仍有阻塞，不能创建正式旅行" }
        val fingerprint = "${prepared.text("id")}|${prepared.text("prepared_hash")}|$action"
        if (pendingPromotion?.first != fingerprint) pendingPromotion = fingerprint to UUID.randomUUID().toString()
        val requestId = requireNotNull(pendingPromotion).second
        val knownId = prepared.text("operation_id").takeIf(String::isNotBlank)
        val result = try { repo.confirmDraftPromotion(prepared, action, requestId) }
            catch (e: Exception) {
                val observed = knownId?.let { runCatching { repo.draftPromotion(it) }.getOrNull() }
                    ?: repo.draftPromotions(prepared.text("draft_id")).firstOrNull {
                        it.text("prepared_id") == prepared.text("id")
                    }
                if (observed == null) throw e
                observed
            }
        pendingPromotion = null
        val operations = repo.draftPromotions(prepared.text("draft_id"))
        mutable.update { it.copy(activePromotion = result, promotionOperations = operations,
            notice = "正式化状态：${result.text("status")}；请按服务状态继续") }
    } }
    private fun resolvePromotionBeforeRetry(action: String) { refreshDraftPromotions() }
    fun resumeDraftPromotion() { retry = ::resumeDraftPromotion; work {
        val active = requireNotNull(mutable.value.activePromotion) { "请先读取正式化操作" }
        val result = repo.resumeDraftPromotion(active.text("id"))
        val operations = repo.draftPromotions(result.text("draft_id"))
        mutable.update { it.copy(activePromotion = result, promotionOperations = operations,
            notice = "正式化状态：${result.text("status")}") }
    } }
    private fun cachedDrafts(values: List<JsonObject>, value: JsonObject) =
        (values.filterNot { it.text("id") == value.text("id") } + value).sortedByDescending { it.text("updated_at") }
    fun category(value: String) { mutable.update { it.copy(category = value) }; search() }
    fun searchNearbyCenter(query: String) { retry = { searchNearbyCenter(query) }; work {
        require(query.isNotBlank()) { "请输入附近搜索中心地点" }
        val values = repo.search(mutable.value.city, query.trim(), "")
        mutable.update { it.copy(nearbyCenterCandidates = values) }
    } }
    fun setNearbyCenter(place: JsonObject) {
        val location = place.obj("location")
        val longitude = location["longitude"]?.jsonPrimitive?.doubleOrNull ?: error("地点缺少有效经度")
        val latitude = location["latitude"]?.jsonPrimitive?.doubleOrNull ?: error("地点缺少有效纬度")
        setNearbyCenter(longitude, latitude, place.text("name"), "verified_place")
    }
    fun setNearbyCenter(longitude: Double, latitude: Double, label: String, source: String = "manual_map") {
        require(longitude.isFinite() && latitude.isFinite() && longitude in -180.0..180.0 && latitude in -90.0..90.0) {
            "请从地图选择有效中心位置"
        }
        require(source in setOf("verified_place", "manual_map", "foreground_location")) { "未知的位置来源" }
        mutable.update { it.copy(nearbyCenter = NearbyCenter(longitude, latitude, label.take(100), source),
            nearbyPlaces = emptyList(), nearbySelectedPlace = null, nearbyRoute = null) }
    }
    fun setNearbyFilters(query: String, category: String, radiusMeters: Int, minRating: Double?,
        maxFoodPriceYuan: Double?, includeUnknown: Boolean) {
        require(category in setOf("", "attraction", "food", "lodging")) { "未知地点分类" }
        require(radiusMeters in 1..50000) { "附近半径须在 1–50000 米之间" }
        require(minRating == null || (minRating.isFinite() && minRating in 0.0..5.0)) { "评分须在 0–5 之间" }
        require(maxFoodPriceYuan == null || (maxFoodPriceYuan.isFinite() && maxFoodPriceYuan >= 0.0)) { "餐饮参考价无效" }
        mutable.update { it.copy(nearbyQuery = query.take(200), nearbyCategory = category,
            nearbyRadiusMeters = radiusMeters, nearbyMinRating = minRating,
            nearbyMaxFoodPriceYuan = maxFoodPriceYuan, nearbyIncludeUnknown = includeUnknown) }
    }
    fun searchNearby() { retry = ::searchNearby; work {
        val s = mutable.value
        val center = requireNotNull(s.nearbyCenter) { "请先选择附近搜索中心" }
        require(s.city.isNotBlank()) { "请填写城市" }
        require(s.nearbyQuery.isNotBlank() || s.nearbyCategory.isNotBlank()) { "请输入关键词或选择分类" }
        val point = buildJsonObject {
            put("longitude", center.longitude); put("latitude", center.latitude); put("coordinate_system", "GCJ02")
        }
        val values = repo.discover(s.city, s.nearbyQuery, s.nearbyCategory, point,
            s.nearbyRadiusMeters, s.nearbyMinRating, s.nearbyMaxFoodPriceYuan, s.nearbyIncludeUnknown)
        mutable.update { it.copy(nearbyPlaces = values, nearbySelectedPlace = null, nearbyRoute = null,
            notice = "按当前条件找到 ${values.size} 个真实地点") }
    } }
    fun selectNearbyPlace(place: JsonObject) {
        require(mutable.value.nearbyPlaces.any { it.placeId() == place.placeId() }) { "请从本次附近结果选择地点" }
        mutable.update { it.copy(nearbySelectedPlace = place, nearbyRoute = null) }
    }
    fun toggleCompare(place: JsonObject) {
        val id = place.placeId()
        require(id.isNotBlank() && (id in mutable.value.comparePlaceIds ||
            mutable.value.nearbyPlaces.any { it.placeId() == id })) { "请从本次附近结果选择地点" }
        mutable.update { state ->
            val places = if (id in state.comparePlaceIds) state.comparedPlaces.filterNot { it.placeId() == id }
                else (state.comparedPlaces + place).takeLast(8)
            state.copy(comparedPlaces = places, comparePlaceIds = places.map { it.placeId() }.toSet())
        }
    }
    fun nearbyRoute(destination: JsonObject, mode: String = "walk") { retry = { nearbyRoute(destination, mode) }; work {
        require(mode in setOf("walk", "driving")) { "当前支持步行或驾车路线" }
        val s = mutable.value
        val center = requireNotNull(s.nearbyCenter) { "请先选择附近搜索中心" }
        require(s.nearbyPlaces.any { it.placeId() == destination.placeId() }) { "请从本次附近结果选择目的地" }
        val point = buildJsonObject {
            put("longitude", center.longitude); put("latitude", center.latitude); put("coordinate_system", "GCJ02")
        }
        val result = repo.routePoints(point, destination.obj("location"), mode)
        mutable.update { it.copy(nearbyRoute = result, nearbyRouteMode = mode, nearbySelectedPlace = destination) }
    } }
    fun go(screen: String) { if (screen != mutable.value.screen) history.add(mutable.value.screen); mutable.update { it.copy(screen = screen, error = null) } }
    fun back() { mutable.update { it.copy(screen = if (history.isEmpty()) "explore" else history.removeAt(history.lastIndex), error = null) } }
    fun search() { retry = ::search; work {
        val s = mutable.value
        require(s.query.isNotBlank() || s.category.isNotBlank()) { "请输入城市或地点，或选择分类" }
        var city = s.city.trim()
        var query = s.query.trim()
        var category = s.category
        if (city.isBlank()) {
            val matches = repo.cities(query).filter {
                it.text("name").removeSuffix("市") == query.removeSuffix("市")
            }
            require(matches.size == 1) { "查具体地点时请补充所在城市；城市有歧义时请填写更完整的城市名称。" }
            city = matches.single().text("name")
            query = ""
            if (category.isBlank()) category = "attraction"
        }
        val places = repo.search(city, query, category)
        mutable.update { it.copy(city = city, query = query, category = category, places = places) }
    } }
    fun openPlace(id: String) { retry = { openPlace(id) }; work {
        val place = repo.detail(id); val saved = repo.isFavorite(id)
        go("detail"); mutable.update { it.copy(place = place, favorite = saved, route = null) }
    } }
    fun toggleFavorite() { retry = ::toggleFavorite; work {
        val s = mutable.value; val id = s.place?.placeId() ?: return@work
        repo.favorite(id, !s.favorite); val saved = repo.isFavorite(id)
        mutable.update { it.copy(favorite = saved, notice = if (saved) "已收藏，刷新和重新进入后保留" else "已取消收藏") }
    } }
    fun favorites() { retry = ::favorites; work { val values = repo.favorites(); go("favorites"); mutable.update { it.copy(favorites = values) } } }
    fun openPreferences() {
        retry = ::openPreferences
        val previous = mutable.value.screen
        work { loadPreferences(previous) }
    }
    private suspend fun loadPreferences(previous: String) {
        val value = repo.travelPreferences()
        if (previous != "preferences") history.add(previous)
        mutable.update { it.copy(screen = "preferences", preferences = value, preferenceInterests = value.interests.joinToString("，")) }
    }
    fun togglePreferenceCategory(category: String, enabled: Boolean) {
        mutable.update { state ->
            val categories = if (enabled) (state.preferences.preferredCategories + category).distinct()
                else state.preferences.preferredCategories.filterNot { it == category }
            state.copy(preferences = state.preferences.copy(preferredCategories = categories.take(3)), notice = null)
        }
    }
    fun editPreferenceInterests(value: String) { mutable.update { it.copy(preferenceInterests = value.take(300), notice = null) } }
    fun savePreferences() { retry = ::savePreferences; work {
        val terms = mutable.value.preferenceInterests.split(',', '，').map(String::trim).filter(String::isNotEmpty).distinct()
        require(terms.size <= 8 && terms.all { it.length <= 30 }) { "最多填写8个兴趣词，每个不超过30字。" }
        val saved = repo.saveTravelPreferences(mutable.value.preferences.copy(interests = terms))
        mutable.update { it.copy(preferences = saved, preferenceInterests = saved.interests.joinToString("，"), notice = "偏好已保存；可刷新重新读取。") }
    } }
    fun setOrigin(place: JsonObject) { mutable.update { it.copy(origin = place, route = null, notice = "已设为路线起点：${place.text("name")}") } }
    fun route(mode: String = mutable.value.routeMode) { retry = { route(mode) }; work {
        val s = mutable.value; val origin = s.origin ?: error("请先搜索一个真实地点，在详情中设为起点")
        val destination = s.place ?: error("请先打开目的地详情")
        require(origin.placeId() != destination.placeId()) { "起点与终点相同，请选择其他地点" }
        val result = repo.route(origin, destination, mode)
        go("route"); mutable.update { it.copy(route = result, routeMode = mode) }
    } }
    fun map() { go("map") }
    fun assistant(place: JsonObject? = null) {
        mutable.update { it.copy(discussing = place, assistantTripId = null, assistantDraftId = null,
            assistantDraftVersion = null, assistantSurface = if (place == null) "assistant" else "place",
            draft = if (place != null) "想了解${place.text("name")}，请推荐附近真实地点。" else it.draft) }
        go("assistant"); retry = { assistant(place) }; work { val session = repo.session(); mutable.update { it.copy(session = session) } }
    }
    fun assistantDraft(draftId: String, version: Int, city: String) {
        require(version >= 1 && city.isNotBlank()) { "草稿版本或城市无效" }
        mutable.update { it.copy(city = city, discussing = null, assistantTripId = null,
            assistantDraftId = draftId, assistantDraftVersion = version, assistantSurface = "draft") }
        go("assistant"); retry = { assistantDraft(draftId, version, city) }
        work { val session = repo.session(); mutable.update { it.copy(session = session) } }
    }
    fun assistantForDraft(draftId: String) { retry = { assistantForDraft(draftId) }; work {
        val value = repo.draft(draftId)
        val city = value.text("city")
        val version = value["version"]?.jsonPrimitive?.intOrNull ?: error("草稿版本缺失")
        val session = repo.session()
        go("assistant")
        mutable.update { it.copy(city = city, discussing = null, assistantTripId = null,
            assistantDraftId = draftId, assistantDraftVersion = version, assistantSurface = "draft", session = session) }
    } }
    fun assistantForTrip(tripId: String, city: String, surface: String = "trip") {
        require(surface in setOf("trip", "execution") && city.isNotBlank()) { "旅行上下文无效" }
        mutable.update { it.copy(city = city, discussing = null, assistantTripId = tripId,
            assistantDraftId = null, assistantDraftVersion = null, assistantSurface = surface) }
        go("assistant"); retry = { assistantForTrip(tripId, city, surface) }
        work { val session = repo.session(); mutable.update { it.copy(session = session) } }
    }
    fun send() { retry = ::send; work {
        val s = mutable.value; val message = s.draft.trim(); if (message.isEmpty()) return@work
        val session = s.session ?: repo.session()
        val id = pendingMessage?.takeIf { it.first == message }?.second ?: UUID.randomUUID().toString()
        pendingMessage = message to id
        val result = repo.message(session.text("id"), message, id, s.city, s.discussing,
            readTripId = s.assistantTripId, readDraftId = s.assistantDraftId,
            readDraftVersion = s.assistantDraftVersion, surface = s.assistantSurface)
        require(result["trip_id"] == null || result["trip_id"] == JsonNull) { "无 Trip 会话关联异常，请重新连接" }
        mutable.update { it.copy(session = result, draft = "") }; pendingMessage = null
    } }
    fun assistantRoute(destinationId: String) {
        val originId = mutable.value.origin?.placeId()
        if (originId == null) { mutable.update { it.copy(error = "请先在真实地点详情设为路线起点") }; return }
        val requestId = UUID.randomUUID().toString()
        fun execute() { work {
            require(originId != destinationId) { "起点与终点相同" }
            val s = mutable.value
            val session = s.session ?: repo.session()
            val result = repo.message(session.text("id"), "查询从已选起点到该地点的真实步行路线", requestId, s.city, s.discussing, buildJsonObject {
                put("origin_place_id", originId); put("destination_place_id", destinationId); put("mode", "walk")
            })
            mutable.update { it.copy(session = result) }
        } }
        retry = ::execute; execute()
    }
    fun openAssistantRoute(message: JsonObject) { retry = { openAssistantRoute(message) }; work {
        val query = message.obj("context").obj("route_request")
        val origin = repo.detail(query.text("origin_place_id"))
        val destination = repo.detail(query.text("destination_place_id"))
        val result = message.obj("read_tools").obj("route")
        require(result.text("status") == "available") { "此路线尚不可用，可重新查询" }
        go("route"); mutable.update { it.copy(origin = origin, place = destination, route = result.obj("result"), routeMode = query.text("mode")) }
    } }
    fun saveConnection(url: String, code: String) { retry = { saveConnection(url, code) }; work {
        endpoint.save(url)
        mutable.update { it.copy(connection = endpoint.url(), session = null, discussing = null) }
        if (code.isNotBlank()) repo.pair(code)
        saved.get<String>("selectedPlaceId")?.let { id ->
            runCatching { repo.detail(id) }.getOrNull()?.takeIf { it.placeId() == id }?.let { place ->
                mutable.update { it.copy(place = place) }
            }
        }
        val compared = saved.get<String>("comparedPlaceIds").orEmpty().split(',')
            .filter(String::isNotBlank).take(8).mapNotNull { id ->
                runCatching { repo.detail(id) }.getOrNull()?.takeIf { it.placeId() == id }
            }
        val selectedNearby = saved.get<String>("nearbySelectedPlaceId")?.let { id ->
            runCatching { repo.detail(id) }.getOrNull()?.takeIf { it.placeId() == id }
        }
        mutable.update { it.copy(comparedPlaces = compared, comparePlaceIds = compared.map { p -> p.placeId() }.toSet(),
            nearbySelectedPlace = selectedNearby) }
        saved.get<String>("selectedDraftId")?.let { id ->
            runCatching {
                val draft = repo.draft(id)
                val effective = repo.draftRequirements(id)
                val operations = repo.draftPromotions(id)
                mutable.update { it.copy(travelDraft = draft, draftEffectiveRequirements = effective,
                    travelDrafts = cachedDrafts(it.travelDrafts, draft), promotionOperations = operations,
                    activePromotion = operations.firstOrNull(), promotionPreview = null) }
            }
        }
        mutable.update { it.copy(notice = if (code.isBlank()) "地址已保存；USB 本机代理无需 APK 密钥" else "已配对，临时授权仅保存在内存") }
    } }
    fun disconnect() { work { repo.disconnect(); mutable.update { it.copy(notice = "临时授权已撤销") } } }
    fun retry() { retry?.invoke() }
    fun refresh() { when(mutable.value.screen) {
        "detail" -> mutable.value.place?.placeId()?.let(::openPlace)
        "favorites" -> favorites()
        "assistant" -> assistant(mutable.value.discussing)
        "preferences" -> openPreferences()
        "drafts" -> drafts()
        "draft-detail" -> mutable.value.travelDraft?.text("id")?.let(::openDraft)
        "route" -> route()
        else -> search()
    } }
}
