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
        val dueText = intent.getStringExtra(AlarmScheduler.EXTRA_DUE_TEXT) ?: "Due now 🌸"

        // 2. Respect Quiet Hours
        if (isQuietHoursActive(prefs)) {
            // Suppress non-critical alerts during quiet hours
            return
        }

        // 3. Respect System Do Not Disturb (DND)
        val notifManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val filter = notifManager.currentInterruptionFilter
            if (filter == NotificationManager.INTERRUPTION_FILTER_NONE ||
                filter == NotificationManager.INTERRUPTION_FILTER_ALARMS
            ) {
                // System DND is strictly blocking notifications
                return
            }
        }

        // 4. Wake up device screen briefly so user sees the reminder alert immediately
        try {
            val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
            val wakeLock = pm?.newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "sinbha:reminder_alarm_wake"
            )
            wakeLock?.acquire(8000L) // 8 seconds to light up screen
        } catch (e: Exception) {}

        // 5. Always display high-priority sound, vibration, and heads-up notification!
        showHighPriorityNotification(context, taskId, taskTitle, dueText)

        // 6. If screen is active, unlocked, and user allowed overlay: launch floating bird
        val canOverlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(context)
        } else {
            true
        }

        val powerManager = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
        val keyguardManager = context.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
        val isInteractive = powerManager?.isInteractive ?: false
        val isLocked = keyguardManager?.isKeyguardLocked ?: false

        if (canOverlay && isInteractive && !isLocked) {
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

    private fun showHighPriorityNotification(context: Context, taskId: Int, title: String, dueText: String) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                REMINDER_CHANNEL_ID,
                "SINBHA Task Reminders",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Urgent reminder alerts with Done and Snooze actions"
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

        // Action: Snooze 2m
        val snooze2Intent = Intent(context, ReminderActionReceiver::class.java).apply {
            action = ReminderActionReceiver.ACTION_SNOOZE
            putExtra(ReminderActionReceiver.EXTRA_TASK_ID, taskId)
            putExtra(ReminderActionReceiver.EXTRA_MINUTES, 2)
        }
        val pSnooze2 = PendingIntent.getBroadcast(
            context,
            taskId * 10 + 4,
            snooze2Intent,
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
            .setContentTitle("🕊️ $title")
            .setContentText(dueText)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(Color.parseColor("#EC4899"))
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 500, 200, 500, 200, 500))
            .setDefaults(Notification.DEFAULT_ALL)
            .setAutoCancel(true)
            .setContentIntent(pOpen)
            .addAction(R.drawable.ic_sinbha, "✓ Done", pDone)
            .addAction(R.drawable.ic_sinbha, "⏰ 2m", pSnooze2)
            .addAction(R.drawable.ic_sinbha, "⏰ 15m", pSnooze15)
            .build()

        manager.notify(taskId, notif)
    }
}
