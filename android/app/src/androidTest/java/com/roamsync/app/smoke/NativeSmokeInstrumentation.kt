package com.roamsync.app.smoke

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.os.SystemClock
import android.view.KeyEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.io.File

/** Small device smoke using the public Android accessibility test API, with no app backdoor.
 * Invoke with `adb shell am instrument -w -e pairingCode <one-use-code>
 * -e baseUrl http://127.0.0.1:18003/ <debug-package>.test/
 * com.roamsync.app.smoke.NativeSmokeInstrumentation` after adb reverse and installing both APKs.
 * Test data stays in the isolated service, explicitly labelled Android模拟器验收.
 * No server credential, owner identifier, direct repository call, or Trip creation is used.
 */
class NativeSmokeInstrumentation : Instrumentation() {
    private lateinit var args: Bundle
    private lateinit var evidence: File
    private var paired = false
    private var stage = "launch"
    private var marker = "Android模拟器验收-${System.currentTimeMillis()}"

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        args = arguments ?: Bundle()
        start()
    }

    override fun onStart() {
        val results = Bundle()
        try {
            evidence = File(targetContext.getExternalFilesDir(null), "native-smoke/run-${System.currentTimeMillis()}").apply { mkdirs() }
            val intent = targetContext.packageManager.getLaunchIntentForPackage(targetContext.packageName)
                ?: error("MainActivity launch intent missing")
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            targetContext.startActivity(intent)
            if (args.getString("mode").orEmpty().startsWith("product")) {
                waitFor("探索", 30_000)
                productConnection()
                if (args.getString("mode") == "product-explore") productExplore()
                else if (args.getString("mode") == "product-draft") productDraft()
                else productJourney()
            } else if (args.getString("mode") == "inspect") {
                dump("inspect")
            } else {
                connect()
                if (args.getString("mode") == "route") assistantRoute()
                else if (args.getString("mode") == "trips") tripsReadOnly()
                else {
                    if (args.getString("resumeExisting") != "true") preferences()
                    drafts()
                    if (args.getString("assistantRoute") == "true") assistantRoute()
                    tripsReadOnly()
                }
            }
            results.putString("stream", "PASS native Android UI smoke; marker=$marker; evidence=${evidence.absolutePath}\n")
            finish(Activity.RESULT_OK, results)
        } catch (error: Throwable) {
            // The one-time code is never included in diagnostic trees or error messages.
            runCatching { dump("failure-$stage") }
            if (paired) runCatching { screenshot("failure-$stage") }
            results.putString("stream", "FAIL native Android UI smoke at $stage: ${error.javaClass.simpleName}: ${error.message}\nEvidence=${evidence.absolutePath}\n")
            finish(Activity.RESULT_CANCELED, results)
        }
    }

    private fun tapContains(label: String, timeout: Long = 30_000) {
        performClick(findScrolled(label, contains = true, requireClickable = true, timeout = timeout))
    }

    private fun productConnection() {
        checkpoint("product-shell")
        screenshot("product-00-home")
        click("我的")
        tapContains("连接与隐私")
        waitFor("连接统一服务")
        setField("服务根地址", args.getString("baseUrl") ?: "http://127.0.0.1:18004/")
        setField("一次性配对码", args.getString("pairingCode") ?: error("Fresh isolated pairing required"))
        click("保存并连接")
        waitFor("已配对，临时授权仅保存在内存", 30_000)
        paired = true
        click("探索")
        screenshot("product-01-connected-explore")
    }

    private fun productExplore() {
        checkpoint("product-real-explore")
        setField("想去哪里", "成都人民公园")
        tapContains("所在城市")
        setField("所在城市", "成都")
        click("完成")
        click("搜索")
        tapContains("人民公园", 45_000)
        findScrolled("围绕此地问 AI")
        if (all().none { text(it).contains("已收藏") }) click("收藏地点")
        findScrolled("已收藏", contains = true)
        screenshot("product-02-real-place")
        click("查看地图")
        findScrolled("地图", contains = true)
        screenshot("product-03-place-map")
        click("‹")
        if (all().none { text(it) == "已设为路线起点" }) click("设为路线起点")
        findScrolled("已设为路线起点")
        click("‹")
        waitForField("想去哪里", "成都人民公园")
        setField("想去哪里", "成都宽窄巷子景区")
        click("搜索")
        tapContains("宽窄巷子景区", 45_000)
        click("步行路线")
        findScrolled("分钟", contains = true, timeout = 45_000)
        screenshot("product-04-real-walking-route")
        click("‹")
        click("围绕此地问 AI")
        waitFor("统一旅行 AI")
        setField("聊聊旅行", "请介绍当前讨论地点的游览主题，不修改任何旅行。")
        click("发送讨论")
        val deadline = SystemClock.uptimeMillis() + 150_000
        do {
            val nodes = all()
            if (nodes.none { text(it).contains("正在读取真实地点并整理建议") } &&
                field("聊聊旅行")?.text?.toString().orEmpty().isBlank()) break
            SystemClock.sleep(500)
        } while (SystemClock.uptimeMillis() < deadline)
        screenshot("product-05-context-assistant")
        click("完成")
        findScrolled("围绕此地问 AI")
        screenshot("product-06-return-to-place")
        click("‹")
        waitForField("想去哪里", "成都宽窄巷子景区")
        checkpoint("product-explore-return-retained")
    }

    private fun productJourney() {
        checkpoint("product-journey-lifecycle")
        click("旅程")
        for (label in listOf("正在筹划", "即将出发", "正在旅行", "历史旅行")) {
            findScrolled(label, contains = true)
        }
        screenshot("product-07-journey-phases")
        tapContains("正在旅行")
        val title = args.getString("retainedTripTitle") ?: error("Only a dedicated new native test trip is allowed")
        tapContains(title, 45_000)
        findScrolled("已确认的日程")
        check(all().none { text(it) == "手动创建" || text(it) == "旅程总管" }) { "Legacy workbench path remains" }
        scrollTop()
        screenshot("product-08-formal-current-next")
        if (args.getString("mode") == "product-location") {
            checkpoint("product-real-foreground-location")
            click("查询下一站路线")
            SystemClock.sleep(35_000)
            scrollTop()
            dump("product-location-observation")
            val locationError = all().map(::text).firstOrNull {
                it.contains("暂时无法取得新定位") || it.contains("定位精度不足") ||
                    it.contains("定位结果已过期") || it.contains("请先开启系统定位")
            }
            check(locationError == null) { locationError.orEmpty() }
            findScrolled("定位：精度约", contains = true, timeout = 70_000)
            screenshot("product-13-location-result")
            dump("product-13-location-result")
            return
        }
        if (args.getString("mode") !in setOf("product-execution", "product-recovery")) return
        if (args.getString("mode") == "product-execution") {
        checkpoint("product-manual-execution")
        if (all().any { text(it) == "开始这一天的旅行" }) click("开始这一天的旅行")
        findScrolled("我已到达")
        click("我已到达")
        click("开始体验")
        findScrolled("完成这站")
        screenshot("product-09-experience-started")
        click("延长停留")
        click("延长 60 分钟")
        }
        checkpoint("product-recovery-review")
        findScrolled("确认采用调整", timeout = 300_000)
        screenshot("product-10-recovery-before-after")
        click("确认采用调整")
        findScrolled("完成这站", timeout = 45_000)
        screenshot("product-11-recovery-adopted")
        click("完成这站")
        findScrolled("我已到达", timeout = 45_000)
        click("我已到达")
        click("开始体验")
        findScrolled("完成这站")
        screenshot("product-12-next-stop-started")
        uiAutomation.injectInputEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_HOME), true)
        uiAutomation.injectInputEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_HOME), true)
        SystemClock.sleep(1500)
        android.os.ParcelFileDescriptor.AutoCloseInputStream(uiAutomation.executeShellCommand(
            "am start -n ${targetContext.packageName}/com.roamsync.app.MainActivity"
        )).use { it.readBytes() }
        findScrolled("完成这站", timeout = 30_000)
        screenshot("product-14-background-restored")
        checkpoint("product-recovery-accept-continued")
    }

    private fun productDraft() {
        checkpoint("product-draft-restore-edit")
        click("旅程")
        tapContains("正在筹划")
        tapContains(args.getString("retainedTripTitle") ?: error("Dedicated draft required"), 45_000)
        setField("整段旅行的要求", "三个真实地点，轻松游览，保留休息时间。真机编辑保留检查。")
        click("探索")
        click("旅程")
        waitForField("整段旅行的要求", "真机编辑保留检查")
        click("核对并保存")
        click("确认保存")
        screenshot("product-15-draft-saved")
        checkpoint("product-draft-formal-preview")
        click("选择日期")
        click("确定")
        setField("单处停留", "45")
        setField("每日最大步行时间", "180")
        click("查看日期和完整安排")
        findScrolled("待确认的正式安排", timeout = 90_000)
        screenshot("product-16-full-formal-preview")
        click("确认创建并采用这份日程")
        findScrolled("打开正式旅行", timeout = 90_000)
        click("打开正式旅行")
        findScrolled("已确认的日程", timeout = 45_000)
        screenshot("product-17-new-formal-from-draft")
        checkpoint("product-draft-confirmed-formal")
    }

    private fun connect() {
        checkpoint("connection")
        click("连接")
        waitFor("连接统一服务")
        setField("服务根地址", args.getString("baseUrl") ?: "http://127.0.0.1:18003/")
        val code = args.getString("pairingCode") ?: error("A fresh one-use pairingCode argument is required")
        setField("一次性配对码", code)
        click("保存并连接")
        waitFor("已配对，临时授权仅保存在内存", 30_000)
        paired = true
        screenshot("01-paired")
    }

    private fun preferences() {
        checkpoint("preferences-save-refresh")
        click("管理旅行偏好")
        waitFor("我的旅行偏好")
        val checkbox = all().firstOrNull { it.isCheckable } ?: error("No preference checkbox")
        val expectedChecked = !checkbox.isChecked
        performClick(checkbox)
        setField("兴趣关键词", "博物馆，茶馆，$marker")
        click("保存旅行偏好")
        findScrolled("偏好已保存；可刷新重新读取。")
        setField("兴趣关键词", "未保存的临时编辑")
        click("刷新")
        waitForField("兴趣关键词", marker)
        check(all().first { it.isCheckable }.isChecked == expectedChecked) { "Preference category did not persist after refresh" }
        screenshot("02-preferences-refreshed")
        click("探索")
    }

    private fun drafts() {
        checkpoint(if (args.getString("resumeExisting") == "true") "draft-resume-existing" else "draft-create")
        // Some physical-device accessibility implementations expose the selected
        // navigation item as non-clickable. Preferences already returned here.
        if (all().none { text(it) == "日期未定？编辑自由旅行草稿" }) click("探索")
        click("日期未定？编辑自由旅行草稿")
        waitFor("自由旅行草稿")
        if (args.getString("resumeExisting") == "true") {
            // The service returns newest drafts first; resume only explicitly retained test data.
            click("杭州3日自由草稿")
            scrollTop()
            waitForField("生成或修改要求", "Android模拟器验收")
            if (args.getString("resumeAfterModify") == "true") {
                marker = args.getString("retainedMarker") ?: error("resumeAfterModify requires the retained run marker")
            }
        } else {
            setField("三日草稿要求", "$marker 保留的测试草稿。杭州三天，博物馆与茶馆，慢节奏；日期未定。")
            click("创建三日草稿")
            waitFor("生成三日草稿", 30_000)
            screenshot("03-draft-created")
            checkpoint("draft-generate")
            click("生成三日草稿")
        }
        waitGenerated()
        screenshot("04-draft-generated")
        dump("04-draft-generated")

        checkpoint("draft-modify")
        if (args.getString("resumeAfterModify") != "true") {
            setField("生成或修改要求", "$marker 修改：第二天减少步行，保留博物馆；每天最多两个地点。")
            click("按要求修改草稿")
            waitGenerated()
        }
        assertModifiedRun()
        screenshot("05-draft-modified")

        checkpoint("draft-save-reopen")
        click("保存草稿")
        findScrolled("草稿已保存")
        click("‹ 返回")
        scrollTop()
        findScrolled("自由旅行草稿")
        val savedCard = findScrolled("杭州3日自由草稿", requireClickable = true)
        check(subtreeContains(clickable(savedCard)!!, "已保存")) { "Draft list retained stale unsaved state" }
        screenshot("06-list-saved-without-refresh")
        click("杭州3日自由草稿")
        scrollTop()
        assertModifiedRun()
        check(all().any { text(it).contains("已保存") }) { "Reopened draft is not saved" }
        screenshot("06-draft-reopened")

        checkpoint("draft-cancel-restore")
        click("取消草稿")
        waitFor("恢复草稿", 30_000)
        screenshot("07-draft-cancelled")
        click("恢复草稿")
        waitFor("取消草稿", 30_000)
        check(all().any { text(it).contains("已保存") }) { "Restore lost saved status" }
        screenshot("08-draft-restored")
        dump("08-draft-restored")
    }

    private fun assertModifiedRun() {
        val record = findScrolled("$marker 修改", contains = true, timeout = 30_000)
        check(text(record).contains("completed")) { "Modified run is not completed" }
        scrollTop()
    }

    private fun tripsReadOnly() {
        checkpoint("legacy-trips-read-only")
        click("旅程")
        waitFor("我的旅行", 30_000)
        if (args.getString("expectAutoRefresh") == "true") {
            waitFor(args.getString("retainedTripTitle") ?: "第二批原生API联调三日草稿", 30_000)
            val deadline = SystemClock.uptimeMillis() + 30_000
            var settledSince = 0L
            while (SystemClock.uptimeMillis() < deadline) {
                if (all().none { it.className.toString() == "android.widget.ProgressBar" }) {
                    if (settledSince == 0L) settledSince = SystemClock.uptimeMillis()
                    if (SystemClock.uptimeMillis() - settledSince >= 1_000) break
                } else settledSince = 0L
                SystemClock.sleep(250)
            }
            check(settledSince != 0L && SystemClock.uptimeMillis() - settledSince >= 1_000) { "Trip entry did not settle" }
            check(all().none { text(it).contains("请通过本地 RoamSync 页面访问") || text(it).contains("连接授权已过期") }) { "Trip entry retained stale authorization error" }
            screenshot("10-trips-auto-refreshed")
            dump("10-trips-auto-refreshed")
            return
        }
        screenshot("10-trips-entry")
        dump("10-trips-entry")
        click("刷新", timeout = 30_000)
        val deadline = SystemClock.uptimeMillis() + 30_000
        while (all().any { it.className.toString() == "android.widget.ProgressBar" } && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(500)
        screenshot("11-trips-refreshed")
        dump("11-trips-refreshed")
    }

    private fun waitGenerated() {
        val deadline = SystemClock.uptimeMillis() + 240_000
        var settledSince = 0L
        while (SystemClock.uptimeMillis() < deadline) {
            SystemClock.sleep(1_000)
            val nodes = all()
            if (nodes.any { it.className.toString() == "android.widget.ProgressBar" }) { settledSince = 0L; continue }
            val running = nodes.any { text(it).contains("生成进行中") }
            if (!running && nodes.any { text(it) == "按要求修改草稿" && clickable(it)?.isEnabled == true }) {
                if (settledSince == 0L) settledSince = SystemClock.uptimeMillis()
                if (SystemClock.uptimeMillis() - settledSince >= 2_000) {
                    findScrolled("第1天", contains = true)
                    scrollTop()
                    return
                }
                continue
            }
            settledSince = 0L
            // During a long request the physical phone may omit an off-screen
            // progress indicator and expose refresh as disabled. Keep observing;
            // do not turn that legitimate busy state into an early test failure.
            nodes.firstOrNull { text(it) == "刷新" && clickable(it)?.isEnabled == true }
                ?.let { performClick(it) }
        }
        error("Draft generation did not complete within 240 seconds")
    }

    private fun assistantRoute() {
        checkpoint("assistant-route")
        click("探索")
        waitFor("搜索真实地点")
        setField("浏览城市", "杭州")
        setField("搜索景点、美食、住宿", "断桥残雪")
        click("搜索真实地点")
        val origin = findScrolled("断桥残雪", contains = true, requireClickable = true, timeout = 30_000)
        performClick(origin)
        click("设为路线起点")
        click("探索")
        waitFor("搜索真实地点")
        setField("搜索景点、美食、住宿", "灵隐寺")
        click("搜索真实地点")
        val destination = findScrolled("灵隐寺", contains = true, requireClickable = true, timeout = 30_000)
        performClick(destination)
        click("问问这里")
        waitFor("统一旅行 AI")
        setField("聊聊旅行", "$marker 请介绍当前讨论的这个真实地点。")
        click("发送")
        findScrolled("你：$marker", contains = true, timeout = 120_000)
        val shortcutDeadline = SystemClock.uptimeMillis() + 30_000
        var passedCurrentMessage = false
        var clickedCurrentShortcut = false
        while (SystemClock.uptimeMillis() < shortcutDeadline && !clickedCurrentShortcut) {
            val nodes = all()
            val currentMessage = nodes.indexOfFirst { text(it).startsWith("你：$marker") }
            if (currentMessage >= 0) passedCurrentMessage = true
            val shortcut = nodes.withIndex().firstOrNull { (index, node) ->
                text(node) == "从已选起点步行到这里" && clickable(node)?.isEnabled == true &&
                    (if (currentMessage >= 0) index > currentMessage else passedCurrentMessage)
            }?.value
            if (shortcut != null) { performClick(shortcut); clickedCurrentShortcut = true }
            else {
                nodes.firstOrNull { it.isScrollable }?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
                SystemClock.sleep(300)
            }
        }
        check(clickedCurrentShortcut) { "No route shortcut after this run's new message" }
        val route = findScrolled("打开路线地图", requireClickable = true, timeout = 120_000)
        performClick(route)
        waitFor("高德真实步行路线（估计）", 30_000, contains = true)
        waitFor("断桥", contains = true)
        waitFor("灵隐寺", contains = true)
        screenshot("09-assistant-route")
        dump("09-assistant-route")
        // Capture after the map's 20-second load/error boundary as well as its first frame.
        SystemClock.sleep(25_000)
        screenshot("09-route-map-settled")
        dump("09-route-map-settled")
    }

    private fun checkpoint(value: String) {
        stage = value
        sendStatus(0, Bundle().apply { putString("stream", "Native UI: $value\n") })
    }

    private fun all(): List<AccessibilityNodeInfo> {
        if (android.os.Build.VERSION.SDK_INT >= 33) uiAutomation.clearCache()
        val result = mutableListOf<AccessibilityNodeInfo>()
        fun visit(node: AccessibilityNodeInfo?) {
            if (node == null) return
            result.add(node)
            for (i in 0 until node.childCount) visit(node.getChild(i))
        }
        visit(uiAutomation.rootInActiveWindow)
        return result
    }

    private fun text(node: AccessibilityNodeInfo): String = listOfNotNull(node.text, node.contentDescription, node.hintText).joinToString(" ").trim()
    private fun clickable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        repeat(6) {
            if (current?.isClickable == true) return current
            current = current?.parent
        }
        return null
    }
    private fun performClick(node: AccessibilityNodeInfo) {
        val target = clickable(node) ?: error("Node has no clickable parent")
        check(target.isEnabled && target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) { "Click failed" }
        SystemClock.sleep(350)
    }
    private fun click(label: String, timeout: Long = 15_000) {
        val deadline = SystemClock.uptimeMillis() + timeout
        do {
            // Compose may expose a newly added button before the busy recomposition settles.
            if (all().none { it.className.toString() == "android.widget.ProgressBar" }) {
                val node = findScrolled(label, requireClickable = true, timeout = timeout)
                val target = clickable(node)
                if (target?.isEnabled == true && target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    SystemClock.sleep(500)
                    return
                }
            }
            SystemClock.sleep(300)
        } while (SystemClock.uptimeMillis() < deadline)
        error("Cannot click settled UI control: $label")
    }

    private fun waitFor(label: String, timeout: Long = 15_000, contains: Boolean = false): AccessibilityNodeInfo {
        val deadline = SystemClock.uptimeMillis() + timeout
        do {
            all().firstOrNull { if (contains) text(it).contains(label) else text(it) == label }?.let { return it }
            SystemClock.sleep(200)
        } while (SystemClock.uptimeMillis() < deadline)
        error("UI text missing: $label")
    }

    private fun findScrolled(label: String, contains: Boolean = false, requireClickable: Boolean = false, timeout: Long = 15_000): AccessibilityNodeInfo {
        val deadline = SystemClock.uptimeMillis() + timeout
        var attempts = 0
        do {
            val nodes = all()
            nodes.firstOrNull {
                (if (contains) text(it).contains(label) else text(it) == label) && !it.isEditable &&
                    (!requireClickable || clickable(it)?.isEnabled == true)
            }?.let { return it }
            val action = if (attempts % 14 < 7) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            nodes.firstOrNull { it.isScrollable }?.performAction(action)
            attempts++
            SystemClock.sleep(250)
        } while (SystemClock.uptimeMillis() < deadline)
        error("UI control missing: $label")
    }

    private fun subtreeContains(node: AccessibilityNodeInfo, label: String, depth: Int = 4): Boolean =
        text(node).contains(label) || (depth > 0 && (0 until node.childCount).any {
            node.getChild(it)?.let { child -> subtreeContains(child, label, depth - 1) } == true
        })
    private fun field(label: String): AccessibilityNodeInfo? = all().firstOrNull { it.isEditable && subtreeContains(it, label) }
    private fun setField(label: String, value: String) {
        val deadline = SystemClock.uptimeMillis() + 15_000
        var target = field(label)
        while (target == null && SystemClock.uptimeMillis() < deadline) {
            findScrolled(label, contains = true)
            target = field(label)
        }
        check(target != null) { "Editable field missing: $label" }
        check(target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        })) { "Cannot edit field: $label" }
        SystemClock.sleep(250)
        // Dismiss only if an IME actually has a window; otherwise BACK navigates the app.
        if (uiAutomation.windows.any { it.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD }) {
            uiAutomation.injectInputEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_BACK), true)
            uiAutomation.injectInputEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_BACK), true)
        }
    }
    private fun waitForField(label: String, expected: String) {
        val deadline = SystemClock.uptimeMillis() + 30_000
        do {
            if (field(label)?.text?.contains(expected) == true) return
            SystemClock.sleep(250)
        } while (SystemClock.uptimeMillis() < deadline)
        error("Field did not retain expected value: $label")
    }
    private fun scrollTop() {
        repeat(12) { all().firstOrNull { it.isScrollable }?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) }
        SystemClock.sleep(300)
    }
    private fun screenshot(name: String) {
        uiAutomation.takeScreenshot()?.useBitmap { bitmap ->
            File(evidence, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        } ?: error("Android screenshot unavailable")
    }
    private inline fun Bitmap.useBitmap(block: (Bitmap) -> Unit) { try { block(this) } finally { recycle() } }
    private fun dump(name: String) {
        File(evidence, "$name.txt").writeText(all().joinToString("\n") {
            "${it.className} enabled=${it.isEnabled} clickable=${it.isClickable} checked=${it.isChecked} text=${if (it.isEditable) "<editable-redacted>" else redactedText(text(it))}"
        })
    }
    private fun redactedText(value: String): String = when {
        value.contains("GPS WGS84") || value.contains("路线请求 GCJ02") -> "<precise-location-redacted>"
        else -> value.replace(Regex("(?<![0-9])(?:[1-9][0-9]?|1[0-7][0-9])\\.[0-9]{4,}(?![0-9])"), "<coordinate-redacted>")
    }
}
