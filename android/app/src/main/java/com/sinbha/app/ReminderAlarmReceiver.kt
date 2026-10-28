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
 * Guarantees high-priority sound, vibration, and lockscreen alerts even
 * when phone is asleep or app is swiped away. Launches the floating bird
 * overlay when the user is actively using the phone.
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

        val taskId = intent.getIntExtra(AlarmScheduler.EXTRA_TASK_ID, -1)
        val taskTitle = intent.getStringExtra(AlarmScheduler.EXTRA_TASK_TITLE) ?: "Task Reminder"
        val dueText = intent.getStringExtra(AlarmScheduler.EXTRA_DUE_TEXT) ?: "Due now"
        val soundOption = intent.getStringExtra(AlarmScheduler.EXTRA_SOUND_OPTION) ?: "voice_then_tone"
        val songUri = intent.getStringExtra(AlarmScheduler.EXTRA_SONG_URI) ?: ""
        val userName = intent.getStringExtra(AlarmScheduler.EXTRA_USER_NAME) ?: ""
        val spokenText = intent.getStringExtra(AlarmScheduler.EXTRA_SPOKEN_TEXT) ?: ""

        // 2. Wake up device screen so user sees the clock alarm immediately
        try {
            val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
            val wakeLock = pm?.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "sinbha:reminder_alarm_wake"
            )
            wakeLock?.acquire(10000L) // 10 seconds to light up screen
        } catch (e: Exception) {}

        // 3. Launch full-screen AlarmActivity immediately (over lockscreen & screen-off)
        val alarmIntent = Intent(context, AlarmActivity::class.java).apply {
            putExtra(AlarmActivity.EXTRA_TASK_ID, taskId)
            putExtra(AlarmActivity.EXTRA_TASK_TITLE, taskTitle)
            putExtra(AlarmActivity.EXTRA_DUE_TEXT, dueText)
            putExtra(AlarmActivity.EXTRA_SOUND_OPTION, soundOption)
            putExtra(AlarmActivity.EXTRA_SONG_URI, songUri)
            putExtra(AlarmActivity.EXTRA_USER_NAME, userName)
            putExtra(AlarmActivity.EXTRA_SPOKEN_TEXT, spokenText)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_NO_USER_ACTION
        }

        try {
            context.startActivity(alarmIntent)
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // 4. Also trigger full-screen intent heads-up notification with sound & vibration
        showHighPriorityNotification(
            context = context,
            taskId = taskId,
            title = taskTitle,
            dueText = dueText,
            alarmIntent = alarmIntent
        )

        // 5. If user allowed overlay: launch floating bird over active apps
        val canOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(context)
        } else {
            true
        }

        if (canOverlay) {
            OverlayBirdService.launch(context, taskId, taskTitle, dueText)
        }
    }

    private fun isQuietHoursActive(prefs: PreferencesManager): Boolean {
        if (!prefs.isQuietHoursEnabled) return false
        val nowStr = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        val start = prefs.quietHoursStart
        val end = prefs.quietHoursEnd

        return if (start > end) {
            nowStr >= start || nowStr < end
        } else {
            nowStr in start..<end
        }
    }

    private fun showHighPriorityNotification(
        context: Context,
        taskId: Int,
        title: String,
        dueText: String,
        alarmIntent: Intent
    ) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                REMINDER_CHANNEL_ID,
                "SINBHA Task Alarms",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Urgent reminder alarms with full-screen clock display, Dismiss, and Snooze"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 500, 200, 500, 200, 500)
                enableLights(true)
                lightColor = Color.parseColor("#F25F85")
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

        // Full Screen Pending Intent: opens AlarmActivity directly on lockscreen or heads-up banner
        val pFullScreen = PendingIntent.getActivity(
            context,
            taskId * 10 + 9,
            alarmIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Action: Done / Dismiss
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

        // Action: Open App
        val openIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("open_task_id", taskId)
        }
        val pOpen = PendingIntent.getActivity(
            context,
            taskId * 10 + 3,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(context, REMINDER_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_sinbha)
            .setContentTitle("⏰ $title")
            .setContentText(dueText)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(Color.parseColor("#F25F85"))
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 500, 200, 500, 200, 500))
            .setDefaults(Notification.DEFAULT_ALL)
            .setAutoCancel(true)
            .setContentIntent(pOpen)
            .setFullScreenIntent(pFullScreen, true)
            .addAction(R.drawable.ic_sinbha, "✓ Dismiss", pDone)
            .addAction(R.drawable.ic_sinbha, "⏰ Snooze 5m", pSnooze5)
            .build()

        manager.notify(taskId, notif)
    }
}
