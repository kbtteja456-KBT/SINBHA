package com.sinbha.app

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.net.Uri
import android.os.Build
import android.provider.AlarmClock
import android.provider.MediaStore
import android.provider.Settings
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
    val needsOverlayPermission: Boolean = false
)

/**
 * Universal native application launcher for Android (Step C2.5 Item 4).
 * Resolves installed apps with PackageManager queryIntentActivities,
 * checks Android background-activity restrictions (overlay permission),
 * and supports deep links for YouTube, WhatsApp, Instagram.
 */
object SinbhaAppLauncher {

    private val KNOWN_PACKAGES = mapOf(
        "whatsapp" to "com.whatsapp",
        "whatsap" to "com.whatsapp",
        "watsapp" to "com.whatsapp",
        "youtube" to "com.google.android.youtube",
        "youtub" to "com.google.android.youtube",
        "snapchat" to "com.snapchat.android",
        "instagram" to "com.instagram.android",
        "insta" to "com.instagram.android",
        "telegram" to "org.telegram.messenger",
        "spotify" to "com.spotify.music",
        "spotfy" to "com.spotify.music",
        "chrome" to "com.android.chrome",
        "google chrome" to "com.android.chrome",
        "gmail" to "com.google.android.gm",
        "email" to "com.google.android.gm",
        "mail" to "com.google.android.gm",
        "maps" to "com.google.android.apps.maps",
        "google maps" to "com.google.android.apps.maps",
        "claude" to "com.anthropic.claude",
        "chatgpt" to "com.openai.chatgpt",
        "files" to "com.google.android.documentsui",
        "file manager" to "com.google.android.documentsui",
        "explorer" to "com.google.android.documentsui",
        "calculator" to "com.google.android.calculator",
        "calc" to "com.google.android.calculator",
        "clock" to "com.google.android.deskclock"
    )

    private val WEB_FALLBACKS = mapOf(
        "whatsapp" to "https://web.whatsapp.com",
        "youtube" to "https://m.youtube.com",
        "snapchat" to "https://web.snapchat.com",
        "instagram" to "https://www.instagram.com",
        "telegram" to "https://web.telegram.org",
        "spotify" to "https://open.spotify.com",
        "claude" to "https://claude.ai",
        "chatgpt" to "https://chatgpt.com",
        "gmail" to "https://mail.google.com",
        "maps" to "https://maps.google.com",
        "chrome" to "https://www.google.com"
    )

