package com.sinbha.app

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Handles action buttons from background Notifications (Done & Snooze)
 * without requiring the app or chat screen to open.
 */
class ReminderActionReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_MARK_DONE = "com.sinbha.app.ACTION_MARK_DONE"
        const val ACTION_SNOOZE = "com.sinbha.app.ACTION_SNOOZE"
        const val ACTION_STOP_RING = "com.sinbha.app.ACTION_STOP_RING"
        const val EXTRA_TASK_ID = "extra_task_id"
        const val EXTRA_MINUTES = "extra_minutes"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_STOP_RING) {
            SinbhaPlugin.stopCurrentAlarmRing(context)
            return
        }

        val taskId = intent.getIntExtra(EXTRA_TASK_ID, -1)
        if (taskId <= 0) return

        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.cancel(taskId)

        val apiClient = SinbhaApiClient(context)
        val scope = CoroutineScope(Dispatchers.IO)

        when (intent.action) {
            ACTION_MARK_DONE -> {
                scope.launch {
                    apiClient.markTaskDone(taskId)
                }
            }
            ACTION_SNOOZE -> {
                val minutes = intent.getIntExtra(EXTRA_MINUTES, 2)
                val taskTitle = intent.getStringExtra(AlarmScheduler.EXTRA_TASK_TITLE) ?: "Reminder"
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

                scope.launch {
                    apiClient.snoozeReminder(taskId, minutes)
                }
            }
        }
    }
}
