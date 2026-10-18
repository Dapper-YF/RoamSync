package com.roamsync.app.ui

import android.annotation.SuppressLint
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun NearbyNative(s: TourismState, vm: TourismViewModel, onOpenPlace: (String) -> Unit) {
    var centerQuery by rememberSaveable { mutableStateOf("") }
    var longitude by rememberSaveable(s.nearbyCenter?.longitude) { mutableStateOf(s.nearbyCenter?.longitude?.toString().orEmpty()) }
    var latitude by rememberSaveable(s.nearbyCenter?.latitude) { mutableStateOf(s.nearbyCenter?.latitude?.toString().orEmpty()) }
    var query by rememberSaveable { mutableStateOf(s.nearbyQuery) }
    var category by rememberSaveable { mutableStateOf(s.nearbyCategory) }
    var radius by rememberSaveable { mutableIntStateOf(s.nearbyRadiusMeters) }
    var ratingEnabled by rememberSaveable { mutableStateOf(s.nearbyMinRating != null) }
    var rating by rememberSaveable { mutableFloatStateOf((s.nearbyMinRating ?: 4.0).toFloat()) }
    var maxFoodPrice by rememberSaveable { mutableStateOf(s.nearbyMaxFoodPriceYuan?.toString().orEmpty()) }
    var includeUnknown by rememberSaveable { mutableStateOf(s.nearbyIncludeUnknown) }
    var showCenterPicker by rememberSaveable { mutableStateOf(false) }
    var showFilters by rememberSaveable { mutableStateOf(false) }
    var showManualCoordinates by rememberSaveable { mutableStateOf(false) }
    var resultView by rememberSaveable { mutableStateOf("list") }
    val minLongitude = longitude.toDoubleOrNull()
    val minLatitude = latitude.toDoubleOrNull()
    val filtersValid = maxFoodPrice.isBlank() || maxFoodPrice.toDoubleOrNull()?.let { it >= 0.0 } == true

    LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { PageHeading("NEARBY, AT YOUR PACE", "在附近慢慢挑。", "选择一个地点或地图位置作为中心，再查看真实的附近结果。") }
        item {
            AppCard(color = if (s.nearbyCenter == null) Mist else Paper) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("搜索中心", color = Ink, fontWeight = FontWeight.SemiBold)
                        Text(
                            s.nearbyCenter?.let { "${it.label} · ${if (it.source == "verified_place") "真实地点" else "地图选点"}" }
                                ?: "先选择城市中的一个地点或地图位置",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp,
                        )
                    }
                    OutlinedButton(onClick = { showCenterPicker = true }) { Text(if (s.nearbyCenter == null) "选择" else "更改") }
                }
            }
        }
        item {
            AppCard {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it.take(200) },
                    label = { Text("关键词") },
                    placeholder = { Text("茶馆、公园、面馆…") },
                    leadingIcon = { Text("⌕", color = DeepTeal, fontSize = 20.sp) },
                    singleLine = true,
                    enabled = !s.busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    listOf("" to "全部", "attraction" to "景点", "food" to "餐饮", "lodging" to "住宿").forEach { (value, label) ->
                        FilterChip(selected = category == value, onClick = { category = value }, enabled = !s.busy, label = { Text(label) })
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { showFilters = true }, enabled = !s.busy) {
                        Text("筛选 · ${radius / 1000} km${if (ratingEnabled) " · 评分 ${"%.1f".format(rating)}+" else ""}")
                    }
                    Text("${s.nearbyPlaces.size} 个地点", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                if (!filtersValid) Text("餐饮人均上限需为 0 或正数。", color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
                s.error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
                Button(
                    onClick = {
                        vm.setNearbyFilters(query, category, radius, if (ratingEnabled) rating.toDouble() else null,
                            maxFoodPrice.takeIf { it.isNotBlank() }?.toDoubleOrNull(), includeUnknown)
                        vm.searchNearby()
                    },
                    enabled = !s.busy && filtersValid && s.nearbyCenter != null && (query.isNotBlank() || category.isNotBlank()),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(if (s.busy) "正在寻找…" else "搜索附近地点") }
            }
        }
        if (s.nearbyPlaces.isNotEmpty()) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${s.nearbyPlaces.size} 个真实地点", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, color = Ink)
                    FilterChip(selected = resultView == "list", onClick = { resultView = "list" }, label = { Text("列表") })
                    FilterChip(selected = resultView == "map", onClick = { resultView = "map" }, label = { Text("地图") })
                }
            }
            if (resultView == "map") item {
                AppCard(color = Mist) {
                    Text("附近地点地图", style = MaterialTheme.typography.titleMedium, color = Ink)
                    NearbyMap(s, vm) { lng, lat ->
                        longitude = lng.toString()
                        latitude = lat.toString()
                        vm.setNearbyCenter(lng, lat, "地图选点", "manual_map")
                    }
                }
            }
            items(s.nearbyPlaces, key = { it.placeId() }) { place ->
                NearbyPlaceCard(s, vm, place, selected = s.nearbySelectedPlace?.placeId() == place.placeId())
            }
            if (s.nearbySelectedPlace != null) item { NearbySelectedPlace(s, vm, s.nearbySelectedPlace, onOpenPlace) }
            if (s.comparedPlaces.isNotEmpty()) item { NearbyCompare(s, vm) }
        } else if (!s.busy) {
            item {
                QuietState(
                    if (s.nearbyCenter == null) "先选一个搜索中心" else "附近地点会显示在这里",
                    if (s.nearbyCenter == null) "选择城市中的真实地点，或在地图上点选中心。" else "填写关键词或选择分类，再设定筛选条件开始搜索。",
                )
            }
        }
    }

    if (showCenterPicker) {
        ModalBottomSheet(onDismissRequest = { showCenterPicker = false }) {
            LazyColumn(contentPadding = PaddingValues(horizontal = 20.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { PageHeading("CHOOSE A REAL PLACE", "选择搜索中心。", "搜索地点或在地图上点选。定位不会自动开启。") }
                item {
                    OutlinedTextField(
                        value = s.city,
                        onValueChange = vm::editCity,
                        label = { Text("城市") },
                        placeholder = { Text("例如：杭州") },
                        singleLine = true,
                        enabled = !s.busy,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = centerQuery,
                            onValueChange = { centerQuery = it.take(100) },
                            label = { Text("搜索中心地点") },
                            placeholder = { Text("西湖、地铁站或酒店") },
                            singleLine = true,
                            enabled = !s.busy,
                            modifier = Modifier.weight(1f),
                        )
                        Button(onClick = { vm.searchNearbyCenter(centerQuery) }, enabled = !s.busy && s.city.isNotBlank() && centerQuery.isNotBlank()) { Text("查找") }
                    }
                }
                if (s.city.isBlank()) item { Text("请先填写城市，再查找真实地点。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
                s.error?.let { error -> item { Text(error, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) } }
                s.nearbyCenterCandidates.forEach { candidate ->
                    item(key = candidate.placeId()) {
                        OutlinedButton(onClick = {
                            vm.setNearbyCenter(candidate)
                            longitude = candidate.obj("location").text("longitude")
                            latitude = candidate.obj("location").text("latitude")
                        }, enabled = !s.busy, modifier = Modifier.fillMaxWidth()) {
                            Text("${candidate.text("name")} · ${candidate.text("address").ifBlank { "真实地点" }}", maxLines = 2)
                        }
                    }
                }
                s.nearbyCenter?.let { center ->
                    item {
                        Text("当前中心：${center.label} · GCJ02", color = DeepTeal, fontSize = 12.sp)
                    }
                    item {
                        NearbyMap(s, vm) { lng, lat ->
                            longitude = lng.toString()
                            latitude = lat.toString()
                            vm.setNearbyCenter(lng, lat, "地图选点", "manual_map")
                        }
                    }
                }
                item {
                    TextButton(onClick = { showManualCoordinates = !showManualCoordinates }) {
                        Text(if (showManualCoordinates) "收起坐标输入" else "手动输入 GCJ02 坐标", color = DeepTeal)
                    }
                }
                if (showManualCoordinates) {
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(longitude, { longitude = it }, label = { Text("经度") }, singleLine = true, modifier = Modifier.weight(1f))
                            OutlinedTextField(latitude, { latitude = it }, label = { Text("纬度") }, singleLine = true, modifier = Modifier.weight(1f))
                        }
                    }
                    item {
                        OutlinedButton(onClick = {
                            vm.setNearbyCenter(requireNotNull(minLongitude), requireNotNull(minLatitude), "你选择的位置", "manual_map")
                        }, enabled = !s.busy && minLongitude != null && minLatitude != null, modifier = Modifier.fillMaxWidth()) {
                            Text("使用输入的坐标")
                        }
                    }
                }
                item {
                    Button(onClick = { showCenterPicker = false }, modifier = Modifier.fillMaxWidth()) { Text("完成") }
                }
            }
        }
    } else if (showFilters) {
        ModalBottomSheet(onDismissRequest = { showFilters = false }) {
            LazyColumn(contentPadding = PaddingValues(horizontal = 20.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { PageHeading("YOUR FILTERS", "筛选附近地点。", "结果只按当前搜索中心与筛选条件排列。") }
                item {
                    Text("搜索半径 · ${radius / 1000.0} 公里", color = DeepTeal, fontWeight = FontWeight.Medium)
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(1000, 3000, 5000, 10000).forEach { meters ->
                            FilterChip(selected = radius == meters, onClick = { radius = meters }, label = { Text("${meters / 1000} km") })
                        }
                    }
                }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(checked = ratingEnabled, onCheckedChange = { ratingEnabled = it })
                        Text("最低评分 ${"%.1f".format(rating)}", modifier = Modifier.padding(start = 8.dp))
                    }
                    if (ratingEnabled) Slider(value = rating, onValueChange = { rating = it }, valueRange = 1f..5f, steps = 3)
                }
                if (category == "food" || category.isBlank()) item {
                    OutlinedTextField(
                        value = maxFoodPrice,
                        onValueChange = { maxFoodPrice = it },
                        label = { Text("餐饮人均上限（元，可选）") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = includeUnknown, onCheckedChange = { includeUnknown = it })
                        Text("保留评分或价格未知的地点", fontSize = 13.sp)
                    }
                }
                item {
                    Button(
                        onClick = {
                            vm.setNearbyFilters(query, category, radius, if (ratingEnabled) rating.toDouble() else null,
                                maxFoodPrice.takeIf { it.isNotBlank() }?.toDoubleOrNull(), includeUnknown)
                            vm.searchNearby()
                            showFilters = false
                        },
                        enabled = !s.busy && filtersValid && s.nearbyCenter != null && (query.isNotBlank() || category.isNotBlank()),
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("应用筛选并搜索") }
                }
            }
        }
    }
}

