package com.sinbha.app

import android.app.KeyguardManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.NotificationCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Receiver invoked by AlarmManager when an exact reminder fires.
 * Enforces STOP rules, Quiet Hours, and system DND.
 * Launches the full-screen AlarmActivity (over lockscreen) with ALARM audio stream,
 * rising volume, looping sound/TTS, and Done/Snooze actions.
 */
class ReminderAlarmReceiver : BroadcastReceiver() {

    companion object {
        const val REMINDER_CHANNEL_ID = "sinbha_reminder_alerts_channel"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val prefs = PreferencesManager(context)

        // 1. Respect STOP (Emergency Stopped)
        if (prefs.isEmergencyStopped) {
            return
        }

        // 2. Respect DND choices
        if (!prefs.dndAllowAlarms) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && nm != null) {
                val filter = nm.currentInterruptionFilter
                if (filter == NotificationManager.INTERRUPTION_FILTER_NONE ||
                    filter == NotificationManager.INTERRUPTION_FILTER_PRIORITY) {
                    // Suppressed by user DND preference
                    return
                }
            }
        }

        val taskId = intent.getIntExtra(AlarmScheduler.EXTRA_TASK_ID, -1)
        val taskTitle = intent.getStringExtra(AlarmScheduler.EXTRA_TASK_TITLE) ?: "Task Reminder"
        val dueText = intent.getStringExtra(AlarmScheduler.EXTRA_DUE_TEXT) ?: "Due now 🌸"
        val reminderId = intent.getStringExtra(AlarmScheduler.EXTRA_REMINDER_ID)
        val soundMode = intent.getStringExtra(AlarmScheduler.EXTRA_SOUND_MODE) ?: prefs.reminderSoundMode
        val customSongUri = intent.getStringExtra(AlarmScheduler.EXTRA_CUSTOM_SONG_URI) ?: prefs.customSongUri
        val userName = intent.getStringExtra(AlarmScheduler.EXTRA_USER_NAME) ?: (prefs.userDisplayName ?: "Friend")
        val speechText = intent.getStringExtra(AlarmScheduler.EXTRA_SPEECH_TEXT)

        // 3. Wake up device screen so user sees the reminder alert immediately
        try {
            val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
            val wakeLock = pm?.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "sinbha:reminder_alarm_wake"
            )
            wakeLock?.acquire(15000L) // 15 seconds to turn on screen
        } catch (e: Exception) {}

        // 4. Intent for full-screen Clock-app Alarm Experience
        val alarmIntent = Intent(context, AlarmActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_NO_USER_ACTION or
                    Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
            putExtra(AlarmScheduler.EXTRA_TASK_ID, taskId)
            putExtra(AlarmScheduler.EXTRA_TASK_TITLE, taskTitle)
            putExtra(AlarmScheduler.EXTRA_DUE_TEXT, dueText)
            putExtra(AlarmScheduler.EXTRA_REMINDER_ID, reminderId)
            putExtra(AlarmScheduler.EXTRA_SOUND_MODE, soundMode)
            putExtra(AlarmScheduler.EXTRA_CUSTOM_SONG_URI, customSongUri)
            putExtra(AlarmScheduler.EXTRA_USER_NAME, userName)
            putExtra(AlarmScheduler.EXTRA_SPEECH_TEXT, speechText)
        }

        val fullScreenPendingIntent = PendingIntent.getActivity(
            context,
            taskId * 10 + 7,
            alarmIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // 5. Always display high-priority notification with fullScreenIntent configured
        showHighPriorityNotification(context, taskId, taskTitle, dueText, fullScreenPendingIntent)

        // 6. Direct activity launch over lock screen / background
        try {
            context.startActivity(alarmIntent)
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // 7. If user allowed overlay: launch floating bird over active apps
        val canOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(context)
        } else {
            true
        }

        if (canOverlay) {
            OverlayBirdService.launch(context, taskId, taskTitle, dueText)
        }
    }

    private fun showHighPriorityNotification(
        context: Context,
        taskId: Int,
        title: String,
        dueText: String,
        fullScreenIntent: PendingIntent
    ) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                REMINDER_CHANNEL_ID,
                "SINBHA Task Reminders",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Urgent reminder alerts with Full-screen Alarm, Done, and Snooze"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 500, 200, 500, 200, 500)
                enableLights(true)
                lightColor = Color.parseColor("#EC4899")
                val audioAttributes = AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .build()
                setSound(soundUri, audioAttributes)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                setBypassDnd(true)
            }
            manager.createNotificationChannel(channel)
        }

        // Action: Done
        val doneIntent = Intent(context, ReminderActionReceiver::class.java).apply {
            action = ReminderActionReceiver.ACTION_MARK_DONE
            putExtra(ReminderActionReceiver.EXTRA_TASK_ID, taskId)
        }
        val pDone = PendingIntent.getBroadcast(
            context,
            taskId * 10 + 1,
            doneIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Action: Snooze 5m
        val snooze5Intent = Intent(context, ReminderActionReceiver::class.java).apply {
            action = ReminderActionReceiver.ACTION_SNOOZE
            putExtra(ReminderActionReceiver.EXTRA_TASK_ID, taskId)
            putExtra(ReminderActionReceiver.EXTRA_MINUTES, 5)
        }
        val pSnooze5 = PendingIntent.getBroadcast(
            context,
            taskId * 10 + 4,
            snooze5Intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Action: Snooze 15m
        val snooze15Intent = Intent(context, ReminderActionReceiver::class.java).apply {
            action = ReminderActionReceiver.ACTION_SNOOZE
            putExtra(ReminderActionReceiver.EXTRA_TASK_ID, taskId)
            putExtra(ReminderActionReceiver.EXTRA_MINUTES, 15)
        }
        val pSnooze15 = PendingIntent.getBroadcast(
            context,
            taskId * 10 + 2,
            snooze15Intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(context, REMINDER_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_sinbha)
            .setContentTitle("⏰ $title")
            .setContentText(dueText)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(Color.parseColor("#EC4899"))
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 500, 200, 500, 200, 500))
            .setDefaults(Notification.DEFAULT_ALL)
            .setAutoCancel(true)
            .setContentIntent(fullScreenIntent)
            .setFullScreenIntent(fullScreenIntent, true)
            .addAction(R.drawable.ic_sinbha, "✓ Done", pDone)
            .addAction(R.drawable.ic_sinbha, "⏰ 5m", pSnooze5)
            .addAction(R.drawable.ic_sinbha, "⏰ 15m", pSnooze15)
            .build()

        manager.notify(taskId, notif)
    }
}
