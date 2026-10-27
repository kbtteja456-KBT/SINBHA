package com.sinbha.app

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.AlarmClock
import android.provider.MediaStore
import android.provider.Settings
import org.json.JSONObject
import java.net.URLEncoder

/**
 * Universal native application launcher for Android.
 * Supports direct package launching, dynamic installed app search,
 * parameterized web searches, URLs, and graceful fallbacks.
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
        return launchApp(context, app, query, url, text)
    }

    fun launchApp(
        context: Context,
        appName: String,
        searchQuery: String? = null,
        url: String? = null,
        typeText: String? = null
    ): Boolean {
        val cleanName = appName.lowercase().trim()
        val pm = context.packageManager

        // 1. Direct URL handling
        if (!url.isNullOrBlank()) {
            val targetUrl = if (url.startsWith("http://") || url.startsWith("https://")) url else "https://$url"
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(targetUrl)).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
                return true
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 2. Search query handling (e.g. "open chrome and search whatsapp", "open youtube and search music")
        if (!searchQuery.isNullOrBlank()) {
            if (cleanName.contains("youtube")) {
                try {
                    val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                    val ytUri = Uri.parse("https://www.youtube.com/results?search_query=$encoded")
                    val ytIntent = Intent(Intent.ACTION_VIEW, ytUri).apply {
                        setPackage("com.google.android.youtube")
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(ytIntent)
                    return true
                } catch (e: Exception) {
                    // Fall back to general browser search
                }
            }

            try {
                val encoded = URLEncoder.encode(searchQuery, "UTF-8")
                val searchUri = Uri.parse("https://www.google.com/search?q=$encoded")
                val searchIntent = Intent(Intent.ACTION_VIEW, searchUri).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(searchIntent)
                return true
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 3. Special Android System Actions
        when (cleanName) {
            "camera" -> {
                try {
                    val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return true
                } catch (e: Exception) {}
            }
            "settings" -> {
                try {
                    val intent = Intent(Settings.ACTION_SETTINGS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return true
                } catch (e: Exception) {}
            }
            "clock", "alarm" -> {
                try {
                    val intent = Intent(AlarmClock.ACTION_SHOW_ALARMS).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return true
                } catch (e: Exception) {}
            }
            "files", "explorer", "file manager" -> {
                try {
                    val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "*/*"
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    context.startActivity(intent)
                    return true
                } catch (e: Exception) {}
            }
        }

        // 4. Hardcoded Known Packages
        val targetPkg = KNOWN_PACKAGES[cleanName] ?: if (cleanName.contains(".")) cleanName else null
        if (targetPkg != null) {
            val launchIntent = pm.getLaunchIntentForPackage(targetPkg)
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(launchIntent)
                return true
            }
        }

        // 5. Dynamic search across all installed apps on device
        try {
            val installedApps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            for (appInfo in installedApps) {
                val isSystem = (appInfo.flags and ApplicationInfo.FLAG_SYSTEM) != 0
                val label = pm.getApplicationLabel(appInfo).toString().lowercase()
                val pkg = appInfo.packageName.lowercase()

                if (label == cleanName || label.contains(cleanName) || pkg.contains(cleanName)) {
                    val intent = pm.getLaunchIntentForPackage(appInfo.packageName)
                    if (intent != null) {
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(intent)
                        return true
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // 6. Web / Store fallback
        val fallbackUrl = WEB_FALLBACKS[cleanName]
        if (fallbackUrl != null) {
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(fallbackUrl)).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
                return true
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        // 7. Play Store search fallback
        if (targetPkg != null) {
            try {
                val storeIntent = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$targetPkg")).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(storeIntent)
                return true
            } catch (e: Exception) {}
        }

        return false
    }
}