@Composable
private fun NearbyPlaceCard(s: TourismState, vm: TourismViewModel, place: JsonObject, selected: Boolean) {
    AppCard(color = if (selected) Color(0xFFF0F5EE) else Paper, modifier = Modifier.clickable { vm.selectNearbyPlace(place) }) {
        ReviewedPlacePhotos(place, vm::reviewedImageBytes)
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(place.text("name"), style = MaterialTheme.typography.titleLarge, color = Ink)
                Text("${place.text("city")} · ${categoryName(place.text("category"))}", color = DeepTeal, fontSize = 12.sp)
            }
            Text(if (place.placeId() in s.comparePlaceIds) "已加入对比" else "加入对比", color = DeepTeal, fontSize = 11.sp,
                modifier = Modifier.clickable { vm.toggleCompare(place) }.padding(8.dp))
        }
        Text(place.text("address").ifBlank { "地址暂无" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("评分 ${place.text("rating").ifBlank { "未知" }}", fontSize = 12.sp)
            Text("人均 ${place.obj("price").text("amount").ifBlank { "未知" }}${if (place.obj("price").text("amount").isNotBlank()) " 元" else ""}", fontSize = 12.sp)
            Text("距离 ${place.text("distance_meters").ifBlank { "—" }}${if (place.text("distance_meters").isNotBlank()) " 米" else ""}", fontSize = 12.sp)
        }
        val reasons = place.rows("reasons").mapNotNull { reason ->
            reason.text("text").ifBlank { reason.text("label") }.takeIf(String::isNotBlank)
        }
        reasons.take(3).forEach { Text("· $it", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        if (selected) Text("已选中 · 下方查看详情", fontSize = 11.sp, color = DeepTeal, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun NearbySelectedPlace(s: TourismState, vm: TourismViewModel, place: JsonObject, onOpenPlace: (String) -> Unit) {
    AppCard {
        PageHeading("Selected place", place.text("name"), place.text("address").ifBlank { "地址暂无" })
        val experience = place.obj("experience")
        Text("地点体验", style = MaterialTheme.typography.titleMedium, color = Ink)
        val summary = experience.text("summary")
        if (summary.isNotBlank()) {
            Text(summary, lineHeight = 22.sp)
            val source = experience.text("source_title")
            if (source.isNotBlank()) Text("资料来源：$source${experience.text("reviewed_at").takeIf(String::isNotBlank)?.let { " · 核对于 $it" }.orEmpty()}", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else Text("暂无可靠的地点体验资料。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        val attributes = experience.obj("attributes")
        attributes.forEach { (key, value) ->
            val label = value.jsonPrimitiveOrText()
            if (label.isNotBlank()) Text("${experienceLabel(key)}：$label", fontSize = 12.sp)
        }
        val route = s.nearbyRoute
        if (route != null) {
            HorizontalDivider(color = Color(0xFFE8E6DC))
            Text("从搜索中心出发 · ${if (s.nearbyRouteMode == "walk") "步行" else "驾车"}", fontWeight = FontWeight.SemiBold, color = DeepTeal)
            Text("${route.text("distance_meters").ifBlank { "距离未知" }} 米 · ${route.text("duration_seconds").toLongOrNull()?.div(60)?.let { "约 $it 分钟" } ?: "用时未知"}", fontSize = 13.sp)
            NearbyMap(s, vm, showRoute = true) { lng, lat -> vm.setNearbyCenter(lng, lat, "地图选点", "manual_map") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { vm.nearbyRoute(place, "walk") }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("步行路线") }
            OutlinedButton(onClick = { vm.nearbyRoute(place, "driving") }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("驾车路线") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(onClick = { onOpenPlace(place.placeId()) }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("完整地点详情") }
            OutlinedButton(onClick = { vm.assistant(place) }, enabled = !s.busy, modifier = Modifier.weight(1f)) { Text("问问 AI") }
        }
    }
}

@Composable
private fun NearbyCompare(s: TourismState, vm: TourismViewModel) {
    AppCard(color = Color(0xFFE9EEE4)) {
        Text("一起比较", style = MaterialTheme.typography.titleLarge, color = Ink)
        Text("已保存 ${s.comparedPlaces.size} 个真实地点；搜索条件变化后仍会保留。", fontSize = 12.sp)
        s.comparedPlaces.forEach { place ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(place.text("name"), fontWeight = FontWeight.SemiBold, color = Ink)
                    Text("${categoryName(place.text("category"))} · 评分 ${place.text("rating").ifBlank { "未知" }} · 人均 ${place.obj("price").text("amount").ifBlank { "未知" }}", fontSize = 11.sp)
                }
                TextButton(onClick = { vm.toggleCompare(place) }) { Text("移除") }
            }
        }
    }
}

private fun experienceLabel(value: String): String = when (value) {
    "outdoor" -> "户外体验"; "indoor" -> "室内体验"; "shaded" -> "遮阴情况"; "accessibility" -> "无障碍"
    "family_friendly" -> "适合家庭"; "crowd_level" -> "人流情况"; "best_time" -> "建议时段"; else -> value.replace('_', ' ')
}

private fun JsonElement.jsonPrimitiveOrText(): String = when (this) {
    is JsonPrimitive -> contentOrNull.orEmpty()
    is JsonObject -> text("label").ifBlank { text("value") }
    else -> ""
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun NearbyMap(s: TourismState, vm: TourismViewModel, showRoute: Boolean = false, onPick: (Double, Double) -> Unit) {
    val center = s.nearbyCenter ?: return
    if (BuildConfig.AMAP_WEB_KEY.isBlank()) {
        QuietState("地图服务尚未配置", "你仍可使用已选真实中心、坐标、附近搜索、地点比较和路线查询。")
        return
    }
    val data = remember(center, s.nearbyPlaces, s.nearbySelectedPlace, s.nearbyRoute, showRoute) {
        buildJsonObject {
            put("center", buildJsonArray { add(center.longitude); add(center.latitude) })
            put("points", buildJsonArray {
                add(buildJsonObject { put("name", center.label); put("lng", center.longitude); put("lat", center.latitude); put("kind", "center") })
                s.nearbyPlaces.forEachIndexed { index, place ->
                    val location = place.obj("location")
                    val lng = location["longitude"]?.jsonPrimitive?.doubleOrNull
                    val lat = location["latitude"]?.jsonPrimitive?.doubleOrNull
                    if (lng != null && lat != null) add(buildJsonObject {
                        put("name", place.text("name")); put("lng", lng); put("lat", lat); put("index", index); put("kind", "place")
                    })
                }
            })
            put("paths", buildJsonArray {
                if (showRoute) s.nearbyRoute?.rows("path")?.takeIf { it.isNotEmpty() }?.let { path -> add(buildJsonArray {
                    path.forEach { point ->
                        val lng = point["longitude"]?.jsonPrimitive?.doubleOrNull ?: point["lng"]?.jsonPrimitive?.doubleOrNull
                        val lat = point["latitude"]?.jsonPrimitive?.doubleOrNull ?: point["lat"]?.jsonPrimitive?.doubleOrNull
                        if (lng != null && lat != null) add(buildJsonArray { add(lng); add(lat) })
                    }
                }) }
            })
        }.toString()
    }
    val html = remember(data) { nearbyMapDocument(data) }
    val currentPick by rememberUpdatedState(onPick)
    val currentSelect by rememberUpdatedState<(Int) -> Unit> { index -> s.nearbyPlaces.getOrNull(index)?.let(vm::selectNearbyPlace) }
    AndroidView(
        factory = { context -> WebView(context).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = false
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            addJavascriptInterface(NearbyMapBridge({ lng, lat -> currentPick(lng, lat) }, { index -> currentSelect(index) }), "NativeNearby")
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: android.webkit.WebResourceRequest?): Boolean = true
            }
            loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null)
            tag = html
        } },
        update = { view -> if (view.tag != html) { view.tag = html; view.loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null) } },
        onRelease = { it.removeJavascriptInterface("NativeNearby"); it.stopLoading(); it.destroy() },
        modifier = Modifier.fillMaxWidth().height(280.dp).clip(RoundedCornerShape(20.dp)),
    )
}

private class NearbyMapBridge(private val onCenter: (Double, Double) -> Unit, private val onPlace: (Int) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    @JavascriptInterface fun selectCenter(longitude: Double, latitude: Double) { main.post { onCenter(longitude, latitude) } }
    @JavascriptInterface fun selectPlace(index: Int) { main.post { onPlace(index) } }
}

private fun nearbyMapDocument(data: String): String = """
<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><style>
html,body,#map{margin:0;width:100%;height:100%;overflow:hidden;background:#e9eee4;font-family:sans-serif}#status{position:absolute;z-index:10;top:10px;left:10px;right:10px;padding:10px 12px;border-radius:14px;background:#fffdf7;color:#183a38;font-size:12px}.pin{width:27px;height:27px;border-radius:50%;border:2px solid white;background:#287d70;color:white;line-height:27px;text-align:center;box-shadow:0 2px 8px #183a3866}.center{background:#dd815d}.hint{position:absolute;z-index:10;bottom:12px;left:12px;right:12px;padding:10px;border-radius:14px;background:#fffdf7d9;color:#183a38;font-size:11px}
</style></head><body><div id="map"></div><div id="status">地图加载中…</div><div class="hint">点击地图可重新选择附近搜索中心；点按编号选择地点</div><script>
const data=JSON.parse(${JsonPrimitive(data).toString().replace("<", "\\u003c")});
window._AMapSecurityConfig={securityJsCode:${JsonPrimitive(BuildConfig.AMAP_SECURITY_CODE)}};
function fail(){document.getElementById('status').textContent='地图暂时无法加载；可使用上方坐标输入选择中心。'}window.onerror=fail;const timer=setTimeout(fail,20000);
function ready(){try{const map=new AMap.Map('map',{viewMode:'2D',zoom:14,center:data.center,resizeEnable:true});const markers=[];data.points.forEach(p=>{const isCenter=p.kind==='center';const marker=new AMap.Marker({position:[p.lng,p.lat],title:p.name,content:'<div class="pin '+(isCenter?'center':'')+'">'+(isCenter?'⌖':((p.index||0)+1))+'</div>',anchor:'center'});marker.on('click',()=>{if(isCenter)window.NativeNearby.selectCenter(p.lng,p.lat);else window.NativeNearby.selectPlace(p.index)});markers.push(marker)});if(markers.length)map.add(markers);data.paths.forEach(path=>map.add(new AMap.Polyline({path,strokeColor:'#287d70',strokeWeight:5,showDir:true})));if(data.points.length>1)map.setFitView(markers,false,[45,45,45,45],13);map.on('click',event=>window.NativeNearby.selectCenter(event.lnglat.getLng(),event.lnglat.getLat()));map.on('complete',()=>{clearTimeout(timer);document.getElementById('status').style.display='none'});}catch(e){fail()}}
const script=document.createElement('script');script.src='https://webapi.amap.com/maps?v=2.0&key='+encodeURIComponent(${JsonPrimitive(BuildConfig.AMAP_WEB_KEY)})+'&callback=ready';script.onerror=fail;document.head.appendChild(script);
</script></body></html>
""".trimIndent()
