package com.roamsync.app.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebResourceRequest
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceError
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.roamsync.app.BuildConfig
import kotlinx.serialization.json.*

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun RouteMap(s: RoamSyncUiState, vm: RoamSyncViewModel) {
    val day = s.day
    val context = LocalContext.current
    var mapError by remember { mutableStateOf(false) }
    var retry by remember { mutableIntStateOf(0) }
    val data = remember(day, s.trip) { buildJsonObject {
        put("center", buildJsonArray { add(s.trip?.longitude ?: 116.397428); add(s.trip?.latitude ?: 39.90923) })
        put("points", buildJsonArray { day?.activities?.forEach { a -> add(buildJsonObject {
            put("name", a.display_name.ifBlank { a.name }); put("lng", a.longitude); put("lat", a.latitude)
        }) } })
        put("paths", buildJsonArray { day?.route_legs?.forEach { leg -> if (leg.path.isNotEmpty()) add(buildJsonArray { leg.path.forEach { point -> add(buildJsonArray { point.forEach { add(it) } }) } }) } })
    }.toString() }
    val html = remember(data) { mapDocument(data) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal = 20.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("walk", "transit", "driving").forEach { mode -> FilterChip(selected = day?.route_mode == mode, onClick = { vm.route(mode) }, enabled = !s.busy && day != null, label = { Text(modeName(mode)) }, shape = CircleShape) }
        }
        if (BuildConfig.AMAP_WEB_KEY.isBlank()) Text("地图服务尚未配置，可使用下方地点在地图应用中导航。", Modifier.padding(20.dp))
        else if (mapError) Column(Modifier.weight(1f).padding(24.dp), verticalArrangement = Arrangement.Center) {
            Text("地图加载遇到问题，请重试，或通过下方地点打开导航。")
            Button(onClick = { mapError = false; retry++ }) { Text("重新加载地图") }
        }
        else key(day?.id, retry) {
            AndroidView(factory = { ctx -> WebView(ctx).apply {
                WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = true
                    override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                        if (request?.isForMainFrame == true) mapError = true
                    }
                    override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                        mapError = true
                        return true
                    }
                }
                loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null)
                tag = html
            } }, update = { view -> if (view.tag != html) { view.tag = html; view.loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null) } },
                onRelease = { it.stopLoading(); it.destroy() }, modifier = Modifier.fillMaxWidth().weight(1f))
        }
        Text("${day?.activities?.size ?: 0} 个地点 · 路线 ${day?.route_legs?.sumOf { it.duration_minutes } ?: 0} 分钟", Modifier.padding(horizontal = 20.dp, vertical = 10.dp), fontSize = 13.sp)
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            day?.activities?.forEachIndexed { i, a -> OutlinedButton(onClick = {
                val uri = Uri.parse("https://uri.amap.com/marker?position=${a.longitude},${a.latitude}&name=${Uri.encode(a.display_name.ifBlank { a.name })}&coordinate=gaode&callnative=1")
                runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri)) }
            }) { Text("${i+1}. ${a.display_name.ifBlank { a.name }}", maxLines = 1) } }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable internal fun CurrentLocationRouteMap(preview: CurrentRoutePreview) {
    if (BuildConfig.AMAP_WEB_KEY.isBlank()) {
        Text("未配置地图公钥；路线距离与用时来自本次真实坐标路线查询。", fontSize = 12.sp)
        return
    }
    val data = remember(preview) { buildJsonObject {
        put("center", buildJsonArray { add(preview.route.origin.longitude); add(preview.route.origin.latitude) })
        put("points", buildJsonArray {
            add(buildJsonObject { put("name", "当前位置"); put("lng", preview.route.origin.longitude); put("lat", preview.route.origin.latitude) })
            add(buildJsonObject { put("name", preview.targetName); put("lng", preview.route.destination.longitude); put("lat", preview.route.destination.latitude) })
        })
        put("paths", buildJsonArray {
            if (preview.route.path.isNotEmpty()) add(buildJsonArray {
                preview.route.path.forEach { point -> add(buildJsonArray { add(point.longitude); add(point.latitude) }) }
            })
        })
    }.toString() }
    val html = remember(data) { mapDocument(data) }
    AndroidView(factory = { ctx -> WebView(ctx).apply {
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = true
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                // Keep the local route geometry visible; mapDocument shows its
                // own bounded loading/error message if the provider script fails.
            }
        }
        loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null)
        tag = html
    } }, update = { view -> if (view.tag != html) { view.tag = html; view.loadDataWithBaseURL("https://roamsync.local/", html, "text/html", "UTF-8", null) } },
        onRelease = { it.stopLoading(); it.destroy() }, modifier = Modifier.fillMaxWidth().height(220.dp))
}

