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

    fun scheduleExactAlarm(
        context: Context,
        taskId: Int,
        taskTitle: String,
        dueText: String,
        reminderId: String?,
        triggerAtMillis: Long
    ) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val intent = Intent(context, ReminderAlarmReceiver::class.java).apply {
            putExtra(EXTRA_TASK_ID, taskId)
            putExtra(EXTRA_TASK_TITLE, taskTitle)
            putExtra(EXTRA_DUE_TEXT, dueText)
            putExtra(EXTRA_REMINDER_ID, reminderId)
        }

        val requestCode = (taskId * 31 + (reminderId?.hashCode() ?: 0)).let { if (it < 0) -it else it }
        val pendingIntent = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (alarmManager.canScheduleExactAlarms()) {
                alarmManager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    triggerAtMillis,
                    pendingIntent
                )
            } else {
                alarmManager.setAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    triggerAtMillis,
                    pendingIntent
                )
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
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
                    triggerMillis
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
                        triggerMillis
                    )
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
