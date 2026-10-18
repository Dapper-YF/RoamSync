package com.roamsync.app.ui

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.HttpException

/** Diagnoses only an explicit service response. No coordinate inference or location logging. */
internal fun currentLocationRouteFailure(error: Exception): String {
    if (error is java.io.IOException) return "路线服务连接中断，请检查网络后重试。"
    if (error !is HttpException) return "尚未取得路线；原因未确认，请重试或改选起点。"
    val detail = runCatching {
        val root = Json.parseToJsonElement(error.response()?.errorBody()?.string().orEmpty()) as? JsonObject
        root?.get("detail") as? JsonObject
    }.getOrNull()
    val code = runCatching { detail?.get("code")?.jsonPrimitive?.content }.getOrNull()
    val providerCode = runCatching { detail?.get("provider_code")?.jsonPrimitive?.content }.getOrNull()
    val provider = runCatching { detail?.get("provider")?.jsonPrimitive?.content }.getOrNull()
    if (provider == "amap") {
        when (providerCode) {
            "20800" -> return "高德返回起点或终点超出路径规划服务范围；这不表示定位失败。可改选支持区域内的起点。"
            "20801" -> return "高德未找到起点或终点附近的道路，请检查地图选点或改选起点。"
            "20802" -> return "高德无法连通这两个地点的道路，可改选起点或交通方式。"
            "20803" -> return "高德返回起终点距离超出当前路线模式的范围，可改选附近起点或交通方式。"
        }
    }
    return when {
        error.code() == 401 -> "连接授权已过期，请重新配对后再查询；已保存的旅行仍保留。"
        error.code() == 422 -> "路线请求参数未通过检查，请重新选择起点和目的地。"
        code in setOf("map_quota_exceeded", "map_rate_limited") -> "高德查询额度或频率受限，请稍后重试。"
        code == "map_credentials_invalid" || code == "map_not_configured" -> "地图服务配置暂不可用，需要检查服务连接配置。"
        code == "map_network_error" -> "路线服务连接超时或中断，请稍后重试。"
        else -> "路线服务暂未返回可用结果，尚不能确定是覆盖范围、道路还是服务问题。可重试或改选起点。"
    }
}
