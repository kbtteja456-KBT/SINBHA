package com.sinbha.app

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.net.Uri
import android.os.Build
import android.provider.AlarmClock
import android.provider.MediaStore
import android.provider.Settings
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.net.URLEncoder

/**
 * Result of an Android app launch attempt.
 * Contains package name, method, and background launch readiness status.
 */
data class LaunchResult(
    val success: Boolean,
    val app: String,
    val packageName: String? = null,
    val method: String? = null,
    val error: String? = null,
    val needsTap: Boolean = false,
    val needsOverlayPermission: Boolean = false
)

/**
 * Universal native application launcher for Android (Step C2.5 & C2.6).
 * Resolves installed apps with PackageManager queryIntentActivities,
 * checks Android background-activity restrictions (overlay permission),
 * handles tap-to-open notifications when blocked from background,
 * and uses typo-tolerant matching without ever falling back silently to a website.
 */
object SinbhaAppLauncher {

    const val TAP_NOTIFICATION_ID = 3003

    private val KNOWN_PACKAGES = mapOf(
        "whatsapp" to listOf("com.whatsapp"),
        "whatsap" to listOf("com.whatsapp"),
        "watsapp" to listOf("com.whatsapp"),
        "youtube" to listOf("com.google.android.youtube"),
        "youtub" to listOf("com.google.android.youtube"),
        "snapchat" to listOf("com.snapchat.android"),
        "snap" to listOf("com.snapchat.android"),
        "instagram" to listOf("com.instagram.android"),
        "insta" to listOf("com.instagram.android"),
        "telegram" to listOf("org.telegram.messenger"),
        "spotify" to listOf("com.spotify.music"),
        "spotfy" to listOf("com.spotify.music"),
        "chrome" to listOf("com.android.chrome"),
        "google chrome" to listOf("com.android.chrome"),
        "gmail" to listOf("com.google.android.gm"),
        "email" to listOf("com.google.android.gm"),
        "mail" to listOf("com.google.android.gm"),
        "maps" to listOf("com.google.android.apps.maps"),
        "google maps" to listOf("com.google.android.apps.maps"),
        "claude" to listOf("com.anthropic.claude"),
        "chatgpt" to listOf("com.openai.chatgpt"),
        "files" to listOf(
            "com.google.android.documentsui",
            "com.coloros.filemanager",
            "com.oppo.filemanager",
            "com.oneplus.filemanager",
            "com.android.documentsui"
        ),
        "file manager" to listOf(
            "com.google.android.documentsui",
            "com.coloros.filemanager",
            "com.oppo.filemanager",
            "com.oneplus.filemanager",
            "com.android.documentsui"
        ),
        "explorer" to listOf(
            "com.google.android.documentsui",
            "com.coloros.filemanager",
            "com.oppo.filemanager"
        ),
        "settings" to listOf("com.android.settings"),
        "calculator" to listOf("com.google.android.calculator", "com.coloros.calculator"),
        "calc" to listOf("com.google.android.calculator", "com.coloros.calculator"),
        "clock" to listOf("com.google.android.deskclock", "com.coloros.alarmclock")
    )

    fun getInstalledApps(context: Context): List<Map<String, String>> {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN, null).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val list = mutableListOf<Map<String, String>>()
        try {
            val resolveInfos: List<ResolveInfo> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                pm.queryIntentActivities(intent, PackageManager.ResolveInfoFlags.of(0))
            } else {
                @Suppress("DEPRECATION")
                pm.queryIntentActivities(intent, 0)
            }
            val seen = mutableSetOf<String>()
            for (ri in resolveInfos) {
                val pkg = ri.activityInfo.packageName
                if (!seen.add(pkg)) continue
                val label = ri.loadLabel(pm)?.toString()?.trim() ?: pkg
                list.add(mapOf("name" to label, "package" to pkg))
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return list
    }

