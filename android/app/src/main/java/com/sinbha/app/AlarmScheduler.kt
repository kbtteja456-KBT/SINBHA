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
    const val EXTRA_SOUND_OPTION = "extra_sound_option"
    const val EXTRA_SONG_URI = "extra_song_uri"
    const val EXTRA_USER_NAME = "extra_user_name"
    const val EXTRA_SPOKEN_TEXT = "extra_spoken_text"

    fun scheduleExactAlarm(
        context: Context,
        taskId: Int,
        taskTitle: String,
        dueText: String,
        reminderId: String?,
        triggerAtMillis: Long,
        soundOption: String = "voice_then_tone",
        songUri: String = "",
        userName: String = "",
        spokenText: String = ""
    ) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val intent = Intent(context, ReminderAlarmReceiver::class.java).apply {
            putExtra(EXTRA_TASK_ID, taskId)
            putExtra(EXTRA_TASK_TITLE, taskTitle)
            putExtra(EXTRA_DUE_TEXT, dueText)
            putExtra(EXTRA_REMINDER_ID, reminderId)
            putExtra(EXTRA_SOUND_OPTION, soundOption)
            putExtra(EXTRA_SONG_URI, songUri)
            putExtra(EXTRA_USER_NAME, userName)
            putExtra(EXTRA_SPOKEN_TEXT, spokenText)
        }

        val requestCode = (taskId * 31 + (reminderId?.hashCode() ?: 0)).let { if (it < 0) -it else it }
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Show intent for AlarmClockInfo: opens AlarmActivity directly when user taps the alarm clock icon in system UI
        val showIntent = Intent(context, AlarmActivity::class.java).apply {
            putExtra(AlarmActivity.EXTRA_TASK_ID, taskId)
            putExtra(AlarmActivity.EXTRA_TASK_TITLE, taskTitle)
            putExtra(AlarmActivity.EXTRA_DUE_TEXT, dueText)
            putExtra(AlarmActivity.EXTRA_SOUND_OPTION, soundOption)
            putExtra(AlarmActivity.EXTRA_SONG_URI, songUri)
            putExtra(AlarmActivity.EXTRA_USER_NAME, userName)
            putExtra(AlarmActivity.EXTRA_SPOKEN_TEXT, spokenText)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val showPendingIntent = PendingIntent.getActivity(
            context,
            requestCode + 1000,
            showIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        try {
            // AlarmManager.setAlarmClock is the gold standard for clock/alarm apps:
            // - Wakes the CPU from deepest Doze mode
            // - Starts even if the app was swiped from recents or killed
            // - Highest reliability across all Android vendors (Samsung, Xiaomi, Pixel, OnePlus)
            val clockInfo = AlarmManager.AlarmClockInfo(triggerAtMillis, showPendingIntent)
            alarmManager.setAlarmClock(clockInfo, pendingIntent)
        } catch (e: Exception) {
            // Fallback if setAlarmClock has OS-level security restriction
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
                put("sound_option", item.soundOption)
                put("song_uri", item.songUri)
                put("user_name", item.userName)
                put("spoken_text", item.spokenText)
            }
            jsonArray.put(jsonItem)

            val triggerMillis = parseDateTimeToMillis(item.reminderTime)
            if (triggerMillis != null && triggerMillis > now) {
                scheduleExactAlarm(
                    context = context,
                    taskId = item.taskId,
                    taskTitle = item.taskTitle,
                    dueText = item.label,
                    reminderId = item.reminderId,
                    triggerAtMillis = triggerMillis,
                    soundOption = item.soundOption,
                    songUri = item.songUri,
                    userName = item.userName,
                    spokenText = item.spokenText
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
                        context = context,
                        taskId = item.getInt("task_id"),
                        taskTitle = item.optString("task_title", "Reminder"),
                        dueText = item.optString("label", "Due now"),
                        reminderId = item.optString("reminder_id", null),
                        triggerAtMillis = triggerMillis,
                        soundOption = item.optString("sound_option", "voice_then_tone"),
                        songUri = item.optString("song_uri", ""),
                        userName = item.optString("user_name", ""),
                        spokenText = item.optString("spoken_text", "")
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
        soundOption: String = "voice_then_tone",
        songUri: String = "",
        userName: String = "",
        spokenText: String = ""
    ) {
        val prefs = PreferencesManager(context)
        val cached = prefs.cachedRemindersJson
        val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        val formattedTime = sdf.format(Date(triggerAtMillis))

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
                            put("sound_option", soundOption.ifEmpty { item.optString("sound_option", "voice_then_tone") })
                            put("song_uri", songUri.ifEmpty { item.optString("song_uri", "") })
                            put("user_name", userName.ifEmpty { item.optString("user_name", "") })
                            put("spoken_text", spokenText.ifEmpty { item.optString("spoken_text", "") })
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
                put("sound_option", soundOption)
                put("song_uri", songUri)
                put("user_name", userName)
                put("spoken_text", spokenText)
            }
            newArray.put(newItem)
        }

        prefs.cachedRemindersJson = newArray.toString()
    }
}