internal fun mapDocument(data: String): String = """
<!doctype html><html lang="zh-CN"><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><style>
html,body{margin:0;width:100vw;height:100vh;overflow:hidden;background:#edf3ee;font-family:sans-serif}#map{position:fixed;inset:0;width:100vw;height:100vh}#status{position:absolute;top:18px;left:18px;right:18px;z-index:100;padding:12px;border-radius:14px;background:#fff;color:#11243f;font-size:13px}.pin{background:#218f84;color:white;border:3px solid white;border-radius:50%;width:25px;height:25px;text-align:center;line-height:25px;box-shadow:0 2px 8px #1234}
.controls{position:absolute;right:12px;bottom:28px;z-index:90;display:flex;flex-direction:column;gap:8px}.controls button{min-width:44px;min-height:44px;border:1px solid #d9e8e3;border-radius:14px;background:white;color:#164d48;box-shadow:0 3px 12px #1232;font-size:16px;padding:8px}
</style></head><body><div id="map"></div><div id="status">正在加载地图…</div><div class="controls"><button id="zoom-in" aria-label="放大地图">＋</button><button id="zoom-out" aria-label="缩小地图">−</button><button id="overview">全览</button></div><script>
const data=JSON.parse(${JsonPrimitive(data).toString().replace("<", "\\u003c")});
window._AMapSecurityConfig={securityJsCode:${JsonPrimitive(BuildConfig.AMAP_SECURITY_CODE)}};
function fail(){document.getElementById('status').textContent='地图暂时无法加载，可使用下方地点打开导航。'}
window.onerror=fail;
const timer=setTimeout(fail,20000);
function ready(){try{
const fit=()=>{document.getElementById('map').style.height=window.innerHeight+'px'};fit();window.addEventListener('resize',fit);
const map=new AMap.Map('map',{viewMode:'2D',zoom:12,center:data.center,resizeEnable:true});
const overlays=data.points.map((p,i)=>new AMap.Marker({position:[p.lng,p.lat],title:p.name,content:'<div class="pin">'+(i+1)+'</div>',anchor:'center'}));
data.paths.forEach(path=>overlays.push(new AMap.Polyline({path,strokeColor:'#218f84',strokeWeight:5,showDir:true})));
map.add(overlays);
function overview(){
// A single scenic-area POI has no bounds: street-level fitting hides its surroundings.
if(data.points.length===1 && data.paths.length===0)map.setZoomAndCenter(11,[data.points[0].lng,data.points[0].lat]);
else if(overlays.length)map.setFitView(overlays,false,[45,65,45,45],14);
else map.setZoomAndCenter(12,data.center);
}
overview();
document.getElementById('zoom-in').onclick=()=>map.zoomIn();
document.getElementById('zoom-out').onclick=()=>map.zoomOut();
document.getElementById('overview').onclick=overview;
AMap.plugin(['AMap.Scale'],()=>map.addControl(new AMap.Scale()));
map.on('complete',()=>{clearTimeout(timer);document.getElementById('status').style.display='none'});
}catch(e){fail()}}
const script=document.createElement('script');script.src='https://webapi.amap.com/maps?v=2.0&key='+encodeURIComponent(${JsonPrimitive(BuildConfig.AMAP_WEB_KEY)})+'&callback=ready';script.onerror=fail;document.head.appendChild(script);
</script></body></html>
""".trimIndent()