    private fun levenshteinDistance(s1: String, s2: String): Int {
        val dp = Array(s1.length + 1) { IntArray(s2.length + 1) }
        for (i in 0..s1.length) dp[i][0] = i
        for (j in 0..s2.length) dp[0][j] = j
        for (i in 1..s1.length) {
            for (j in 1..s2.length) {
                val cost = if (s1[i - 1] == s2[j - 1]) 0 else 1
                dp[i][j] = minOf(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
            }
        }
        return dp[s1.length][s2.length]
    }

    fun launchFromPayload(context: Context, payload: JSONObject): LaunchResult {
        val app = payload.optString("app", "").trim()
        val query = payload.optString("search_query", null)?.takeIf { it.isNotBlank() }
        val url = payload.optString("url", null)?.takeIf { it.isNotBlank() }
        val text = payload.optString("type_text", null)?.takeIf { it.isNotBlank() }
        return launchAppWithResult(context, app, query, url, text)
    }

    fun launchApp(
        context: Context,
        appName: String,
        searchQuery: String? = null,
        url: String? = null,
        typeText: String? = null
    ): Boolean {
        return launchAppWithResult(context, appName, searchQuery, url, typeText).success
    }

    /**
     * Step C2.6 Item 5 & 6:
     * Launches app and returns detailed LaunchResult.
     * Uses overlay permission exemption or tap-to-open notification.
     * Uses typo-tolerant matching and never falls back silently to a website.
     */
    fun launchAppWithResult(
        context: Context,
        appName: String,
        searchQuery: String? = null,
        url: String? = null,
        typeText: String? = null
    ): LaunchResult {
        val cleanName = appName.lowercase().trim()
        val normalizedQuery = cleanName.replace(Regex("[^a-z0-9]"), "")
        val pm = context.packageManager

        // 1. Direct URL handling (explicit URL requested)
        if (!url.isNullOrBlank()) {
            val targetUrl = if (url.startsWith("http://") || url.startsWith("https://")) url else "https://$url"
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(targetUrl)).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                return launchIntentSafely(context, appName, null, intent, method = "direct_url")
            } catch (e: Exception) {
                return LaunchResult(false, appName, error = "Failed to open URL: ${e.message}")
            }
        }

