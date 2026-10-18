package com.roamsync.app.ui

import com.roamsync.app.data.normalizedTourismUrl
import com.roamsync.app.data.tourismContext
import com.roamsync.app.data.remote.TripResponse
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class TourismContractTest {
    @Test fun failedModificationDoesNotReportPreviousSuccessAsAnUpdate() {
        val draft = Json.parseToJsonElement("""{"runs":[{"request_id":"old","status":"completed"},{"request_id":"current","status":"failed"}]}""").jsonObject
        assertEquals("本次生成未完成，原方案保留；可重试或修改要求。", draftActionNotice("runs", draft, "current"))
        assertEquals("草稿内容已更新，请查看生成记录", draftActionNotice("runs", draft, "old"))
    }
    @Test fun existingTripWithUnsetBudgetStillOpens() {
        val trip = Json { ignoreUnknownKeys = true }.decodeFromString<TripResponse>("""{"id":"trip","title":"保留旅程","start_date":"2026-10-15","end_date":"2026-10-17","total_budget_fen":null,"daily_budget_fen":null,"currency":"CNY","timezone":"Asia/Shanghai"}""")
        assertNull(trip.totalBudgetFen)
        assertEquals("未设置", formatFen(trip.totalBudgetFen))
    }
    @Test fun usbEndpointIsAllowedWithoutEmbeddingCredentials() {
        assertEquals("http://127.0.0.1:3000/", normalizedTourismUrl("http://127.0.0.1:3000"))
        assertEquals("http://127.0.0.1:18003/", normalizedTourismUrl("http://127.0.0.1:18003/"))
    }
    @Test fun insecureLanAndCredentialUrlsAreRejected() {
        listOf("http://192.168.1.3:18003/", "https://user:password@example.com/", "https://example.com/?token=x", "https://example.com/api/").forEach {
            assertTrue(it, runCatching { normalizedTourismUrl(it) }.isFailure)
        }
    }
    @Test fun browsingNeverCarriesFormalTripAuthorityOrGps() {
        val id = "7489846f-f1da-596d-97f9-1a4c0a30164d"
        val context = tourismContext("杭州", id)
        assertEquals(id, context["discussing_place_id"]?.jsonPrimitive?.content)
        assertEquals("place", context["surface"]?.jsonPrimitive?.content)
        assertEquals("assistant-context-v1", context["version"]?.jsonPrimitive?.content)
        listOf("read_trip_id", "action_target", "physical_location").forEach { assertEquals(JsonNull, context[it]) }
        assertFalse(context.containsKey("owner_id"))
    }
    @Test fun unifiedAssistantReadScopesNeverGrantFormalMutationAuthority() {
        val draft = tourismContext("杭州", null, readDraftId = "draft-id", readDraftVersion = 3, surface = "draft")
        assertEquals("draft", draft["surface"]?.jsonPrimitive?.content)
        assertEquals("draft-id", draft["read_draft_id"]?.jsonPrimitive?.content)
        assertEquals(3, draft["read_draft_version"]?.jsonPrimitive?.int)
        assertEquals(JsonNull, draft["read_trip_id"])
        assertEquals(JsonNull, draft["action_target"])
        val trip = tourismContext("杭州", null, readTripId = "trip-id", surface = "execution")
        assertEquals("trip-id", trip["read_trip_id"]?.jsonPrimitive?.content)
        assertEquals(JsonNull, trip["read_draft_id"])
        assertEquals(JsonNull, trip["action_target"])
        assertEquals(JsonNull, trip["physical_location"])
    }
}
