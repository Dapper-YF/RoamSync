package com.roamsync.app.navigation

import com.roamsync.app.data.remote.GeoPoint
import com.roamsync.app.data.remote.RouteQuery
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class CoordinateTransformTest {
    @Test fun convertsGpsWgs84ToAmapGcj02() {
        val converted = wgs84ToGcj02(116.397, 39.908)
        assertEquals("GCJ02", converted.coordinateSystem)
        assertEquals(116.40324, converted.longitude, 0.0001)
        assertEquals(39.9094, converted.latitude, 0.0001)
        assertNotEquals(116.397, converted.longitude, 0.001)
    }

    @Test fun rejectsInvalidAndOutOfServiceAreaCoordinates() {
        listOf(
            Double.NaN to 30.0,
            181.0 to 30.0,
            104.0 to 91.0,
            0.0 to 0.0,
            72.0039 to 30.0,
            137.8348 to 30.0,
            104.0 to 0.8292,
            104.0 to 55.8271 + 0.0001,
        ).forEach { (longitude, latitude) ->
            assertThrows(IllegalArgumentException::class.java) { wgs84ToGcj02(longitude, latitude) }
        }
    }

    @Test fun routePayloadRequiresAnExplicitGcj02OriginAndDestination() {
        val json = Json.encodeToString(RouteQuery.serializer(), RouteQuery(
            origin = wgs84ToGcj02(116.397, 39.908),
            destination = GeoPoint(116.41, 39.92, "GCJ02"),
        ))
        assertEquals(true, json.contains("\"coordinate_system\":\"GCJ02\""))
        assertEquals(true, json.contains("\"longitude\":116.403"))
    }
}
