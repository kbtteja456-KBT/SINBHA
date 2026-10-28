package com.sinbha.app

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.pm.PackageInfoCompat
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

    companion object {
        const val DEVICE_COMMANDS_CHANNEL_ID = "sinbha_device_commands_channel"
        const val RING_NOTIFICATION_ID = 8888
        private var activeRingPlayer: MediaPlayer? = null

        fun stopCurrentAlarmRing(context: Context) {
            try {
                activeRingPlayer?.stop()
                activeRingPlayer?.release()
                activeRingPlayer = null
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                nm.cancel(RING_NOTIFICATION_ID)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        fun startAlarmRing(ctx: Context, sender: String = "Paired Companion"): Boolean {
            stopCurrentAlarmRing(ctx)
            return try {
                val alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                    ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)

                val player = MediaPlayer().apply {
                    setDataSource(ctx, alarmUri)
                    setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build()
                    )
                    isLooping = true
                    prepare()
                    start()
                }
                activeRingPlayer = player

                val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    val channel = NotificationChannel(
                        DEVICE_COMMANDS_CHANNEL_ID,
                        "SINBHA Device Commands",
                        NotificationManager.IMPORTANCE_HIGH
                    ).apply {
                        description = "Notifications from paired companion devices"
                    }
                    nm.createNotificationChannel(channel)
                }

                val stopIntent = Intent(ctx, ReminderActionReceiver::class.java).apply {
                    action = ReminderActionReceiver.ACTION_STOP_RING
                }
                val stopPi = PendingIntent.getBroadcast(
                    ctx,
                    8888,
                    stopIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )

                val openIntent = Intent(ctx, MainActivity::class.java)
                val openPi = PendingIntent.getActivity(
                    ctx,
                    8889,
                    openIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )

                val notif = NotificationCompat.Builder(ctx, DEVICE_COMMANDS_CHANNEL_ID)
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle("🔔 Ringing this Device")
                    .setContentText("Triggered by $sender")
                    .setOngoing(true)
                    .setPriority(NotificationCompat.PRIORITY_MAX)
                    .setContentIntent(openPi)
                    .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop Ringing", stopPi)
                    .build()

                nm.notify(RING_NOTIFICATION_ID, notif)
                true
            } catch (e: Exception) {
                e.printStackTrace()
                false
            }
        }
    }

    private lateinit var prefs: PreferencesManager

    override fun load() {
        super.load()
        prefs = PreferencesManager(context)
        try {
            SinbhaCompanionService.start(context)
        } catch (e: Exception) {}
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

        val devId = call.getString("deviceId")
        if (!devId.isNullOrEmpty()) {
            prefs.deviceId = devId
        }

        val qObj = call.getObject("quiet_hours")
        if (qObj != null) {
            prefs.isQuietHoursEnabled = qObj.optString("enabled", "true") == "true"
            prefs.quietHoursStart = qObj.optString("start", "22:00")
            prefs.quietHoursEnd = qObj.optString("end", "08:00")
        }

        // Start persistent companion service
        try {
            SinbhaCompanionService.start(context)
        } catch (e: Exception) {}

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
        val dueText = call.getString("dueText") ?: "Due now 🐘"
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
     * Schedules a local exact alarm and updates cache for snoozed reminders (offline + reboot survival).
     */
    @PluginMethod
    fun snoozeLocalAlarm(call: PluginCall) {
        val taskId = call.getInt("taskId", -1) ?: -1
        val taskTitle = call.getString("taskTitle") ?: "Reminder"
        val minutes = call.getInt("minutes", 2) ?: 2
        if (taskId <= 0) {
            call.reject("Invalid taskId")
            return
        }

        val triggerAtMillis = System.currentTimeMillis() + minutes * 60 * 1000L
        val snoozeRemId = "snooze_$taskId"
        val dueLabel = "Snoozed (${minutes}m)"

        AlarmScheduler.scheduleExactAlarm(
            context,
            taskId,
            taskTitle,
            dueLabel,
            snoozeRemId,
            triggerAtMillis
        )
        AlarmScheduler.addOrUpdateCachedReminder(
            context,
            taskId,
            taskTitle,
            dueLabel,
            snoozeRemId,
            triggerAtMillis
        )

        call.resolve(JSObject().apply {
            put("success", true)
            put("triggerAtMillis", triggerAtMillis)
        })
    }

    /**
     * Step 16b: Shows a native heads-up notification for an incoming remote note.
     */
    @PluginMethod
    fun showNoteNotification(call: PluginCall) {
        val title = call.getString("title") ?: "Note from Paired Device"
        val text = call.getString("text") ?: ""
        val ctx = context
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                DEVICE_COMMANDS_CHANNEL_ID,
                "SINBHA Device Commands",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications from paired companion devices"
            }
            nm.createNotificationChannel(channel)
        }

        val intent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(
            ctx,
            (System.currentTimeMillis() % 10000).toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(ctx, DEVICE_COMMANDS_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        nm.notify((System.currentTimeMillis() % 10000).toInt() + 1000, notif)
        call.resolve(JSObject().put("success", true))
    }

    /**
     * Step 16b: Rings device using Alarm stream with Stop action button.
     */
    @PluginMethod
    fun startAlarmRing(call: PluginCall) {
        val sender = call.getString("sender") ?: "Paired Companion"
        val ok = startAlarmRing(context, sender)
        if (ok) {
            call.resolve(JSObject().put("success", true))
        } else {
            call.reject("Failed to play alarm ring")
        }
    }

    /**
     * Step 16b: Stops alarm ring audio.
     */
    @PluginMethod
    fun stopAlarmRing(call: PluginCall) {
        stopCurrentAlarmRing(context)
        call.resolve(JSObject().put("success", true))
    }

    /**
     * Returns app version metadata.
     */
    @PluginMethod
    fun getAppVersion(call: PluginCall) {
        val pInfo = context.packageManager.getPackageInfo(context.packageName, 0)
        val vCode = PackageInfoCompat.getLongVersionCode(pInfo)
        val res = JSObject().apply {
            put("versionName", pInfo.versionName)
            put("versionCode", vCode)
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
        val vCode = PackageInfoCompat.getLongVersionCode(pInfo)

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

    /**
     * Step 16c: Launches native apps on Android by app name, package, search query, or URL.
     */
    @PluginMethod
    fun openApp(call: PluginCall) {
        val appName = call.getString("app", "")?.trim() ?: ""
        val searchQuery = call.getString("search_query", null) ?: call.getString("query", null)
        val url = call.getString("url", null)
        val text = call.getString("type_text", null) ?: call.getString("text", null)

        val success = SinbhaAppLauncher.launchApp(context, appName, searchQuery, url, text)
        if (success) {
            call.resolve(JSObject().put("success", true).put("app", appName))
        } else {
            call.reject("Could not find or launch matching app for '$appName'")
        }
    }

    /**
     * Step 16c: Returns phone battery level and charging state.
     */
    @PluginMethod
    fun getBatteryStatus(call: PluginCall) {
        try {
            val ifilter = android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED)
            val bStatus = context.registerReceiver(null, ifilter)
            val level = bStatus?.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = bStatus?.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1) ?: -1
            val batteryPct = if (level >= 0 && scale > 0) (level * 100 / scale) else -1
            val status = bStatus?.getIntExtra(android.os.BatteryManager.EXTRA_STATUS, -1) ?: -1
            val isCharging = status == android.os.BatteryManager.BATTERY_STATUS_CHARGING ||
                             status == android.os.BatteryManager.BATTERY_STATUS_FULL

            val res = JSObject().apply {
                put("percentage", batteryPct)
                put("isCharging", isCharging)
            }
            call.resolve(res)
        } catch (e: Exception) {
            call.reject("Failed to get battery status: ${e.message}")
        }
    }

    /**
     * Step 16c: Returns recent notifications collected by SinbhaNotificationListener.
     */
    @PluginMethod
    fun getRecentNotifications(call: PluginCall) {
        try {
            val items = SinbhaNotificationListener.getRecent()
            val arr = JSArray()
            for (item in items) {
                arr.put(JSObject().apply {
                    put("app", item.app)
                    put("title", item.title)
                    put("text", item.text)
                    put("timestamp", item.timestamp)
                })
            }
            call.resolve(JSObject().put("notifications", arr))
        } catch (e: Exception) {
            call.reject("Failed to get notifications: ${e.message}")
        }
    }

    /**
     * Step 16c: Opens Android Notification Listener settings if permission needed.
     */
    @PluginMethod
    fun requestNotificationAccess(call: PluginCall) {
        try {
            val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)
            call.resolve(JSObject().put("success", true))
        } catch (e: Exception) {
            call.reject("Failed to open notification settings: ${e.message}")
        }
    }

    private var previewPlayer: MediaPlayer? = null
    private var previewTts: android.speech.tts.TextToSpeech? = null

    /**
     * Step 17: Checks whether USE_FULL_SCREEN_INTENT is allowed on Android 14+ (API 34+).
     */
    @PluginMethod
    fun checkFullScreenIntentPermission(call: PluginCall) {
        val granted = if (Build.VERSION.SDK_INT >= 34) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.canUseFullScreenIntent()
        } else {
            true
        }
        val res = JSObject().apply {
            put("granted", granted)
            put("sdkInt", Build.VERSION.SDK_INT)
        }
        call.resolve(res)
    }

    /**
     * Step 17: Opens system Settings to grant USE_FULL_SCREEN_INTENT permission.
     */
    @PluginMethod
    fun requestFullScreenIntentPermission(call: PluginCall) {
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                val intent = Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT).apply {
                    data = Uri.parse("package:${context.packageName}")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
            } else {
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:${context.packageName}")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context.startActivity(intent)
            }
            call.resolve(JSObject().put("success", true))
        } catch (e: Exception) {
            call.reject("Failed to open permission settings: ${e.message}")
        }
    }

    /**
     * Step 17: Previews the chosen alarm sound (tone, song, voice, voice then tone).
     */
    @PluginMethod
    fun previewAlarmSound(call: PluginCall) {
        stopAlarmPreviewInternal()
        val option = call.getString("soundOption") ?: "voice_then_tone"
        val songUriStr = call.getString("songUri") ?: ""
        val spokenText = call.getString("spokenText") ?: "Hey, it is time for your task."

        try {
            when (option) {
                "alarm_tone" -> {
                    playAlarmTonePreview()
                    call.resolve(JSObject().put("playing", true))
                }
                "song" -> {
                    if (songUriStr.isNotEmpty()) {
                        try {
                            val uri = Uri.parse(songUriStr)
                            previewPlayer = MediaPlayer().apply {
                                setDataSource(context.applicationContext, uri)
                                setAudioAttributes(
                                    AudioAttributes.Builder()
                                        .setUsage(AudioAttributes.USAGE_ALARM)
                                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                                        .build()
                                )
                                prepare()
                                start()
                            }
                            call.resolve(JSObject().put("playing", true))
                            return
                        } catch (e: Exception) {}
                    }
                    playAlarmTonePreview()
                    call.resolve(JSObject().put("playing", true).put("fallback", true))
                }
                "spoken_voice" -> {
                    speakPreview(spokenText, onDone = {})
                    call.resolve(JSObject().put("playing", true))
                }
                "voice_then_tone" -> {
                    speakPreview(spokenText, onDone = {
                        playAlarmTonePreview()
                    })
                    call.resolve(JSObject().put("playing", true))
                }
                else -> {
                    playAlarmTonePreview()
                    call.resolve(JSObject().put("playing", true))
                }
            }
        } catch (e: Exception) {
            call.reject("Preview failed: ${e.message}")
        }
    }

    /**
     * Step 17: Stops the alarm sound preview.
     */
    @PluginMethod
    fun stopAlarmPreview(call: PluginCall) {
        stopAlarmPreviewInternal()
        call.resolve(JSObject().put("stopped", true))
    }

    private fun stopAlarmPreviewInternal() {
        try {
            previewPlayer?.stop()
            previewPlayer?.release()
            previewPlayer = null
        } catch (e: Exception) {}
        try {
            previewTts?.stop()
            previewTts?.shutdown()
            previewTts = null
        } catch (e: Exception) {}
    }

    private fun playAlarmTonePreview() {
        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        previewPlayer = MediaPlayer().apply {
            setDataSource(context.applicationContext, soundUri)
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            isLooping = false
            prepare()
            start()
        }
    }

    private fun speakPreview(text: String, onDone: () -> Unit) {
        previewTts = android.speech.tts.TextToSpeech(context) { status ->
            if (status == android.speech.tts.TextToSpeech.SUCCESS) {
                previewTts?.language = java.util.Locale.getDefault()
                val params = android.os.Bundle().apply {
                    putInt(android.speech.tts.TextToSpeech.Engine.KEY_PARAM_STREAM, android.media.AudioManager.STREAM_ALARM)
                }
                previewTts?.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) {
                        onDone()
                    }
                    override fun onError(utteranceId: String?) {
                        onDone()
                    }
                })
                previewTts?.speak(text, android.speech.tts.TextToSpeech.QUEUE_FLUSH, params, "preview_alarm")
            } else {
                onDone()
            }
        }
    }
}