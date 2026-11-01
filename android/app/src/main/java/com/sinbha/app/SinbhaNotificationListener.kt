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

        val lowerPkg = pkg.lowercase()
        // D2 Security Barrier: Strictly never read or capture notifications from banking, UPI, or password managers
        if (lowerPkg.contains("paisa") || lowerPkg.contains("phonepe") ||
            lowerPkg.contains("paytm") || lowerPkg.contains("upi") || lowerPkg.contains("bank") ||
            lowerPkg.contains("yono") || lowerPkg.contains("cred") || lowerPkg.contains("bitwarden") ||
            lowerPkg.contains("1password") || lowerPkg.contains("lastpass") || lowerPkg.contains("authenticator") ||
            lowerPkg.contains("wallet") || lowerPkg.contains("finance")
        ) {
            return
        }

        val extras = s.notification?.extras ?: return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim() ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.trim() ?: ""

        // D2 Security Barrier: Never capture OTPs, banking debits/credits, or financial credentials
        val lowerContent = (title + " " + text).lowercase()
        if (lowerContent.contains("otp") || lowerContent.contains("verification code") ||
            lowerContent.contains("debited") || lowerContent.contains("credited") ||
            lowerContent.contains("card pin") || lowerContent.contains("cvv") ||
            lowerContent.contains("secret code") || lowerContent.contains("one-time password")
        ) {
            return
        }

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
