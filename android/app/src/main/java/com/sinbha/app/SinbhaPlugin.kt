package com.sinbha.app

import android.app.AlarmManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.NotificationManagerCompat
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

@CapacitorPlugin(name = "SinbhaNative")
class SinbhaPlugin : Plugin() {

    private lateinit var prefs: PreferencesManager

    override fun load() {
        super.load()
        prefs = PreferencesManager(context)
    }

    /**
     * Bridges user session token from WebView login into Android EncryptedSharedPreferences.
     */
    @PluginMethod
    fun syncSession(call: PluginCall) {
        val token = call.getString("token")
        if (token.isNullOrEmpty()) {
            call.reject("Token is required")
            return
        }

        prefs.sessionToken = token
        prefs.userEmail = call.getString("email")
        prefs.userId = call.getInt("userId", -1) ?: -1
        prefs.isEmergencyStopped = call.getBoolean("emergency_stopped", false) ?: false
        prefs.isAuthPausedAlertShown = false

        val qObj = call.getObject("quiet_hours")
        if (qObj != null) {
            prefs.isQuietHoursEnabled = qObj.optString("enabled", "true") == "true"
            prefs.quietHoursStart = qObj.optString("start", "22:00")
            prefs.quietHoursEnd = qObj.optString("end", "08:00")
        }

        // Trigger immediate alarm sync with new session token
        CoroutineScope(Dispatchers.IO).launch {
            try {
                AlarmScheduler.syncAndScheduleUpcoming(context)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        val res = JSObject().apply {
            put("success", true)
            put("message", "Session synchronized securely to encrypted keystore.")
        }
        call.resolve(res)
    }

    /**
     * Clears device session token and credentials from encrypted keystore on logout.
     */
    @PluginMethod
    fun clearSession(call: PluginCall) {
        prefs.clearSession()
        call.resolve(JSObject().put("success", true).put("message", "Session cleared from encrypted keystore."))
    }

    /**
     * Retrieves current device session token from encrypted keystore.
     */
    @PluginMethod
    fun getSessionToken(call: PluginCall) {
        val token = prefs.sessionToken
        val res = JSObject().apply {
            put("token", token)
            put("hasToken", !token.isNullOrEmpty())
        }
        call.resolve(res)
    }

    /**
     * Checks all Android runtime permissions and power management statuses.
     */
    @PluginMethod
    override fun checkPermissions(call: PluginCall) {
        val ctx = context
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val hasOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(ctx)
        } else {
            true
        }

        val hasNotifications = NotificationManagerCompat.from(ctx).areNotificationsEnabled()

        val hasExactAlarm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            am.canScheduleExactAlarms()
        } else {
            true
        }

        val isBatteryIgnored = pm.isIgnoringBatteryOptimizations(ctx.packageName)

        val manufacturer = Build.MANUFACTURER.lowercase()
        val isOnePlusOrOppo = manufacturer.contains("oneplus") ||
                manufacturer.contains("oppo") ||
                manufacturer.contains("realme")

        val res = JSObject().apply {
            put("overlay", hasOverlay)
            put("notifications", hasNotifications)
            put("exactAlarm", hasExactAlarm)
            put("batteryIgnored", isBatteryIgnored)
            put("manufacturer", Build.MANUFACTURER)
            put("brand", Build.BRAND)
            put("isOnePlusOrOppo", isOnePlusOrOppo)
            put("androidVersion", Build.VERSION.SDK_INT)
        }
        call.resolve(res)
    }

