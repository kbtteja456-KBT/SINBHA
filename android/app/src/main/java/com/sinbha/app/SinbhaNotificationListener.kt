package com.sinbha.app

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import java.util.concurrent.ConcurrentLinkedDeque

/**
 * Step 16c: Notification Listener Service for Cross-Device Intelligence.
 * Securely maintains an in-memory buffer of recent notifications (WhatsApp, Gmail, SMS)
 * so paired devices can summarize communication alerts upon user request.
 */
class SinbhaNotificationListener : NotificationListenerService() {

    data class NotificationItem(
        val app: String,
        val title: String,
        val text: String,
        val timestamp: Long
    )

    companion object {
        private val buffer = ConcurrentLinkedDeque<NotificationItem>()

        fun getRecent(): List<NotificationItem> {
            return buffer.toList()
        }

        fun clear() {
            buffer.clear()
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        val s = sbn ?: return
        val pkg = s.packageName ?: ""

        // Skip our own notifications and ongoing persistent system bars
        if (s.isOngoing || pkg == packageName || pkg == "android" || pkg == "com.android.systemui") {
            return
        }

        val extras = s.notification?.extras ?: return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.trim() ?: ""

        if (title.isNotEmpty() || text.isNotEmpty()) {
            val appLabel = when {
                pkg.contains("whatsapp") -> "WhatsApp"
                pkg.contains("gm") || pkg.contains("email") -> "Gmail"
                pkg.contains("messaging") || pkg.contains("mms") || pkg.contains("sms") -> "Messages"
                pkg.contains("telegram") -> "Telegram"
                pkg.contains("slack") -> "Slack"
                pkg.contains("discord") -> "Discord"
                pkg.contains("instagram") -> "Instagram"
                else -> pkg.substringAfterLast('.')
            }

            buffer.addFirst(
                NotificationItem(
                    app = appLabel,
                    title = title.take(120),
                    text = text.take(300),
                    timestamp = s.postTime
                )
            )

            // Bound memory buffer to 25 items
            while (buffer.size > 25) {
                buffer.removeLast()
            }
        }
    }
}
