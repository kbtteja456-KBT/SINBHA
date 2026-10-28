package com.sinbha.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

/**
 * Persistent Foreground Service that keeps Android Companion connected to the SINBHA
 * device mesh even when swiped away from recent apps or screen is locked.
 * Periodically polls for remote commands and syncs native alarms.
 */
class SinbhaCompanionService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PreferencesManager
    private lateinit var apiClient: SinbhaApiClient

    companion object {
        const val PERSISTENT_CHANNEL_ID = "sinbha_companion_persistent_channel"
        const val PERSISTENT_NOTIF_ID = 2002

        fun start(context: Context) {
            val intent = Intent(context, SinbhaCompanionService::class.java)
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = PreferencesManager(this)
        apiClient = SinbhaApiClient(this)

        createNotificationChannel()
        startForeground(PERSISTENT_NOTIF_ID, buildForegroundNotification())

        startPollingLoop()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        serviceScope.cancel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                PERSISTENT_CHANNEL_ID,
                "SINBHA Companion Sync",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps device commands & reminders synced across your phone and laptop"
                setShowBadge(false)
            }
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildForegroundNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pi = PendingIntent.getActivity(
            this,
            PERSISTENT_NOTIF_ID,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, PERSISTENT_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("SINBHA Companion Connected 🐘")
            .setContentText("Listening for phone & laptop commands in background")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setOngoing(true)
            .setContentIntent(pi)
            .build()
    }

    private fun startPollingLoop() {
        serviceScope.launch {
            var lastAlarmSyncTime = 0L

            while (isActive) {
                try {
                    val token = prefs.sessionToken
                    if (!token.isNullOrEmpty()) {
                        // 1. Ensure persistent deviceId
                        var deviceId = prefs.deviceId
                        if (deviceId.isNullOrEmpty()) {
                            val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
                            deviceId = "android_" + (androidId ?: UUID.randomUUID().toString().substring(0, 8))
                            prefs.deviceId = deviceId
                        }

                        // 2. Poll for pending remote commands
                        val commands = apiClient.fetchPendingCommands(deviceId)
                        for (cmd in commands) {
                            handleRemoteCommand(cmd)
                        }

                        // 3. Periodically sync alarms (every 60s)
                        val now = System.currentTimeMillis()
                        if (now - lastAlarmSyncTime > 60_000L) {
                            lastAlarmSyncTime = now
                            try {
                                AlarmScheduler.syncAndScheduleUpcoming(applicationContext)
                            } catch (e: Exception) {}
                        }
                    }
                } catch (e: Exception) {
                    // Suppress network jitter in loop
                }

                delay(3000L)
            }
        }
    }

    private fun handleRemoteCommand(cmd: JSONObject) {
        try {
            val type = cmd.optString("type")
            val payload = cmd.optJSONObject("payload") ?: JSONObject()
            val sender = cmd.optString("sender_name", "Paired Companion")

            when (type) {
                "open_app" -> {
                    SinbhaAppLauncher.launchFromPayload(applicationContext, payload)
                }
                "ring_phone" -> {
                    SinbhaPlugin.startAlarmRing(applicationContext, sender)
                }
                "send_note" -> {
                    showNoteHeadsUp(
                        payload.optString("title", "Note from Paired Device"),
                        payload.optString("text", "")
                    )
                }
                "emergency_stop" -> {
                    prefs.isEmergencyStopped = true
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun showNoteHeadsUp(title: String, text: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pi = PendingIntent.getActivity(
            this,
            (System.currentTimeMillis() % 10000).toInt(),
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(this, SinbhaPlugin.DEVICE_COMMANDS_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        nm.notify((System.currentTimeMillis() % 10000).toInt() + 1000, notif)
    }
}
