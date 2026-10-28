package com.sinbha.app

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object AlarmScheduler {

    const val EXTRA_TASK_ID = "extra_task_id"
    const val EXTRA_TASK_TITLE = "extra_task_title"
    const val EXTRA_DUE_TEXT = "extra_due_text"
    const val EXTRA_REMINDER_ID = "extra_reminder_id"
    const val EXTRA_SOUND_MODE = "extra_sound_mode"
    const val EXTRA_CUSTOM_SONG_URI = "extra_custom_song_uri"
    const val EXTRA_USER_NAME = "extra_user_name"
    const val EXTRA_SPEECH_TEXT = "extra_speech_text"

    fun scheduleExactAlarm(
        context: Context,
        taskId: Int,
        taskTitle: String,
        dueText: String,
        reminderId: String?,
        triggerAtMillis: Long,
        soundMode: String = "alarm_tone",
        customSongUri: String? = null,
        userName: String = "Friend",
        speechText: String? = null
    ) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val intent = Intent(context, ReminderAlarmReceiver::class.java).apply {
            putExtra(EXTRA_TASK_ID, taskId)
            putExtra(EXTRA_TASK_TITLE, taskTitle)
            putExtra(EXTRA_DUE_TEXT, dueText)
            putExtra(EXTRA_REMINDER_ID, reminderId)
            putExtra(EXTRA_SOUND_MODE, soundMode)
            putExtra(EXTRA_CUSTOM_SONG_URI, customSongUri)
            putExtra(EXTRA_USER_NAME, userName)
            putExtra(EXTRA_SPEECH_TEXT, speechText)
        }

        val requestCode = (taskId * 31 + (reminderId?.hashCode() ?: 0)).let { if (it < 0) -it else it }
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Show intent for system lock screen / clock widget
        val showIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("open_task_id", taskId)
        }
        val showPendingIntent = PendingIntent.getActivity(
            context,
            requestCode + 100000,
            showIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // The most reliable alarm scheduling method in Android: AlarmManager.setAlarmClock()
        // Highest priority wakeup, exempt from Doze, and displays in system clock/lockscreen
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                val clockInfo = AlarmManager.AlarmClockInfo(triggerAtMillis, showPendingIntent)
                alarmManager.setAlarmClock(clockInfo, pendingIntent)
                return
            }
        } catch (e: Exception) {
            // If exact alarm permission is missing or restricted on Android 12+, fall back to idle wakeup
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                triggerAtMillis,
                pendingIntent
            )
        } else {
            alarmManager.setExact(
                AlarmManager.RTC_WAKEUP,
                triggerAtMillis,
                pendingIntent
            )
        }
    }

    fun parseDateTimeToMillis(dateTimeStr: String): Long? {
        val patterns = arrayOf(
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd'T'HH:mm:ss'Z'"
        )
        for (p in patterns) {
            try {
                val sdf = SimpleDateFormat(p, Locale.getDefault())
                val date = sdf.parse(dateTimeStr)
                if (date != null) return date.time
            } catch (e: Exception) {}
        }
        return null
    }

    suspend fun syncAndScheduleUpcoming(context: Context) {
        val apiClient = SinbhaApiClient(context)
        val prefs = PreferencesManager(context)
        val reminders = apiClient.fetchUpcomingReminders()

        // Requirement 4: If sync fails (e.g. 401 or offline), do NOT clear cache!
        // Reminders already scheduled on the phone must still fire after token stops working.
        if (reminders == null) {
            return
        }

        val jsonArray = JSONArray()
        val now = System.currentTimeMillis()

        for (item in reminders) {
            val jsonItem = JSONObject().apply {
                put("task_id", item.taskId)
                put("task_title", item.taskTitle)
                put("reminder_id", item.reminderId)
                put("time", item.reminderTime)
                put("label", item.label)
                put("is_explicit", item.isExplicit)
                put("sound_mode", item.soundMode)
                put("custom_song_uri", item.customSongUri)
                put("user_name", item.userName)
                put("speech_text", item.speechText)
            }
            jsonArray.put(jsonItem)

            val triggerMillis = parseDateTimeToMillis(item.reminderTime)
            if (triggerMillis != null && triggerMillis > now) {
                scheduleExactAlarm(
                    context,
                    item.taskId,
                    item.taskTitle,
                    item.label,
                    item.reminderId,
                    triggerMillis,
                    item.soundMode,
                    item.customSongUri,
                    item.userName,
                    item.speechText
                )
            }
        }

        prefs.cachedRemindersJson = jsonArray.toString()
    }

    fun rescheduleFromCache(context: Context) {
        val prefs = PreferencesManager(context)
        val cached = prefs.cachedRemindersJson ?: return
        val now = System.currentTimeMillis()

        try {
            val arr = JSONArray(cached)
            for (i in 0 until arr.length()) {
                val item = arr.getJSONObject(i)
                val timeStr = item.getString("time")
                val triggerMillis = parseDateTimeToMillis(timeStr)
                if (triggerMillis != null && triggerMillis > now) {
                    scheduleExactAlarm(
                        context,
                        item.getInt("task_id"),
                        item.optString("task_title", "Reminder"),
                        item.optString("label", "Due now 🌸"),
                        item.optString("reminder_id", null),
                        triggerMillis,
                        item.optString("sound_mode", prefs.reminderSoundMode),
                        item.optString("custom_song_uri", prefs.customSongUri),
                        item.optString("user_name", prefs.userDisplayName ?: "Friend"),
                        item.optString("speech_text", null)
                    )
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun addOrUpdateCachedReminder(
        context: Context,
        taskId: Int,
        taskTitle: String,
        label: String,
        reminderId: String?,
        triggerAtMillis: Long,
        soundMode: String? = null,
        customSongUri: String? = null,
        userName: String? = null,
        speechText: String? = null
    ) {
        val prefs = PreferencesManager(context)
        val cached = prefs.cachedRemindersJson
        val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        val formattedTime = sdf.format(Date(triggerAtMillis))

        val resolvedSoundMode = soundMode ?: prefs.reminderSoundMode
        val resolvedSongUri = customSongUri ?: prefs.customSongUri
        val resolvedUserName = userName ?: (prefs.userDisplayName ?: "Friend")

        val newArray = JSONArray()
        var updated = false

        if (!cached.isNullOrEmpty()) {
            try {
                val oldArr = JSONArray(cached)
                for (i in 0 until oldArr.length()) {
                    val item = oldArr.getJSONObject(i)
                    val tId = item.optInt("task_id", -1)
                    val rId = item.optString("reminder_id", "")
                    if (tId == taskId && (reminderId == null || rId == reminderId || rId.startsWith("snooze_"))) {
                        val updatedItem = JSONObject().apply {
                            put("task_id", taskId)
                            put("task_title", taskTitle)
                            put("reminder_id", reminderId ?: "snooze_$taskId")
                            put("time", formattedTime)
                            put("label", label)
                            put("is_explicit", true)
                            put("sound_mode", resolvedSoundMode)
                            put("custom_song_uri", resolvedSongUri)
                            put("user_name", resolvedUserName)
                            put("speech_text", speechText ?: item.optString("speech_text", null))
                        }
                        newArray.put(updatedItem)
                        updated = true
                    } else {
                        newArray.put(item)
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        if (!updated) {
            val newItem = JSONObject().apply {
                put("task_id", taskId)
                put("task_title", taskTitle)
                put("reminder_id", reminderId ?: "snooze_$taskId")
                put("time", formattedTime)
                put("label", label)
                put("is_explicit", true)
                put("sound_mode", resolvedSoundMode)
                put("custom_song_uri", resolvedSongUri)
                put("user_name", resolvedUserName)
                put("speech_text", speechText)
            }
            newArray.put(newItem)
        }

        prefs.cachedRemindersJson = newArray.toString()
    }
}
