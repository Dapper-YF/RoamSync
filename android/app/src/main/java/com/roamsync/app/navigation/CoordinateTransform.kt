package com.roamsync.app.navigation

import com.roamsync.app.data.remote.GeoPoint
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** Converts a fresh Android WGS84 fix to the GCJ02 system used by AMap. */
fun wgs84ToGcj02(longitude: Double, latitude: Double): GeoPoint {
    require(longitude.isFinite() && latitude.isFinite() && abs(longitude) <= 180 && abs(latitude) <= 90) {
        "定位没有返回有效坐标，请重新定位。"
    }
    require(longitude in 72.004..137.8347 && latitude in 0.8293..55.8271) {
        "当前位置超出高德地图支持区域，未提交路线请求。"
    }

    val x = longitude - 105.0
    val y = latitude - 35.0
    val pi = Math.PI
    var deltaLatitude = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x))
    deltaLatitude += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0
    deltaLatitude += (20.0 * sin(y * pi) + 40.0 * sin(y * pi / 3.0)) * 2.0 / 3.0
    deltaLatitude += (160.0 * sin(y * pi / 12.0) + 320.0 * sin(y * pi / 30.0)) * 2.0 / 3.0
    var deltaLongitude = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x))
    deltaLongitude += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0
    deltaLongitude += (20.0 * sin(x * pi) + 40.0 * sin(x * pi / 3.0)) * 2.0 / 3.0
    deltaLongitude += (150.0 * sin(x * pi / 12.0) + 300.0 * sin(x * pi / 30.0)) * 2.0 / 3.0

    val radians = latitude / 180.0 * pi
    val magic = 1.0 - 0.00669342162296594323 * sin(radians).pow(2.0)
    val rootMagic = sqrt(magic)
    deltaLatitude = deltaLatitude * 180.0 /
        ((6378245.0 * (1.0 - 0.00669342162296594323)) / (magic * rootMagic) * pi)
    deltaLongitude = deltaLongitude * 180.0 / (6378245.0 / rootMagic * cos(radians) * pi)
    return GeoPoint(longitude + deltaLongitude, latitude + deltaLatitude, "GCJ02")
}
