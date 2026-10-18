package com.roamsync.app.navigation

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import android.os.Looper
import androidx.core.content.ContextCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

data class ForegroundLocationFix(
    val wgs84: GeoPointFix,
    val gcj02: com.roamsync.app.data.remote.GeoPoint,
    val accuracyMeters: Float,
    val capturedAtEpochMillis: Long,
    val provider: String,
)

data class GeoPointFix(val longitude: Double, val latitude: Double)

/** One fresh location read, started only after the foreground UI grants permission. */
suspend fun readForegroundLocation(context: Context): ForegroundLocationFix {
    val app = context.applicationContext
    val fine = ContextCompat.checkSelfPermission(app, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
    val coarse = ContextCompat.checkSelfPermission(app, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    require(fine || coarse) { "请允许 RoamSync 在使用时访问位置信息。" }

    val manager = app.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    val providers = listOfNotNull(
        LocationManager.GPS_PROVIDER.takeIf { fine && manager.isProviderEnabled(LocationManager.GPS_PROVIDER) },
        LocationManager.NETWORK_PROVIDER.takeIf { manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) },
    ).distinct()
    require(providers.isNotEmpty()) { "请先开启系统定位服务，再重试。" }

    var location: Location? = null
    for (provider in providers) {
        location = withTimeoutOrNull(15_000L) { requestSingleFix(manager, provider, app) }
        if (location != null) break
    }
    val fix = location ?: error("暂时无法取得新定位，请检查 GPS 或网络后重试。")
    val ageMillis = System.currentTimeMillis() - fix.time
    require(ageMillis in 0..30_000L) { "定位结果已过期，请重新获取当前位置。" }
    require(fix.accuracy.isFinite() && fix.accuracy in 0.1f..100f) { "定位精度不足 100 米，未提交路线请求。" }
    val gcj02 = wgs84ToGcj02(fix.longitude, fix.latitude)
    return ForegroundLocationFix(
        wgs84 = GeoPointFix(fix.longitude, fix.latitude),
        gcj02 = gcj02,
        accuracyMeters = fix.accuracy,
        capturedAtEpochMillis = fix.time,
        provider = fix.provider ?: "unknown",
    )
}

private suspend fun requestSingleFix(manager: LocationManager, provider: String, context: Context): Location? =
    suspendCancellableCoroutine { continuation ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val signal = CancellationSignal()
            continuation.invokeOnCancellation { signal.cancel() }
            manager.getCurrentLocation(provider, signal, context.mainExecutor) { location ->
                if (continuation.isActive) continuation.resume(location)
            }
        } else {
            @Suppress("DEPRECATION")
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    if (continuation.isActive) continuation.resume(location)
                    manager.removeUpdates(this)
                }
                @Deprecated("Deprecated in Android") override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) = Unit
                override fun onProviderEnabled(provider: String) = Unit
                override fun onProviderDisabled(provider: String) = Unit
            }
            continuation.invokeOnCancellation { manager.removeUpdates(listener) }
            @Suppress("DEPRECATION")
            manager.requestSingleUpdate(provider, listener, Looper.getMainLooper())
        }
    }
