package com.roamsync.app.ui

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class RouteFailureTest {
    private fun failure(detail: String, status: Int = 503) = HttpException(Response.error<Any>(
        status, detail.toResponseBody("application/json".toMediaType())
    ))

    @Test fun onlyProviderEvidenceEstablishesCoverageOrDistanceFailure() {
        val outside = currentLocationRouteFailure(failure("""{"detail":{"provider":"amap","provider_code":"20800"}}"""))
        assertTrue(outside.contains("超出路径规划服务范围"))
        val distance = currentLocationRouteFailure(failure("""{"detail":{"provider":"amap","provider_code":"20803"}}"""))
        assertTrue(distance.contains("距离超出"))
        val unknown = currentLocationRouteFailure(failure("""{"detail":{"code":"map_provider_rejected"}}"""))
        assertTrue(unknown.contains("尚不能确定"))
        assertFalse(unknown.contains("超出路径规划服务范围"))
    }

    @Test fun malformedErrorsNeverExposeRawProviderTextOrPrivateCoordinates() {
        val error = currentLocationRouteFailure(failure("""{"detail":"private-coordinate-and-key"}"""))
        assertFalse(error.contains("private-coordinate"))
        assertTrue(error.contains("尚不能确定"))
        assertTrue(currentLocationRouteFailure(failure("not-json", 401)).contains("重新配对"))
        assertTrue(currentLocationRouteFailure(failure("{}", 422)).contains("参数未通过"))
    }

    @Test fun networkAndQuotaAreNotCalledLocationFailure() {
        assertTrue(currentLocationRouteFailure(java.io.IOException("private endpoint")).contains("连接中断"))
        assertTrue(currentLocationRouteFailure(failure("""{"detail":{"code":"map_quota_exceeded"}}""")).contains("额度或频率受限"))
    }
}
