package com.sinbha.app

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.regex.Pattern

/**
 * Step D1: Android Screen Agent Accessibility Service
 * 
 * Capabilities:
 * - Reads screen structure from Accessibility Node Tree (text and element roles)
 * - Actions: tap element, tap coordinates, type text, scroll, back, home, open app
 * - Never-touch list for banking, UPI, payment apps, and password managers
 * - Strictly rejects passwords, OTPs, and credit card numbers
 * - Floating "SINBHA is controlling your phone" indicator with emergency STOP button
 * - Real-time step results reported to companion service
 */
class SinbhaAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "SinbhaAccessibility"

        @Volatile
        var instance: SinbhaAccessibilityService? = null
            private set

        fun isRunning(): Boolean = instance != null

        // Never-touch list: Banking, UPI, payment apps, and password managers
        val NEVER_TOUCH_PACKAGES = setOf(
            // UPI & Payments (India & Global)
            "com.google.android.apps.nbu.paisa.user", // Google Pay (Tez)
            "com.phonepe.app",                       // PhonePe
            "net.one97.paytm",                       // Paytm
            "in.org.npci.upiapp",                    // BHIM UPI
            "com.dreamplug.androidapp",              // CRED
            "com.freecharge.android",                // Freecharge
            "com.mobikwik_new",                      // MobiKwik
            "com.paypal.android.p2pmobile",          // PayPal
            // Indian Banking Apps
            "com.sbi.lotusintouch",                  // YONO SBI
            "com.hdfcbank.android",                  // HDFC Bank MobileBanking
            "com.csam.icici.bank.imobile",           // iMobile Pay by ICICI
            "com.axis.mobile",                       // Axis Mobile
            "com.kotak.mobile",                      // Kotak - 811 & Mobile Banking
            "com.bankofbaroda.mconnect",             // bob World
            "com.canarabank.mobility",               // Canara ai1
            "com.pnb.pnbone",                        // PNB ONE
            "com.unionbank.ecommerce.mobile.android", // Vyom Union Bank
            // Password Managers & 2FA Authenticators
            "com.x8bit.bitwarden",                   // Bitwarden
            "com.agilebits.onepassword",             // 1Password
            "com.lastpass.lpandroid",                // LastPass
            "com.dashlane",                          // Dashlane
            "com.nordpass.android",                  // NordPass
            "keepass2android.keepass2android",       // KeePass2Android
            "com.google.android.apps.authenticator2",// Google Authenticator
            "com.authy.authy",                       // Authy
            "com.microsoft.authenticator"            // Microsoft Authenticator
        )

        // Actions gated for safety (Section 14A & D1 Invariants)
        val GATED_ACTION_VERBS = setOf(
            "send", "post", "submit", "buy", "pay", "delete", "remove", "install", "share", "transfer"
        )
    }

    private var currentPackage: String = ""
    private var isControlling: Boolean = false
    private var windowManager: WindowManager? = null
    private var overlayView: View? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.i(TAG, "🌸 SinbhaAccessibilityService connected and ready.")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        val pkg = event.packageName?.toString() ?: ""
        if (pkg.isNotEmpty()) {
            currentPackage = pkg
        }
    }

    override fun onInterrupt() {
        Log.w(TAG, "SinbhaAccessibilityService interrupted.")
        hideControlIndicator()
    }

    override fun onDestroy() {
        super.onDestroy()
        hideControlIndicator()
        instance = null
        Log.i(TAG, "SinbhaAccessibilityService destroyed.")
    }

    fun getCurrentPackageName(): String {
        return currentPackage.ifEmpty {
            rootInActiveWindow?.packageName?.toString() ?: ""
        }
    }

    fun isCurrentAppNeverTouch(): Boolean {
        val pkg = getCurrentPackageName().lowercase()
        return NEVER_TOUCH_PACKAGES.any { it.lowercase() == pkg }
    }

    // =========================================================================
    // 1. SCREEN TREE READING (Text & Element Structure over Pixels)
    // =========================================================================

    /**
     * Traverses the active window and builds a structured JSON accessibility tree.
     * Respects privacy: never dumps password fields or sensitive banking windows.
     */
    fun dumpScreenTree(): JSONObject {
        val result = JSONObject()
        val pkg = getCurrentPackageName()
        result.put("package", pkg)

        if (isCurrentAppNeverTouch()) {
            result.put("success", false)
            result.put("error", "NEVER_TOUCH_APP")
            result.put("message", "Inspection blocked: active app '$pkg' is in the safety never-touch list.")
            return result
        }

        val rootNode = rootInActiveWindow
        if (rootNode == null) {
            result.put("success", false)
            result.put("error", "ROOT_NODE_NULL")
            result.put("message", "Could not retrieve root accessibility node (window may be secure or transitioning).")
            return result
        }

        val nodesArray = JSONArray()
        val visibleTextBuilder = StringBuilder()

        try {
            traverseNode(rootNode, nodesArray, visibleTextBuilder)
            result.put("success", true)
            result.put("package", pkg)
            result.put("nodes_count", nodesArray.length())
            result.put("nodes", nodesArray)
            result.put("visible_text", visibleTextBuilder.toString().trim())
            result.put("is_untrusted_data", true)
        } catch (e: Exception) {
            result.put("success", false)
            result.put("error", e.message ?: "Failed to traverse node tree")
        } finally {
            rootNode.recycle()
        }

        return result
    }

    private fun traverseNode(
        node: AccessibilityNodeInfo,
        nodesArray: JSONArray,
        textBuilder: StringBuilder,
        depth: Int = 0
    ) {
        if (!node.isVisibleToUser) return

        val text = node.text?.toString()?.trim() ?: ""
        val contentDesc = node.contentDescription?.toString()?.trim() ?: ""
        val isPassword = node.isPassword
        val bounds = Rect()
        node.getBoundsInScreen(bounds)

        // Only record nodes with visible area on screen
        if (bounds.width() > 0 && bounds.height() > 0) {
            val nodeObj = JSONObject()
            nodeObj.put("class", node.className?.toString() ?: "")
            nodeObj.put("view_id", node.viewIdResourceName ?: "")
            nodeObj.put("bounds", JSONObject().apply {
                put("left", bounds.left)
                put("top", bounds.top)
                put("right", bounds.right)
                put("bottom", bounds.bottom)
                put("center_x", bounds.centerX())
                put("center_y", bounds.centerY())
            })
            nodeObj.put("is_clickable", node.isClickable)
            nodeObj.put("is_editable", node.isEditable)
            nodeObj.put("is_scrollable", node.isScrollable)
            nodeObj.put("is_password", isPassword)

            // Strictly scrub password fields from text tree
            if (isPassword) {
                nodeObj.put("text", "••••••••")
                nodeObj.put("content_desc", "[PASSWORD FIELD]")
            } else {
                nodeObj.put("text", text)
                nodeObj.put("content_desc", contentDesc)
                if (text.isNotEmpty()) {
                    textBuilder.append(text).append("\n")
                } else if (contentDesc.isNotEmpty()) {
                    textBuilder.append(contentDesc).append("\n")
                }
            }

            nodesArray.put(nodeObj)
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            traverseNode(child, nodesArray, textBuilder, depth + 1)
            child.recycle()
        }
    }

    // =========================================================================
    // 2. ELEMENT & GESTURE ACTIONS
    // =========================================================================

    /**
     * Taps an element matching accessible text, contentDescription, or view_id.
     */
    fun tapElement(target: String): JSONObject {
        val result = JSONObject()
        val pkg = getCurrentPackageName()

        if (isCurrentAppNeverTouch()) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "Tap refused: active app '$pkg' is in the safety never-touch list.")
            }
        }

        val rootNode = rootInActiveWindow ?: return result.apply {
            put("success", false)
            put("error", "NO_ROOT_NODE")
            put("message", "Cannot tap: no active window found.")
        }

        showControlIndicator("Tapping '$target'...")

        val cleanTarget = target.trim().lowercase()
        val matchedNode = findMatchingNode(rootNode, cleanTarget)

        if (matchedNode != null) {
            val clicked = performClickWithFallback(matchedNode)
            matchedNode.recycle()
            rootNode.recycle()
            return result.apply {
                put("success", clicked)
                put("action", "tap_element")
                put("target", target)
                put("message", if (clicked) "Tapped '$target'" else "Failed to click node for '$target'")
            }
        }

        rootNode.recycle()
        return result.apply {
            put("success", false)
            put("error", "ELEMENT_NOT_FOUND")
            put("message", "Element matching '$target' was not found on screen.")
        }
    }

    private fun findMatchingNode(node: AccessibilityNodeInfo, target: String): AccessibilityNodeInfo? {
        val text = node.text?.toString()?.lowercase() ?: ""
        val desc = node.contentDescription?.toString()?.lowercase() ?: ""
        val viewId = node.viewIdResourceName?.lowercase() ?: ""

        if (text == target || desc == target || viewId.endsWith(target)) {
            return node
        }
        if (text.contains(target) || desc.contains(target)) {
            return node
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findMatchingNode(child, target)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    private fun performClickWithFallback(node: AccessibilityNodeInfo): Boolean {
        // Try direct ACTION_CLICK on node or its clickable parents
        var curr: AccessibilityNodeInfo? = node
        while (curr != null) {
            if (curr.isClickable) {
                val ok = curr.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                if (ok) return true
            }
            curr = curr.parent
        }

        // Fallback to coordinate gesture tap on center
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() > 0 && bounds.height() > 0) {
            return tapCoordinatesSync(bounds.centerX().toFloat(), bounds.centerY().toFloat())
        }
        return false
    }

    /**
     * Taps exact screen coordinates via GestureDescription.
     */
    fun tapCoordinates(x: Float, y: Float): JSONObject {
        val result = JSONObject()
        if (isCurrentAppNeverTouch()) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "Tap coordinates refused: active app is in never-touch list.")
            }
        }

        showControlIndicator("Tapping ($x, $y)...")
        val success = tapCoordinatesSync(x, y)
        return result.apply {
            put("success", success)
            put("action", "tap_coordinates")
            put("x", x)
            put("y", y)
            put("message", if (success) "Tapped at ($x, $y)" else "Gesture tap failed")
        }
    }

    private fun tapCoordinatesSync(x: Float, y: Float): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val path = Path().apply {
            moveTo(x, y)
            lineTo(x, y)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 60)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()

        val latch = CountDownLatch(1)
        var completed = false

        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                completed = true
                latch.countDown()
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                completed = false
                latch.countDown()
            }
        }, null)

        try {
            latch.await(1500, TimeUnit.MILLISECONDS)
        } catch (e: InterruptedException) {
            return false
        }
        return completed
    }

    /**
     * Types text into the focused or specified editable field.
     * Strictly validates against passwords, OTPs, and card numbers.
     */
    fun typeText(text: String, targetField: String? = null): JSONObject {
        val result = JSONObject()
        val pkg = getCurrentPackageName()

        if (isCurrentAppNeverTouch()) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "Typing refused: active app '$pkg' is in the safety never-touch list.")
            }
        }

        // Secret validation check
        val safe = validateSafeTyping(text)
        if (!safe.first) {
            return result.apply {
                put("success", false)
                put("error", "SECRET_TYPING_REFUSED")
                put("message", safe.second)
            }
        }

        showControlIndicator("Typing text...")
        val rootNode = rootInActiveWindow ?: return result.apply {
            put("success", false)
            put("error", "NO_ROOT_NODE")
            put("message", "Cannot type: no active window.")
        }

        // Find editable node
        var editNode: AccessibilityNodeInfo? = null
        if (!targetField.isNullOrBlank()) {
            editNode = findMatchingNode(rootNode, targetField.trim().lowercase())
        }
        if (editNode == null || !editNode.isEditable) {
            editNode = findFocusedOrFirstEditable(rootNode)
        }

        if (editNode == null) {
            rootNode.recycle()
            return result.apply {
                put("success", false)
                put("error", "NO_EDITABLE_FIELD")
                put("message", "No editable input field found on screen.")
            }
        }

        // Refuse if target node is flagged as a password field
        if (editNode.isPassword) {
            editNode.recycle()
            rootNode.recycle()
            return result.apply {
                put("success", false)
                put("error", "PASSWORD_FIELD_REFUSED")
                put("message", "Automated typing into password fields is strictly forbidden.")
            }
        }

        val arguments = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        val typed = editNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)

        editNode.recycle()
        rootNode.recycle()

        return result.apply {
            put("success", typed)
            put("action", "type_text")
            put("chars_typed", text.length)
            put("message", if (typed) "Typed text successfully" else "Failed to set text on input field")
        }
    }

    private fun findFocusedOrFirstEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isFocused && node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findFocusedOrFirstEditable(child)
            if (found != null) return found
            child.recycle()
        }
        // Fallback to any editable node
        if (node.isEditable) return node
        return null
    }

    /**
     * Scrolls the current window forward or backward.
     */
    fun scroll(forward: Boolean = true): JSONObject {
        val result = JSONObject()
        if (isCurrentAppNeverTouch()) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "Scroll refused: active app is in never-touch list.")
            }
        }

        showControlIndicator("Scrolling...")
        val rootNode = rootInActiveWindow ?: return result.apply {
            put("success", false)
            put("error", "NO_ROOT_NODE")
        }

        val action = if (forward) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        val scrollableNode = findScrollableNode(rootNode)

        var scrolled = false
        if (scrollableNode != null) {
            scrolled = scrollableNode.performAction(action)
            scrollableNode.recycle()
        }

        // Gesture swipe fallback if standard action fails
        if (!scrolled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            val displayMetrics = resources.displayMetrics
            val cx = (displayMetrics.widthPixels / 2).toFloat()
            val startY = if (forward) (displayMetrics.heightPixels * 0.75).toFloat() else (displayMetrics.heightPixels * 0.25).toFloat()
            val endY = if (forward) (displayMetrics.heightPixels * 0.25).toFloat() else (displayMetrics.heightPixels * 0.75).toFloat()

            val path = Path().apply {
                moveTo(cx, startY)
                lineTo(cx, endY)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, 300)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()
            dispatchGesture(gesture, null, null)
            scrolled = true
        }

        rootNode.recycle()
        return result.apply {
            put("success", scrolled)
            put("action", "scroll")
            put("direction", if (forward) "forward" else "backward")
            put("message", if (scrolled) "Scrolled successfully" else "No scrollable container found")
        }
    }

    private fun findScrollableNode(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isScrollable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findScrollableNode(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    fun pressBack(): JSONObject {
        val ok = performGlobalAction(GLOBAL_ACTION_BACK)
        return JSONObject().apply {
            put("success", ok)
            put("action", "press_back")
            put("message", if (ok) "Pressed Back" else "Global back action failed")
        }
    }

    fun pressHome(): JSONObject {
        val ok = performGlobalAction(GLOBAL_ACTION_HOME)
        return JSONObject().apply {
            put("success", ok)
            put("action", "press_home")
            put("message", if (ok) "Pressed Home" else "Global home action failed")
        }
    }

    fun openAppByPackage(packageName: String): JSONObject {
        val result = JSONObject()
        if (NEVER_TOUCH_PACKAGES.any { it.equals(packageName.trim(), ignoreCase = true) }) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "App '$packageName' is in the safety never-touch list and cannot be controlled.")
            }
        }

        val launchIntent = packageManager.getLaunchIntentForPackage(packageName.trim())
        if (launchIntent == null) {
            return result.apply {
                put("success", false)
                put("error", "APP_NOT_INSTALLED")
                put("message", "App package '$packageName' is not installed on this device.")
            }
        }

        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        try {
            startActivity(launchIntent)
            return result.apply {
                put("success", true)
                put("action", "open_app")
                put("package", packageName)
                put("message", "Opened $packageName")
            }
        } catch (e: Exception) {
            return result.apply {
                put("success", false)
                put("error", e.message ?: "Failed to launch activity")
            }
        }
    }

    // =========================================================================
    // 3. SCREENSHOT CAPTURE (Vision Verification Fallback)
    // =========================================================================

    /**
     * Takes screenshot via AccessibilityService takeScreenshot API (Android 11+).
     * Refuses capture if active window is in never-touch list.
     */
    fun captureScreenBase64(): JSONObject {
        val result = JSONObject()
        val pkg = getCurrentPackageName()

        if (isCurrentAppNeverTouch()) {
            return result.apply {
                put("success", false)
                put("error", "NEVER_TOUCH_APP")
                put("message", "Screenshot refused: active app '$pkg' is in the never-touch list.")
            }
        }

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return result.apply {
                put("success", false)
                put("error", "API_TOO_LOW")
                put("message", "takeScreenshot requires Android 11 (API 30) or higher.")
            }
        }

        val latch = CountDownLatch(1)
        var base64Jpeg = ""
        var errorMsg = ""

        takeScreenshot(
            0,
            mainHandler::post,
            object : TakeScreenshotCallback {
                override fun onSuccess(screenshotResult: ScreenshotResult) {
                    try {
                        val hardwareBuffer = screenshotResult.hardwareBuffer
                        val colorSpace = screenshotResult.colorSpace
                        val bitmap = Bitmap.wrapHardwareBuffer(hardwareBuffer, colorSpace)
                            ?.copy(Bitmap.Config.ARGB_8888, false)
                        hardwareBuffer.close()

                        if (bitmap != null) {
                            val stream = ByteArrayOutputStream()
                            // Downscale for efficient vision LLM transit
                            val scaled = Bitmap.createScaledBitmap(bitmap, 720, 1280, true)
                            scaled.compress(Bitmap.CompressFormat.JPEG, 75, stream)
                            base64Jpeg = Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
                            bitmap.recycle()
                            scaled.recycle()
                        } else {
                            errorMsg = "Failed to convert hardware buffer to bitmap."
                        }
                    } catch (e: Exception) {
                        errorMsg = e.message ?: "Error processing screenshot"
                    } finally {
                        latch.countDown()
                    }
                }

                override fun onFailure(errorCode: Int) {
                    errorMsg = "takeScreenshot failed with error code: $errorCode"
                    latch.countDown()
                }
            }
        )

        try {
            latch.await(3000, TimeUnit.MILLISECONDS)
        } catch (e: InterruptedException) {
            return result.apply {
                put("success", false)
                put("error", "TIMEOUT")
                put("message", "Screenshot capture timed out.")
            }
        }

        if (base64Jpeg.isNotEmpty()) {
            return result.apply {
                put("success", true)
                put("base64", base64Jpeg)
                put("package", pkg)
            }
        }

        return result.apply {
            put("success", false)
            put("error", "CAPTURE_FAILED")
            put("message", errorMsg)
        }
    }

    // =========================================================================
    // 4. FLOATING CONTROL OVERLAY & STOP BUTTON
    // =========================================================================

    fun showControlIndicator(actionText: String = "Controlling phone...") {
        isControlling = true
        mainHandler.post {
            try {
                if (overlayView == null) {
                    windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
                    val layout = LinearLayout(this).apply {
                        orientation = LinearLayout.HORIZONTAL
                        setBackgroundColor(Color.parseColor("#E61A1A24")) // Semi-transparent dark
                        setPadding(32, 16, 32, 16)
                        gravity = Gravity.CENTER_VERTICAL
                    }

                    val textV = TextView(this).apply {
                        text = "🌸 SINBHA is controlling your phone"
                        setTextColor(Color.WHITE)
                        textSize = 12f
                        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f)
                    }

                    val stopBtn = Button(this).apply {
                        text = "STOP 🛑"
                        setBackgroundColor(Color.parseColor("#EF4444"))
                        setTextColor(Color.WHITE)
                        textSize = 12f
                        setOnClickListener {
                            stopAutomationImmediately()
                        }
                    }

                    layout.addView(textV)
                    layout.addView(stopBtn)

                    val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY
                    } else {
                        @Suppress("DEPRECATION")
                        WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
                    }

                    val params = WindowManager.LayoutParams(
                        WindowManager.LayoutParams.MATCH_PARENT,
                        WindowManager.LayoutParams.WRAP_CONTENT,
                        type,
                        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                        PixelFormat.TRANSLUCENT
                    ).apply {
                        gravity = Gravity.TOP
                    }

                    windowManager?.addView(layout, params)
                    overlayView = layout
                }
            } catch (e: Exception) {
                Log.w(TAG, "Could not show accessibility overlay: ${e.message}")
            }
        }
    }

    fun hideControlIndicator() {
        isControlling = false
        mainHandler.post {
            try {
                overlayView?.let {
                    windowManager?.removeView(it)
                    overlayView = null
                }
            } catch (e: Exception) {
                // Ignore removal errors
            }
        }
    }

    fun stopAutomationImmediately() {
        Log.i(TAG, "🛑 User clicked Emergency STOP on accessibility overlay.")
        hideControlIndicator()
        // Notify companion service to report emergency stop
        val intent = Intent(this, SinbhaCompanionService::class.java).apply {
            action = "ACTION_EMERGENCY_STOP"
        }
        startService(intent)
    }

    // =========================================================================
    // 5. SECRET & SAFE TYPING VALIDATION
    // =========================================================================

    private fun validateSafeTyping(text: String): Pair<Boolean, String> {
        val lower = text.lowercase()
        if (lower.contains("password") || lower.contains("passcode") || lower.contains("passwd")) {
            return Pair(false, "Automated typing of passwords is strictly forbidden.")
        }
        if (Pattern.compile("\\b\\d{6}\\b").matcher(text).find() && (lower.contains("otp") || lower.contains("code") || lower.contains("pin"))) {
            return Pair(false, "Automated typing of OTP verification codes is strictly forbidden.")
        }
        if (Pattern.compile("\\b(?:\\d[ -]*?){13,19}\\b").matcher(text).find()) {
            return Pair(false, "Automated typing of credit/debit card numbers is strictly forbidden.")
        }
        return Pair(true, "")
    }
}
