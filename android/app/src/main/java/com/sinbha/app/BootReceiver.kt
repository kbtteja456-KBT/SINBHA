package com.sinbha.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Ensures reminders survive device reboots and app updates.
 * Reschedules alarms immediately from encrypted cache, then performs
 * a background sync with the cloud backend.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action == Intent.ACTION_BOOT_COMPLETED ||
            action == Intent.ACTION_MY_PACKAGE_REPLACED ||
            action == "android.intent.action.QUICKBOOT_POWERON"
        ) {
            // 1. Immediate local restore from cache
            AlarmScheduler.rescheduleFromCache(context)

            // 2. Cloud sync in background
            val scope = CoroutineScope(Dispatchers.IO)
            scope.launch {
                try {
                    AlarmScheduler.syncAndScheduleUpcoming(context)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }
    }
}