        // 2. Search query handling with deep link support
        if (!searchQuery.isNullOrBlank()) {
            if (cleanName.contains("youtube")) {
                try {
                    val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                    val ytUri = Uri.parse("vnd.youtube://results?search_query=$encoded")
                    val ytIntent = Intent(Intent.ACTION_VIEW, ytUri).apply {
                        setPackage("com.google.android.youtube")
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    if (pm.resolveActivity(ytIntent, 0) != null) {
                        return launchIntentSafely(context, "youtube", "com.google.android.youtube", ytIntent, method = "deep_link_search")
                    }
                } catch (e: Exception) {}
            }

            try {
                val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                val searchUri = Uri.parse("https://www.google.com/search?q=$encoded")
                val searchIntent = Intent(Intent.ACTION_VIEW, searchUri).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                return launchIntentSafely(context, appName, null, searchIntent, method = "web_search")
            } catch (e: Exception) {
                return LaunchResult(false, appName, error = "Search launch failed: ${e.message}")
            }
        }

        // 3. Special System Intent Handlers
        when (cleanName) {
            "settings" -> {
                try {
                    val intent = Intent(Settings.ACTION_SETTINGS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    return launchIntentSafely(context, "settings", "com.android.settings", intent, method = "system_action")
                } catch (e: Exception) {
                    return LaunchResult(false, "settings", error = e.message)
                }
            }
            "camera" -> {
                try {
                    val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    return launchIntentSafely(context, "camera", null, intent, method = "system_action")
                } catch (e: Exception) {}
            }
            "clock", "alarm" -> {
                try {
                    val intent = Intent(AlarmClock.ACTION_SHOW_ALARMS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    return launchIntentSafely(context, "clock", null, intent, method = "system_action")
                } catch (e: Exception) {}
            }
        }

        // 4. Check known packages mapping (including OnePlus / Oppo file manager packages)
        val candidatePkgs = KNOWN_PACKAGES[cleanName]
            ?: if (cleanName.contains(".")) listOf(cleanName) else null

        if (candidatePkgs != null) {
            for (pkg in candidatePkgs) {
                val launchIntent = pm.getLaunchIntentForPackage(pkg)
                if (launchIntent != null) {
                    return launchIntentSafely(context, appName, pkg, launchIntent, method = "package_launcher")
                }
            }
        }

        // 5. Dynamic typo-tolerant resolution against installed launcher activities
        try {
            val launcherIntent = Intent(Intent.ACTION_MAIN, null).apply {
                addCategory(Intent.CATEGORY_LAUNCHER)
            }
            val resolveInfos: List<ResolveInfo> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                pm.queryIntentActivities(launcherIntent, PackageManager.ResolveInfoFlags.of(0))
            } else {
                @Suppress("DEPRECATION")
                pm.queryIntentActivities(launcherIntent, 0)
            }

            var bestMatch: ResolveInfo? = null
            var bestDistance = Int.MAX_VALUE

            for (ri in resolveInfos) {
                val rawLabel = ri.loadLabel(pm).toString()
                val label = rawLabel.lowercase().trim()
                val normLabel = label.replace(Regex("[^a-z0-9]"), "")
                val pkg = ri.activityInfo.packageName.lowercase()

                // Exact match
                if (label == cleanName || normLabel == normalizedQuery || pkg == cleanName) {
                    bestMatch = ri
                    bestDistance = 0
                    break
                }

                // Prefix / substring match
                if (normLabel.contains(normalizedQuery) || normalizedQuery.contains(normLabel)) {
                    if (bestDistance > 1) {
                        bestMatch = ri
                        bestDistance = 1
                    }
                }

                // Typo-tolerant Levenshtein distance
                val dist = levenshteinDistance(normalizedQuery, normLabel)
                val maxAllowable = when {
                    normalizedQuery.length >= 7 -> 2
                    normalizedQuery.length >= 4 -> 1
                    else -> 0
                }
                if (dist <= maxAllowable && dist < bestDistance) {
                    bestMatch = ri
                    bestDistance = dist
                }
            }

            if (bestMatch != null) {
                val pkg = bestMatch.activityInfo.packageName
                val launchIntent = pm.getLaunchIntentForPackage(pkg)
                if (launchIntent != null) {
                    return launchIntentSafely(context, appName, pkg, launchIntent, method = "query_launcher")
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // Step C2.6 Item 6: Never fall back silently to a website!
        return LaunchResult(
            success = false,
            app = appName,
            error = "App '$appName' is not installed on this Android device."
        )
    }

    /**
     * Step C2.6 Item 5:
     * Launches intent from background using overlay exemption.
     * If blocked or overlay permission is missing, shows tap-to-open notification
     * and reports 'needs a tap' honestly.
     */
    private fun launchIntentSafely(
        context: Context,
        appName: String,
        packageName: String?,
        launchIntent: Intent,
        method: String
    ): LaunchResult {
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)

        val canOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(context)
        } else {
            true
        }

        if (canOverlay) {
            try {
                context.startActivity(launchIntent)
                return LaunchResult(
                    success = true,
                    app = appName,
                    packageName = packageName,
                    method = "$method+overlay_exemption"
                )
            } catch (e: Exception) {
                // Background start was restricted by Android OS
            }
        }

        // If overlay is missing or direct start was blocked, show tap-to-open notification
        showTapToOpenNotification(context, appName, launchIntent)
        return LaunchResult(
            success = false,
            app = appName,
            packageName = packageName,
            method = method,
            needsTap = true,
            needsOverlayPermission = !canOverlay,
            error = "needs a tap: Android blocked background launch; notification posted to tap and open"
        )
    }

    private fun showTapToOpenNotification(context: Context, appName: String, launchIntent: Intent) {
        try {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val displayTitle = appName.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            val pi = PendingIntent.getActivity(
                context,
                (System.currentTimeMillis() % 10000).toInt(),
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notif = NotificationCompat.Builder(context, SinbhaPlugin.DEVICE_COMMANDS_CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("Open $displayTitle 📱")
                .setContentText("Tap to open $displayTitle on your phone")
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_CALL)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()

            nm.notify(TAP_NOTIFICATION_ID, notif)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
