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
        const val EXTRA_TASK_ID = "extra_task_id"
    }

    override fun onReceive(context: Context, intent: Intent) {
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
                scope.launch {
                    apiClient.snoozeReminder(taskId, 15)
                }
            }
        }
    }
}
