package com.roamsync.app.data

import android.content.Context
import com.roamsync.app.BuildConfig
import com.roamsync.app.data.remote.TravelPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

fun JsonObject.text(key: String): String = (get(key) as? JsonPrimitive)?.contentOrNull.orEmpty()
fun JsonObject.obj(key: String): JsonObject = get(key) as? JsonObject ?: buildJsonObject { }
fun JsonObject.rows(key: String): List<JsonObject> = (get(key) as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
fun JsonObject.placeId() = obj("ref").text("place_id")

/** HTTP is permitted only over loopback/USB. Never stores a server access credential. */
fun normalizedTourismUrl(value: String): String {
    val url = value.trim().toHttpUrl()
    require(url.username.isEmpty() && url.password.isEmpty() && url.query == null && url.fragment == null) { "地址不能包含凭据或查询参数" }
    require(url.encodedPath == "/") { "请输入服务根地址，例如 http://127.0.0.1:3000/" }
    require(url.isHttps || url.host in setOf("127.0.0.1", "localhost", "::1")) { "非本机服务必须使用 HTTPS 和可信配对" }
    return url.toString()
}

@Singleton class TourismEndpoint @Inject constructor(@ApplicationContext context: Context) {
    @Volatile var accessToken: String? = null
    private val prefs = context.getSharedPreferences("tourism_connection", Context.MODE_PRIVATE)
    fun url() = prefs.getString("base_url", null) ?: BuildConfig.API_BASE_URL
    fun save(value: String) { accessToken = null; prefs.edit().putString("base_url", normalizedTourismUrl(value)).remove("assistant_id").apply() }
    fun sessionId(): String? = prefs.getString("assistant_id", null)
    fun saveSession(value: String) { prefs.edit().putString("assistant_id", value).apply() }
    fun topicId(): String = prefs.getString("assistant_topic_id", null) ?: run {
        val created = "android-" + java.util.UUID.randomUUID().toString()
        prefs.edit().putString("assistant_topic_id", created).apply()
        created
    }
}

@Singleton class TourismRepository @Inject constructor(private val client: OkHttpClient, private val endpoint: TourismEndpoint) {
    private val json = Json { ignoreUnknownKeys = true }
    suspend fun reviewedImageBytes(relativeUrl: String): ByteArray = withContext(Dispatchers.IO) {
        require(Regex("^/api/v1/media/place-images/[a-z0-9-]+\\.jpg$").matches(relativeUrl)) {
            "图片路径未经审核"
        }
        val request = Request.Builder().url(endpoint.url().trimEnd('/') + relativeUrl).build()
        client.newCall(request).execute().use { response ->
            require(response.isSuccessful && response.header("Content-Type")?.startsWith("image/jpeg") == true) {
                "审核图片暂不可用"
            }
            val length = response.body?.contentLength() ?: -1L
            require(length == -1L || length in 1..5_000_000L) { "审核图片大小无效" }
            val bytes = response.body?.bytes() ?: error("审核图片为空")
            require(bytes.size in 1..5_000_000) { "审核图片大小无效" }
            bytes
        }
    }
    suspend fun request(path: String, method: String = "GET", body: JsonObject? = null): JsonElement = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(endpoint.url().trimEnd('/') + "/api/v1/" + path)
            .method(method, if (method in listOf("POST", "PUT")) (body?.toString() ?: "{}").toRequestBody("application/json".toMediaType()) else null).build()
        client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            val parsed = runCatching { json.parseToJsonElement(raw) }.getOrNull()
            if (!response.isSuccessful) {
                if (response.code == 401) { endpoint.accessToken = null; error("连接授权已过期，请到连接设置重新配对") }
                val detail = (parsed as? JsonObject)?.get("detail")
                val message = (detail as? JsonPrimitive)?.contentOrNull ?: (detail as? JsonObject)?.text("message")
                error(message?.takeIf { it.isNotBlank() } ?: "服务暂不可用（${response.code}），请检查 USB 连接后重试")
            }
            parsed ?: JsonNull
        }
    }
    suspend fun pair(code: String) {
        val response = request("device-sessions", "POST", buildJsonObject { put("pairing_code", code.trim()) }).jsonObject
        endpoint.accessToken = response.text("access_token").takeIf { it.isNotBlank() } ?: error("配对未返回临时授权")
    }
    suspend fun disconnect() { if (endpoint.accessToken != null) request("device-sessions/current", "DELETE"); endpoint.accessToken = null }
    suspend fun cities(query: String): List<JsonObject> {
        val params = "http://localhost/".toHttpUrl().newBuilder().addQueryParameter("keyword", query.trim()).build().encodedQuery
        return request("locations/cities?$params").jsonArray.map { it.jsonObject }
    }
    suspend fun search(city: String, query: String, category: String): List<JsonObject> {
        val url = "http://localhost/".toHttpUrl().newBuilder().addQueryParameter("city", city)
            .addQueryParameter("query", query).addQueryParameter("page_size", "12")
        if (category.isNotBlank()) url.addQueryParameter("category", category)
        return request("places/search?" + url.build().encodedQuery).jsonObject.rows("items")
    }
    suspend fun detail(id: String) = request("places/$id").jsonObject
    suspend fun drafts() = request("drafts").jsonArray.map { it.jsonObject }
    suspend fun draft(id: String) = request("drafts/$id").jsonObject
    suspend fun draftRequirements(id: String) = request("drafts/$id/requirements").jsonObject
    suspend fun revokeDraftRequirement(value: JsonObject, requirementId: String, dayIndex: Int?) =
        request("drafts/${value.text("id")}/requirements/revoke", "POST", buildJsonObject {
            put("expected_version", value["version"] ?: error("草稿版本缺失，请刷新"))
            put("requirement_id", requirementId)
            put("day_index", dayIndex?.let(::JsonPrimitive) ?: JsonNull)
        }).jsonObject
    suspend fun editDraft(value: JsonObject, title: String, requirements: String, plan: JsonElement?) =
        request("drafts/${value.text("id")}/edit", "POST", buildJsonObject {
            put("expected_version", value["version"] ?: error("草稿版本缺失，请刷新"))
            put("title", title.trim()); put("requirements", requirements.trim())
            put("plan", plan ?: JsonNull)
        }).jsonObject
    suspend fun previewDraftPromotion(value: JsonObject, options: JsonObject) =
        request("drafts/${value.text("id")}/promotion-preview", "POST", buildJsonObject {
            put("expected_version", value["version"] ?: error("草稿版本缺失，请刷新"))
            options.forEach { (key, part) -> put(key, part) }
        }).jsonObject
    suspend fun draftPromotions(draftId: String) = request("drafts/$draftId/promotions").jsonArray.map { it.jsonObject }
    suspend fun draftPromotion(id: String) = request("draft-promotions/$id").jsonObject
    suspend fun confirmDraftPromotion(prepared: JsonObject, action: String, requestId: String) =
        request(prepared.text("operation_id").takeIf { it.isNotBlank() }
            ?.let { "draft-promotions/$it/review" } ?: "draft-promotions", "POST", buildJsonObject {
            put("request_id", requestId); put("prepared_id", prepared.text("id"))
            put("prepared_hash", prepared.text("prepared_hash")); put("action", action)
            put("confirmation", if (action == "create_only") "创建旅行" else "创建并采用当前方案")
        }).jsonObject
    suspend fun resumeDraftPromotion(id: String) = request("draft-promotions/$id/resume", "POST").jsonObject
    suspend fun createDraft(city: String, title: String, dayCount: Int, requirements: String) = request("drafts", "POST", buildJsonObject {
        put("city", city.trim()); put("title", title.trim()); put("day_count", dayCount); put("requirements", requirements)
    }).jsonObject
    suspend fun discover(city: String, query: String, category: String, center: JsonObject,
        radiusMeters: Int, minRating: Double?, maxFoodPriceYuan: Double?, includeUnknown: Boolean): List<JsonObject> {
        val response = request("places/discover", "POST", buildJsonObject {
            put("city", city.trim()); put("query", query.trim())
            put("category", category.takeIf(String::isNotBlank)?.let(::JsonPrimitive) ?: JsonNull)
            put("center", center); put("radius_meters", radiusMeters)
            put("min_rating", minRating?.let(::JsonPrimitive) ?: JsonNull)
            put("max_food_price_yuan", maxFoodPriceYuan?.let(::JsonPrimitive) ?: JsonNull)
            put("include_unknown", includeUnknown); put("use_preferences", true)
        }).jsonObject
        return response.rows("items").mapNotNull { item ->
            val place = item["place"] as? JsonObject ?: return@mapNotNull null
            JsonObject(place + ("recommendation_reasons" to (item["reasons"] ?: JsonArray(emptyList()))))
        }
    }
    suspend fun draftAction(value: JsonObject, action: String, requirements: String = "", requestId: String? = null) =
        request("drafts/${value.text("id")}/$action", "POST", buildJsonObject {
            put("expected_version", value["version"] ?: error("草稿版本缺失，请刷新"))
            if (action == "runs") { put("request_id", requestId ?: error("请求标识缺失")); put("requirements", requirements) }
        }).jsonObject
    suspend fun runDraft(value: JsonObject, requirements: String, dayIndex: Int?, requestId: String) =
        request("drafts/${value.text("id")}/runs", "POST", buildJsonObject {
            put("expected_version", value["version"] ?: error("草稿版本缺失，请刷新"))
            put("request_id", requestId); put("requirements", requirements.trim())
            put("target_day_indices", if (dayIndex == null) JsonArray(emptyList())
                else JsonArray(listOf(JsonPrimitive(dayIndex))))
        }).jsonObject
    suspend fun travelPreferences(): TravelPreferences = json.decodeFromString(
        TravelPreferences.serializer(), request("me/travel-preferences").toString(),
    )
    suspend fun saveTravelPreferences(value: TravelPreferences): TravelPreferences = json.decodeFromString(
        TravelPreferences.serializer(),
        request("me/travel-preferences", "PUT", buildJsonObject {
            put("version", value.version)
            put("preferred_categories", JsonArray(value.preferredCategories.map(::JsonPrimitive)))
            put("interests", JsonArray(value.interests.map(::JsonPrimitive)))
        }).toString(),
    )
    suspend fun favorites() = request("me/favorites").jsonArray.map { it.jsonObject.obj("place") }
    suspend fun isFavorite(id: String) = request("me/favorites/$id").jsonObject["is_favorite"]?.jsonPrimitive?.booleanOrNull == true
    suspend fun favorite(id: String, save: Boolean) { request("me/favorites/$id", if (save) "PUT" else "DELETE") }
    suspend fun route(origin: JsonObject, destination: JsonObject, mode: String) =
        routePoints(origin.obj("location"), destination.obj("location"), mode)
    suspend fun routePoints(origin: JsonObject, destination: JsonObject, mode: String) = request("routes/query", "POST", buildJsonObject {
        put("origin", origin); put("destination", destination); put("mode", mode)
    }).jsonObject
    suspend fun session(): JsonObject {
        // Session POST is idempotent per legacy global owner; this does not create a Trip.
        val result = request("assistant/sessions", "POST", buildJsonObject { put("trip_id", JsonNull) }).jsonObject
        require(result["trip_id"] == null || result["trip_id"] == JsonNull) { "无 Trip 对话不能关联旅行" }
        endpoint.saveSession(result.text("id")); return result
    }
    suspend fun message(id: String, text: String, messageId: String, city: String, place: JsonObject?,
        routeRequest: JsonObject? = null, readTripId: String? = null, readDraftId: String? = null,
        readDraftVersion: Int? = null, surface: String = "assistant"): JsonObject =
        request("assistant/sessions/$id/messages", "POST", buildJsonObject {
            put("message", text); put("message_id", messageId)
            put("context", buildJsonObject {
                tourismContext(city, place?.placeId(), readTripId, readDraftId, readDraftVersion, surface,
                    endpoint.topicId())
                    .forEach { (key, value) -> put(key, value) }
                if (routeRequest != null) put("route_request", routeRequest)
            })
        }).jsonObject
}

fun tourismContext(city: String, placeId: String?, readTripId: String? = null,
    readDraftId: String? = null, readDraftVersion: Int? = null, surface: String = "assistant",
    topicId: String = "travel-main") = buildJsonObject {
    put("version", "assistant-context-v1"); put("topic_id", topicId)
    put("surface", if (placeId != null) "place" else surface); put("browsing_city", city)
    put("discussing_place_id", placeId?.let(::JsonPrimitive) ?: JsonNull)
    put("physical_location", JsonNull)
    put("read_trip_id", readTripId?.let(::JsonPrimitive) ?: JsonNull)
    put("read_draft_id", readDraftId?.let(::JsonPrimitive) ?: JsonNull)
    put("read_draft_version", readDraftVersion?.let(::JsonPrimitive) ?: JsonNull)
    put("action_target", JsonNull)
}
