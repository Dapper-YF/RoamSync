package com.roamsync.app.navigation

import android.content.Context
import android.view.View
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.lang.reflect.Proxy
import javax.inject.Inject
import javax.inject.Singleton

/** The only class that names AMap runtime types. Reflection keeps callback API drift contained. */
@Singleton class AmapNavigationSource @Inject constructor(@ApplicationContext private val context: Context) : NavigationSource {
    private val mutable = MutableStateFlow(NavigationRuntimeState())
    override val state: StateFlow<NavigationRuntimeState> = mutable.asStateFlow()
    private var navi: Any? = null
    private var naviView: View? = null
    private var callbackGeneration = 0L

    private fun init(generation: Long) {
        if (navi != null) return
        val key = com.roamsync.app.BuildConfig.AMAP_ANDROID_KEY
        check(key.isNotBlank()) { "未配置 Android 高德 Key" }
        try {
            val setting = Class.forName("com.amap.api.navi.NaviSetting")
            setting.getMethod("updatePrivacyShow", Context::class.java, Boolean::class.javaPrimitiveType, Boolean::class.javaPrimitiveType).invoke(null, context, true, true)
            setting.getMethod("updatePrivacyAgree", Context::class.java, Boolean::class.javaPrimitiveType).invoke(null, context, true)
            val clazz = Class.forName("com.amap.api.navi.AMapNavi")
            clazz.getMethod("setApiKey", Context::class.java, String::class.java).invoke(null, context, key)
            navi = clazz.getMethod("getInstance", Context::class.java).invoke(null, context)
            val listenerClass = Class.forName("com.amap.api.navi.AMapNaviListener")
            val listener = Proxy.newProxyInstance(listenerClass.classLoader, arrayOf(listenerClass)) { _, method, args ->
                when (method.name) {
                    "onCalculateRouteSuccess", "onCalculateMultipleRoutesSuccess" -> mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.ROUTE_READY, error = null)
                    "onCalculateRouteFailure", "onError" -> mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.FAILED, error = "高德路线规划失败")
                    "onStartNavi" -> mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.NAVIGATING)
                    "onArriveDestination", "onEndEmulatorNavi" -> mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.ARRIVED)
                    // AMap's local reroute is presentation/runtime state.  The
                    // backend route revision remains authoritative until a
                    // future route-revision negotiation endpoint exists.
                    "onReCalculateRouteForYaw", "onReCalculateRouteForTrafficJam" -> mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.REROUTING)
                    "onLocationChange" -> updateLocation(args?.firstOrNull())
                    "onNaviInfoUpdate" -> updateNaviInfo(args?.firstOrNull())
                }; null
            }
            clazz.getMethod("addAMapNaviListener", listenerClass).invoke(navi, listener)
        } catch (e: Exception) { throw IllegalStateException("导航引擎初始化失败：${e.message}", e) }
    }
    private fun updateLocation(location: Any?) {
        location ?: return
        val coordinate = runCatching { location.javaClass.getMethod("getCoord").invoke(location) }.getOrNull() ?: return
        val latitude = runCatching { coordinate.javaClass.getMethod("getLatitude").invoke(coordinate) as Number }.getOrNull()?.toDouble() ?: return
        val longitude = runCatching { coordinate.javaClass.getMethod("getLongitude").invoke(coordinate) as Number }.getOrNull()?.toDouble() ?: return
        val accuracy = runCatching { location.javaClass.getMethod("getAccuracy").invoke(location) as Number }.getOrNull()?.toFloat()
        mutable.value = mutable.value.copy(longitude = longitude, latitude = latitude, locationAccuracyMeters = accuracy)
    }
    override suspend fun calculate(input: NavigationRouteInput, generation: Long) {
        callbackGeneration = generation; mutable.value = NavigationRuntimeState(input.binding, NavigationLifecycle.CALCULATING, generation)
        require(input.coordinateSystem.lowercase() == "gcj02") { "当前正式行程坐标不是 GCJ-02，不能直接交给高德导航" }
        init(generation)
        try {
            val point = Class.forName("com.amap.api.navi.model.NaviLatLng")
            val start = point.getConstructor(Double::class.javaPrimitiveType, Double::class.javaPrimitiveType).newInstance(input.originLatitude, input.originLongitude)
            val end = point.getConstructor(Double::class.javaPrimitiveType, Double::class.javaPrimitiveType).newInstance(input.destinationLatitude, input.destinationLongitude)
            // v11 exposes both a NaviPoi overload and the legacy three-List
            // overload.  Reflection order is not an API contract, so fence the
            // selection by its erased first parameter type instead of taking
            // the first four-argument method.
            val result = navi!!.javaClass.methods.firstOrNull {
                it.name == "calculateDriveRoute" &&
                    it.parameterTypes.size == 4 &&
                    it.parameterTypes[0] == java.util.List::class.java
            }
                ?.invoke(navi, listOf(start), listOf(end), emptyList<Any>(), 0) as? Boolean ?: false
            if (!result) mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.FAILED, error = "高德未接受路线规划请求")
        } catch (e: Exception) { mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.FAILED, error = "路线规划失败：${e.message}") }
    }
    override suspend fun startSimulation(generation: Long) {
        if (generation != callbackGeneration) return
        try {
            navi!!.javaClass.methods.firstOrNull { it.name == "startNavi" && it.parameterTypes.size == 1 }?.invoke(navi, 2)
            mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.NAVIGATING)
        } catch (e: Exception) { mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.FAILED, error = "模拟导航启动失败：${e.message}") }
    }
    override suspend fun stop(generation: Long) {
        callbackGeneration = generation; mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.STOPPING, generation = generation)
        runCatching { navi?.javaClass?.methods?.firstOrNull { it.name == "stopNavi" && it.parameterTypes.isEmpty() }?.invoke(navi) }
        mutable.value = mutable.value.copy(lifecycle = NavigationLifecycle.STOPPED)
    }
    private fun updateNaviInfo(info: Any?) { if (info == null) return; fun value(vararg names: String) = names.firstNotNullOfOrNull { n -> runCatching { info.javaClass.getMethod(n).invoke(info) }.getOrNull() }
        val seconds = (value("getPathRetainTime", "getRouteRemainTime") as? Number)?.toInt(); val meters = (value("getPathRetainDistance", "getRouteRemainDis") as? Number)?.toInt()
        mutable.value = mutable.value.copy(remainingDistanceMeters = meters ?: mutable.value.remainingDistanceMeters, remainingDurationSeconds = seconds ?: mutable.value.remainingDurationSeconds, etaEpochMillis = seconds?.let { System.currentTimeMillis() + it * 1000L }, currentRoad = value("getCurRoadName") as? String, nextInstruction = value("getNextRoadName") as? String)
    }
    override fun createNavigationView(): View? = runCatching { if (naviView == null) { naviView = Class.forName("com.amap.api.navi.AMapNaviView").getConstructor(Context::class.java).newInstance(context) as View; naviView!!.javaClass.methods.firstOrNull { it.name == "onCreate" }?.invoke(naviView, null) }; naviView }.getOrNull()
    override fun releaseNavigationView() { naviView?.let { view -> runCatching { view.javaClass.methods.firstOrNull { it.name == "onDestroy" }?.invoke(view) } }; naviView = null }
}