    /**
     * Opens target Android Settings page with specialized intents for OnePlus/ColorOS/Realme.
     */
    @PluginMethod
    fun requestPermission(call: PluginCall) {
        val type = call.getString("type") ?: ""
        val ctx = context
        val pkg = ctx.packageName

        try {
            when (type) {
                "overlay" -> {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        val intent = Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:$pkg")
                        ).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }
                        ctx.startActivity(intent)
                    }
                }
                "notifications" -> {
                    val intent = Intent().apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            action = Settings.ACTION_APP_NOTIFICATION_SETTINGS
                            putExtra(Settings.EXTRA_APP_PACKAGE, pkg)
                        } else {
                            action = "android.settings.APP_NOTIFICATION_SETTINGS"
                            putExtra("app_package", pkg)
                            putExtra("app_uid", ctx.applicationInfo.uid)
                        }
                    }
                    ctx.startActivity(intent)
                }
                "exactAlarm" -> {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                        val intent = Intent(
                            Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            Uri.parse("package:$pkg")
                        ).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }
                        ctx.startActivity(intent)
                    }
                }
                "battery" -> {
                    val intent = Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:$pkg")
                    ).apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }
                    ctx.startActivity(intent)
                }
                "autostart" -> {
                    openBrandAutostartSettings(ctx, pkg)
                }
                else -> {
                    // Open default App Info
                    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = Uri.parse("package:$pkg")
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    ctx.startActivity(intent)
                }
            }
            call.resolve(JSObject().put("success", true))
        } catch (e: Exception) {
            // Safe fallback to application details settings
            try {
                val fallback = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:$pkg")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                ctx.startActivity(fallback)
                call.resolve(JSObject().put("success", true).put("fallback", true))
            } catch (ex: Exception) {
                call.reject("Failed to open settings: ${ex.message}")
            }
        }
    }

    private fun openBrandAutostartSettings(ctx: Context, pkg: String) {
        // Specific intents for OnePlus (OxygenOS) / Oppo / Realme (ColorOS)
        val colorOsIntents = arrayOf(
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"),
            ComponentName("com.coloros.safecenter", "com.coloros.privacypermissionsentry.PermissionTopActivity"),
            ComponentName("com.oplus.battery", "com.oplus.battery.AppBatterySettings"),
            ComponentName("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity"),
            ComponentName("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity")
        )

        for (targetComp in colorOsIntents) {
            try {
                val intent = Intent().apply {
                    component = targetComp
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                ctx.startActivity(intent)
                return
            } catch (ignored: Exception) {}
        }

        // Standard App details fallback
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.parse("package:$pkg")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        ctx.startActivity(intent)
    }

    /**
     * Instantly triggers the bird overlay for immediate visual testing.
     */
    @PluginMethod
    fun testBird(call: PluginCall) {
        val title = call.getString("title") ?: "Drink water 💧"
        val dueText = call.getString("dueText") ?: "Due now 🌸"
        val taskId = call.getInt("taskId", 999) ?: 999

        OverlayBirdService.launch(context, taskId, title, dueText)
        call.resolve(JSObject().put("success", true))
    }

    /**
     * Triggers sync of upcoming reminders and schedules exact alarms.
     */
    @PluginMethod
    fun syncReminders(call: PluginCall) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                AlarmScheduler.syncAndScheduleUpcoming(context)
                call.resolve(JSObject().put("success", true))
            } catch (e: Exception) {
                call.reject("Sync failed: ${e.message}")
            }
        }
    }

    /**
     * Returns app version metadata.
     */
    @PluginMethod
    fun getAppVersion(call: PluginCall) {
        val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)
        val res = JSObject().apply {
            put("versionName", pInfo.versionName)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                put("versionCode", pInfo.longVersionCode)
            } else {
                put("versionCode", pInfo.versionCode)
            }
        }
        call.resolve(res)
    }

    /**
     * Requirement 6: Diagnostics screen data provider.
     * Collects permissions, scheduled alarms, device token status, last sync,
     * and error buffer without exposing tokens, passwords, or personal data.
     */
    @PluginMethod
    fun getDiagnostics(call: PluginCall) {
        val ctx = context
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val hasOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(ctx)
        } else {
            true
        }
        val hasNotifications = NotificationManagerCompat.from(ctx).areNotificationsEnabled()
        val hasExactAlarm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            am.canScheduleExactAlarms()
        } else {
            true
        }
        val isBatteryIgnored = pm.isIgnoringBatteryOptimizations(ctx.packageName)

        val pInfo = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        val vCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) pInfo.longVersionCode else pInfo.versionCode.toLong()

        val tokenExists = !prefs.sessionToken.isNullOrEmpty()
        val tokenStatusStr = if (tokenExists) {
            "Active (Stored in Android Keystore, 30-day rolling renewal)"
        } else {
            "Not registered / Logged out"
        }

        // Parse scheduled alarms from cache (stripping any sensitive user fields)
        val alarmsJs = JSArray()
        try {
            val cached = prefs.cachedRemindersJson
            if (!cached.isNullOrEmpty()) {
                val arr = org.json.JSONArray(cached)
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    alarmsJs.put(JSObject().apply {
                        put("taskId", obj.optInt("task_id", -1))
                        put("taskTitle", obj.optString("task_title", "Untitled Task"))
                        put("time", obj.optString("time", ""))
                        put("label", obj.optString("label", "Reminder"))
                    })
                }
            }
        } catch (e: Exception) {}

        // Parse recent errors
        val errorsJs = JSArray()
        try {
            val errArr = org.json.JSONArray(prefs.recentErrorsJson)
            for (i in 0 until errArr.length()) {
                val eObj = errArr.getJSONObject(i)
                errorsJs.put(JSObject().apply {
                    put("time", eObj.optString("time", ""))
                    put("message", eObj.optString("message", ""))
                })
            }
        } catch (e: Exception) {}

        val res = JSObject().apply {
            put("versionName", pInfo.versionName)
            put("versionCode", vCode)
            put("tokenStatus", tokenStatusStr)
            put("hasToken", tokenExists)
            put("lastSyncTime", prefs.lastSyncTime ?: "Never synced yet")
            put("permissions", JSObject().apply {
                put("overlay", hasOverlay)
                put("notifications", hasNotifications)
                put("exactAlarm", hasExactAlarm)
                put("batteryIgnored", isBatteryIgnored)
            })
            put("deviceInfo", JSObject().apply {
                put("manufacturer", Build.MANUFACTURER)
                put("brand", Build.BRAND)
                put("model", Build.MODEL)
                put("androidSdk", Build.VERSION.SDK_INT)
            })
            put("scheduledAlarms", alarmsJs)
            put("recentErrors", errorsJs)
        }

        call.resolve(res)
    }
}
