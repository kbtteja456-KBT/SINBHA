package com.sinbha.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Build
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

data class ReminderItem(
    val taskId: Int,
    val taskTitle: String,
    val reminderId: String?,
    val reminderTime: String,
    val label: String,
    val isExplicit: Boolean
)

data class VersionInfo(
    val minVersionAndroid: String,
    val latestVersionAndroid: String,
    val downloadUrl: String,
    val message: String
)

class SinbhaApiClient(private val context: Context) {

    private val prefs = PreferencesManager(context)

    companion object {
        const val AUTH_NOTIFICATION_ID = 9998
    }

    private fun showAuthPausedNotification() {
        // Requirement 1: Appear only once per failure period; do not repeat on every poll
        if (prefs.isAuthPausedAlertShown) {
            return
        }
        prefs.isAuthPausedAlertShown = true

        try {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = NotificationChannel(
                    ReminderAlarmReceiver.REMINDER_CHANNEL_ID,
                    "SINBHA Task Reminders",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Task reminders and system alerts"
                    enableVibration(true)
                    enableLights(true)
                    lightColor = Color.parseColor("#EC4899")
                }
                manager.createNotificationChannel(channel)
            }

            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            }
            val pIntent = PendingIntent.getActivity(
                context,
                AUTH_NOTIFICATION_ID,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notif = NotificationCompat.Builder(context, ReminderAlarmReceiver.REMINDER_CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_sinbha)
                .setContentTitle("SINBHA Reminders")
                .setContentText("SINBHA reminders are paused, please open the app and log in again.")
                .setStyle(NotificationCompat.BigTextStyle().bigText("SINBHA reminders are paused, please open the app and log in again."))
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_ERROR)
                .setColor(Color.parseColor("#EC4899"))
                .setAutoCancel(true)
                .setContentIntent(pIntent)
                .build()

            manager.notify(AUTH_NOTIFICATION_ID, notif)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    suspend fun markTaskDone(taskId: Int): Boolean = withContext(Dispatchers.IO) {
        val token = prefs.sessionToken ?: return@withContext false
        try {
            val url = URL("${prefs.backendUrl}/api/tasks/$taskId")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "PATCH"
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                connectTimeout = 10000
                readTimeout = 10000
                doOutput = true
            }

            val body = JSONObject().put("status", "completed").toString()
            OutputStreamWriter(conn.outputStream).use { it.write(body) }

            val code = conn.responseCode
            if (code == 401) {
                showAuthPausedNotification()
            } else if (code in 200..299) {
                prefs.isAuthPausedAlertShown = false
            }
            conn.disconnect()
            code in 200..299
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun snoozeReminder(taskId: Int, minutes: Int = 15): Boolean = withContext(Dispatchers.IO) {
        val token = prefs.sessionToken ?: return@withContext false
        try {
            val url = URL("${prefs.backendUrl}/api/reminders/snooze")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                connectTimeout = 10000
                readTimeout = 10000
                doOutput = true
            }

            val body = JSONObject().apply {
                put("task_id", taskId)
                put("minutes", minutes)
            }.toString()

            OutputStreamWriter(conn.outputStream).use { it.write(body) }

            val code = conn.responseCode
            if (code == 401) {
                showAuthPausedNotification()
            } else if (code in 200..299) {
                prefs.isAuthPausedAlertShown = false
            }
            conn.disconnect()
            code in 200..299
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun fetchUpcomingReminders(): List<ReminderItem>? = withContext(Dispatchers.IO) {
        val token = prefs.sessionToken ?: return@withContext null
        val list = mutableListOf<ReminderItem>()
        try {
            val url = URL("${prefs.backendUrl}/api/reminders/upcoming")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                connectTimeout = 10000
                readTimeout = 10000
            }

            val code = conn.responseCode
            if (code == 401) {
                // Requirement 3: 401 on sync -> show high priority notification
                showAuthPausedNotification()
                conn.disconnect()
                return@withContext null
            }

            if (code in 200..299) {
                // Reset alert flag upon successful sync
                prefs.isAuthPausedAlertShown = false
                val responseText = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
                val root = JSONObject(responseText)

                // Update settings cache if returned
                if (root.has("settings")) {
                    val sObj = root.getJSONObject("settings")
                    prefs.isEmergencyStopped = root.optBoolean("emergency_stopped", false)
                    prefs.isQuietHoursEnabled = sObj.optString("quiet_hours_enabled", "true") == "true"
                    prefs.quietHoursStart = sObj.optString("quiet_hours_start", "22:00")
                    prefs.quietHoursEnd = sObj.optString("quiet_hours_end", "08:00")
                }

                val arr = root.optJSONArray("reminders") ?: JSONArray()
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    list.add(
                        ReminderItem(
                            taskId = obj.getInt("task_id"),
                            taskTitle = obj.optString("task_title", "Untitled Task"),
                            reminderId = obj.optString("reminder_id", null),
                            reminderTime = obj.getString("time"),
                            label = obj.optString("label", "Task Reminder"),
                            isExplicit = obj.optBoolean("is_explicit", true)
                        )
                    )
                }
                conn.disconnect()
                return@withContext list
            }
            conn.disconnect()
            return@withContext null
        } catch (e: Exception) {
            e.printStackTrace()
            return@withContext null
        }
    }

    suspend fun checkAppVersion(): VersionInfo? = withContext(Dispatchers.IO) {
        try {
            val url = URL("${prefs.backendUrl}/api/app/version-check")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 8000
                readTimeout = 8000
            }

            if (conn.responseCode in 200..299) {
                val responseText = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
                val obj = JSONObject(responseText)
                VersionInfo(
                    minVersionAndroid = obj.optString("min_version_android", "1.0.0"),
                    latestVersionAndroid = obj.optString("latest_version_android", "1.0.0"),
                    downloadUrl = obj.optString("download_url_android", "https://github.com/kbtteja456-KBT/sinbha-releases/releases/latest"),
                    message = obj.optString("message", "A newer version of SINBHA is available.")
                )
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }
}