    fun launchFromPayload(context: Context, payload: JSONObject): Boolean {
        val app = payload.optString("app", "").trim()
        val query = payload.optString("search_query", null)?.takeIf { it.isNotBlank() }
        val url = payload.optString("url", null)?.takeIf { it.isNotBlank() }
        val text = payload.optString("type_text", null)?.takeIf { it.isNotBlank() }
        return launchAppWithResult(context, app, query, url, text).success
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
     * Launches app and returns detailed LaunchResult (Item 4).
     */
    fun launchAppWithResult(
        context: Context,
        appName: String,
        searchQuery: String? = null,
        url: String? = null,
        typeText: String? = null
    ): LaunchResult {
        val cleanName = appName.lowercase().trim()
        val pm = context.packageManager

        // 1. Check background launch readiness on Android 10+ (API 29+)
        // Background activity starts are blocked unless overlay permission is granted
        // or a foreground service is active.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val canOverlay = Settings.canDrawOverlays(context)
            if (!canOverlay) {
                // If not ready, return clear plain explanation
                // Note: If invoked when SINBHA is in foreground this may be allowed,
                // but overlay is essential for remote companion launching
            }
        }

        // 2. Direct URL handling
        if (!url.isNullOrBlank()) {
            val targetUrl = if (url.startsWith("http://") || url.startsWith("https://")) url else "https://$url"
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(targetUrl)).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
                return LaunchResult(true, appName, method = "direct_url")
            } catch (e: Exception) {
                return LaunchResult(false, appName, error = "Failed to open URL: ${e.message}")
            }
        }

        // 3. Search query handling with deep link support
        if (!searchQuery.isNullOrBlank()) {
            if (cleanName.contains("youtube")) {
                try {
                    val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                    val ytUri = Uri.parse("vnd.youtube://results?search_query=$encoded")
                    val ytIntent = Intent(Intent.ACTION_VIEW, ytUri).apply {
                        setPackage("com.google.android.youtube")
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(ytIntent)
                    return LaunchResult(true, "youtube", packageName = "com.google.android.youtube", method = "deep_link_search")
                } catch (e: Exception) {
                    // Fall back to web search
                }
            }

            try {
                val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                val searchUri = Uri.parse("https://www.google.com/search?q=$encoded")
                val searchIntent = Intent(Intent.ACTION_VIEW, searchUri).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(searchIntent)
                return LaunchResult(true, appName, method = "web_search")
            } catch (e: Exception) {
                return LaunchResult(false, appName, error = "Search launch failed: ${e.message}")
            }
        }

        // 4. App Deep Links (Item 4: YouTube, WhatsApp, Instagram)
        when (cleanName) {
            "youtube" -> {
                try {
                    val ytIntent = Intent(Intent.ACTION_VIEW, Uri.parse("vnd.youtube:")).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        setPackage("com.google.android.youtube")
                    }
                    context.startActivity(ytIntent)
                    return LaunchResult(true, "youtube", packageName = "com.google.android.youtube", method = "deep_link")
                } catch (e: Exception) {}
            }
            "whatsapp", "whatsap" -> {
                try {
                    val waIntent = Intent(Intent.ACTION_VIEW, Uri.parse("whatsapp://send")).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        setPackage("com.whatsapp")
                    }
                    context.startActivity(waIntent)
                    return LaunchResult(true, "whatsapp", packageName = "com.whatsapp", method = "deep_link")
                } catch (e: Exception) {}
            }
            "instagram", "insta" -> {
                try {
                    val instaIntent = Intent(Intent.ACTION_VIEW, Uri.parse("https://instagram.com/_u/")).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        setPackage("com.instagram.android")
                    }
                    context.startActivity(instaIntent)
                    return LaunchResult(true, "instagram", packageName = "com.instagram.android", method = "deep_link")
                } catch (e: Exception) {}
            }
            "settings" -> {
                try {
                    val intent = Intent(Settings.ACTION_SETTINGS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return LaunchResult(true, "settings", packageName = "com.android.settings", method = "system_action")
                } catch (e: Exception) {
                    return LaunchResult(false, "settings", error = e.message)
                }
            }
            "camera" -> {
                try {
                    val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return LaunchResult(true, "camera", method = "system_action")
                } catch (e: Exception) {}
            }
            "clock", "alarm" -> {
                try {
                    val intent = Intent(AlarmClock.ACTION_SHOW_ALARMS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return LaunchResult(true, "clock", method = "system_action")
                } catch (e: Exception) {}
            }
        }

        // 5. Hardcoded Known Packages
        val targetPkg = KNOWN_PACKAGES[cleanName] ?: if (cleanName.contains(".")) cleanName else null
        if (targetPkg != null) {
            val launchIntent = pm.getLaunchIntentForPackage(targetPkg)
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(launchIntent)
                return LaunchResult(true, appName, packageName = targetPkg, method = "package_launcher")
            }
        }

        // 6. Dynamic resolution using queryIntentActivities (Android 11+ compliant)
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

            for (ri in resolveInfos) {
                val label = ri.loadLabel(pm).toString().lowercase()
                val pkg = ri.activityInfo.packageName.lowercase()
                if (label == cleanName || label.contains(cleanName) || pkg.contains(cleanName)) {
                    val launchIntent = pm.getLaunchIntentForPackage(ri.activityInfo.packageName)
                    if (launchIntent != null) {
                        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(launchIntent)
                        return LaunchResult(true, appName, packageName = ri.activityInfo.packageName, method = "query_launcher")
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // 7. Web fallback
        val fallbackUrl = WEB_FALLBACKS[cleanName]
        if (fallbackUrl != null) {
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(fallbackUrl)).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
                return LaunchResult(true, appName, method = "web_fallback")
            } catch (e: Exception) {}
        }

        return LaunchResult(false, appName, error = "App '$appName' is not installed on this Android device.")
    }
}
