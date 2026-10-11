package com.sinbha.app

import android.content.Context
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
            conn.disconnect()
            code in 200..299
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun fetchUpcomingReminders(): List<ReminderItem> = withContext(Dispatchers.IO) {
        val token = prefs.sessionToken ?: return@withContext emptyList()
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

            if (conn.responseCode in 200..299) {
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
            }
            conn.disconnect()
        } catch (e: Exception) {
            e.printStackTrace()
        }
        list
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
                    downloadUrl = obj.optString("download_url_android", "https://github.com/kbtteja456-KBT/SINBHA/releases/latest"),
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
