package com.roamsync.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import com.roamsync.app.data.obj
import com.roamsync.app.data.rows
import com.roamsync.app.data.text
import kotlinx.serialization.json.JsonObject

internal val Paper = Color(0xFFFFFDF7)
internal val Cream = Color(0xFFF7F4EB)
internal val Ink = Color(0xFF183A38)
internal val Teal = Color(0xFF287D70)
internal val DeepTeal = Color(0xFF195B53)
internal val SoftOrange = Color(0xFFDD815D)
internal val Mist = Color(0xFFE9EEE4)

@Composable
internal fun CompassMark(
    modifier: Modifier = Modifier,
    markSize: Dp = 38.dp,
    background: Color = DeepTeal,
    foreground: Color = Paper,
) {
    Box(
        modifier = modifier
            .size(markSize)
            .clip(RoundedCornerShape(14.dp))
            .background(background),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.padding(8.dp).fillMaxSize()) {
            val center = Offset(size.width / 2f, size.height / 2f)
            val radius = size.minDimension * .47f
            drawCircle(foreground, radius, center, style = Stroke(size.minDimension * .075f))
            val north = Path().apply {
                moveTo(center.x, center.y - radius * .72f)
                lineTo(center.x + radius * .23f, center.y + radius * .23f)
                lineTo(center.x - radius * .05f, center.y + radius * .08f)
                close()
            }
            val south = Path().apply {
                moveTo(center.x, center.y + radius * .72f)
                lineTo(center.x - radius * .23f, center.y - radius * .23f)
                lineTo(center.x + radius * .05f, center.y - radius * .08f)
                close()
            }
            drawPath(north, SoftOrange)
            drawPath(south, foreground)
            drawCircle(background, size.minDimension * .06f, center)
        }
    }
}

@Composable
internal fun AppCard(
    modifier: Modifier = Modifier,
    color: Color = Paper,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = color,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE6E3D8)),
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp), content = content)
    }
}

@Composable
internal fun PageHeading(kicker: String, title: String, detail: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.padding(bottom = 4.dp)) {
        Text(kicker.uppercase(), color = Teal, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp)
        Text(title, style = MaterialTheme.typography.headlineMedium, color = Ink)
        if (!detail.isNullOrBlank()) Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
internal fun QuietState(title: String, detail: String, modifier: Modifier = Modifier) {
    AppCard(modifier = modifier, color = Color(0xFFF1F0E6)) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = Ink)
        Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

internal fun approvedPhotos(place: JsonObject): List<JsonObject> {
    val ref = place.obj("ref")
    val placeId = ref.text("place_id")
    val providerId = ref.obj("external_ref").text("provider_place_id")
    if (placeId.isBlank() || providerId.isBlank()) return emptyList()
    val asset = Regex("^/api/v1/media/place-images/[a-z0-9-]+\\.jpg$")
    val license = Regex("^https://creativecommons\\.org/(licenses/by(-sa)?/[0-9.]+/?|publicdomain/zero/1\\.0(/deed\\.en)?/?)$")
    return place.rows("images").filter { photo ->
        val placeRef = photo.obj("place_ref")
        photo.text("usage_basis") == "reviewed_commons_license" &&
            photo.text("provider") == "wikimedia_commons" &&
            placeRef.text("place_id") == placeId &&
            placeRef.obj("external_ref").text("provider") == "amap" &&
            placeRef.obj("external_ref").text("provider_place_id") == providerId &&
            asset.matches(photo.text("url")) && asset.matches(photo.text("thumbnail_url")) &&
            photo.text("source_url").startsWith("https://commons.wikimedia.org/wiki/File:") &&
            photo.text("attribution").isNotBlank() && photo.text("license_name").isNotBlank() &&
            license.matches(photo.text("license_url"))
    }
}

@Composable
internal fun ReviewedPlacePhotos(
    place: JsonObject,
    loadBytes: suspend (String) -> ByteArray?,
    gallery: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val photos = approvedPhotos(place)
    if (photos.isEmpty()) {
        Row(
            modifier = modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(Mist).padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("▧", color = DeepTeal, fontSize = 22.sp)
            Column {
                Text("暂无地点照片", fontWeight = FontWeight.SemiBold, color = Ink)
            }
        }
        return
    }
    var selected by remember(place.obj("ref").text("place_id"), photos.size) { mutableIntStateOf(0) }
    val photo = photos[selected.coerceIn(0, photos.lastIndex)]
    val imagePath = if (gallery) photo.text("url") else photo.text("thumbnail_url")
    val bytes by produceState<ByteArray?>(null, imagePath, loadBytes) {
        value = runCatching { loadBytes(imagePath) }.getOrNull()
    }
    val bitmap = remember(bytes) { bytes?.let { data -> android.graphics.BitmapFactory.decodeByteArray(data, 0, data.size)?.asImageBitmap() } }
    val uriHandler = LocalUriHandler.current
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap,
                contentDescription = photo.text("title").ifBlank { place.text("name") },
                modifier = Modifier.fillMaxWidth().height(if (gallery) 230.dp else 172.dp).clip(RoundedCornerShape(20.dp)),
                contentScale = if (gallery) ContentScale.Fit else ContentScale.Crop,
            )
        } else {
            Row(
                Modifier.fillMaxWidth().height(if (gallery) 180.dp else 142.dp).clip(RoundedCornerShape(20.dp)).background(Mist).padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("▧", color = DeepTeal, fontSize = 22.sp)
                Text("照片暂时无法加载 · 地点信息仍可使用", color = DeepTeal, fontSize = 13.sp)
            }
        }
        Text(photo.text("title"), color = Ink, fontWeight = FontWeight.Medium, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { runCatching { uriHandler.openUri(photo.text("source_url")) } }, contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp)) {
                Text("${photo.text("attribution")} · Wikimedia Commons", fontSize = 11.sp)
            }
            Text("·", color = MaterialTheme.colorScheme.outline)
            TextButton(onClick = { runCatching { uriHandler.openUri(photo.text("license_url")) } }, contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp)) {
                Text(photo.text("license_name"), fontSize = 11.sp)
            }
        }
        if (photo.text("changes").isNotBlank()) Text(photo.text("changes"), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        if (gallery) Text("历史照片仅供了解地点，不代表当前天气、营业状态或现场情况。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        if (photos.size > 1) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                photos.forEachIndexed { index, candidate ->
                    FilterChip(
                        selected = index == selected,
                        onClick = { selected = index },
                        label = { Text("${index + 1}") },
                    )
                }
                Text("${selected + 1} / ${photos.size}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
        }
    }
}
