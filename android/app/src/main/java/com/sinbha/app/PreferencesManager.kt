package com.sinbha.app

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Encrypted preferences manager for secure token storage and app settings.
 * Stores device session token without ever persisting user passwords.
 */
class PreferencesManager(private val context: Context) {

    private val prefs: SharedPreferences by lazy {
        try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context,
                "sinbha_secure_prefs",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            // Fallback to private preferences if device keystore fails in unusual emulators
            context.getSharedPreferences("sinbha_fallback_prefs", Context.MODE_PRIVATE)
        }
    }

    companion object {
        private const val KEY_SESSION_TOKEN = "session_token"
        private const val KEY_COMMAND_TOKEN = "command_token"
        private const val KEY_BACKEND_URL = "backend_url"
        private const val KEY_USER_EMAIL = "user_email"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_EMERGENCY_STOP = "emergency_stopped"
        private const val KEY_QUIET_HOURS_ENABLED = "quiet_hours_enabled"
        private const val KEY_QUIET_HOURS_START = "quiet_hours_start"
        private const val KEY_QUIET_HOURS_END = "quiet_hours_end"
        private const val KEY_REDUCE_MOTION = "reduce_motion"
        private const val KEY_CACHED_REMINDERS = "cached_reminders_json"
        private const val KEY_AUTH_PAUSED_ALERT_SHOWN = "auth_paused_alert_shown"
        private const val KEY_LAST_SYNC_TIME = "last_sync_time"
        private const val KEY_LAST_POLL_TIME = "last_poll_time"
        private const val KEY_LAST_HTTP_STATUS = "last_http_status"
        private const val KEY_LAST_ERROR = "last_error"
        private const val KEY_WS_CONNECTED = "ws_connected"
        private const val KEY_LAST_WS_ERROR = "last_ws_error"
        private const val KEY_RECENT_ERRORS = "recent_errors_json"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_REMINDER_SOUND_MODE = "reminder_sound_mode"
        private const val KEY_CUSTOM_SONG_URI = "custom_song_uri"
        private const val KEY_USER_DISPLAY_NAME = "user_display_name"
        private const val KEY_DND_ALLOW_ALARMS = "dnd_allow_alarms"
        const val DEFAULT_BACKEND_URL = "https://sinbha-backend.onrender.com"
    }

    var reminderSoundMode: String
        get() = prefs.getString(KEY_REMINDER_SOUND_MODE, "alarm_tone") ?: "alarm_tone"
        set(value) = prefs.edit().putString(KEY_REMINDER_SOUND_MODE, value).apply()

    var customSongUri: String?
        get() = prefs.getString(KEY_CUSTOM_SONG_URI, null)
        set(value) = prefs.edit().putString(KEY_CUSTOM_SONG_URI, value).apply()

    var userDisplayName: String?
        get() = prefs.getString(KEY_USER_DISPLAY_NAME, "Friend")
        set(value) = prefs.edit().putString(KEY_USER_DISPLAY_NAME, value).apply()

    var dndAllowAlarms: Boolean
        get() = prefs.getBoolean(KEY_DND_ALLOW_ALARMS, true)
        set(value) = prefs.edit().putBoolean(KEY_DND_ALLOW_ALARMS, value).apply()

    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE_ID, null)
        set(value) = prefs.edit().putString(KEY_DEVICE_ID, value).apply()

    var lastSyncTime: String?
        get() = prefs.getString(KEY_LAST_SYNC_TIME, null)
        set(value) = prefs.edit().putString(KEY_LAST_SYNC_TIME, value).apply()

    var recentErrorsJson: String
        get() = prefs.getString(KEY_RECENT_ERRORS, "[]") ?: "[]"
        set(value) = prefs.edit().putString(KEY_RECENT_ERRORS, value).apply()

    fun recordError(message: String) {
        try {
            val arr = org.json.JSONArray(recentErrorsJson)
            val item = org.json.JSONObject().apply {
                put("time", java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date()))
                // Scrub potential tokens/passwords
                val sanitized = message
                    .replace(Regex("Bearer\\s+[a-zA-Z0-9_.-]+", RegexOption.IGNORE_CASE), "Bearer [REDACTED]")
                    .replace(Regex("snb_dev_[a-zA-Z0-9_.-]+", RegexOption.IGNORE_CASE), "[REDACTED_DEV_TOKEN]")
                put("message", sanitized)
            }
            arr.put(item)
            // Keep strictly last 20 errors
            val trimmed = org.json.JSONArray()
            val start = if (arr.length() > 20) arr.length() - 20 else 0
            for (i in start until arr.length()) {
                trimmed.put(arr.get(i))
            }
            recentErrorsJson = trimmed.toString()
        } catch (e: Exception) {}
    }

    var sessionToken: String?
        get() = prefs.getString(KEY_SESSION_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_SESSION_TOKEN, value).apply()

    var commandToken: String?
        get() = prefs.getString(KEY_COMMAND_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_COMMAND_TOKEN, value).apply()

    var lastPollTime: String?
        get() = prefs.getString(KEY_LAST_POLL_TIME, null)
        set(value) = prefs.edit().putString(KEY_LAST_POLL_TIME, value).apply()

    var lastHttpStatus: Int
        get() = prefs.getInt(KEY_LAST_HTTP_STATUS, -1)
        set(value) = prefs.edit().putInt(KEY_LAST_HTTP_STATUS, value).apply()

    var lastError: String?
        get() = prefs.getString(KEY_LAST_ERROR, null)
        set(value) = prefs.edit().putString(KEY_LAST_ERROR, value).apply()

    var wsConnected: Boolean
        get() = prefs.getBoolean(KEY_WS_CONNECTED, false)
        set(value) = prefs.edit().putBoolean(KEY_WS_CONNECTED, value).apply()

    var lastWsError: String?
        get() = prefs.getString(KEY_LAST_WS_ERROR, null)
        set(value) = prefs.edit().putString(KEY_LAST_WS_ERROR, value).apply()

    var backendUrl: String
        get() = prefs.getString(KEY_BACKEND_URL, DEFAULT_BACKEND_URL) ?: DEFAULT_BACKEND_URL
        set(value) = prefs.edit().putString(KEY_BACKEND_URL, value).apply()

    var userEmail: String?
        get() = prefs.getString(KEY_USER_EMAIL, null)
        set(value) = prefs.edit().putString(KEY_USER_EMAIL, value).apply()

    var userId: Int
        get() = prefs.getInt(KEY_USER_ID, -1)
        set(value) = prefs.edit().putInt(KEY_USER_ID, value).apply()

    var isEmergencyStopped: Boolean
        get() = prefs.getBoolean(KEY_EMERGENCY_STOP, false)
        set(value) = prefs.edit().putBoolean(KEY_EMERGENCY_STOP, value).apply()

    var isQuietHoursEnabled: Boolean
        get() = prefs.getBoolean(KEY_QUIET_HOURS_ENABLED, true)
        set(value) = prefs.edit().putBoolean(KEY_QUIET_HOURS_ENABLED, value).apply()

    var quietHoursStart: String
        get() = prefs.getString(KEY_QUIET_HOURS_START, "22:00") ?: "22:00"
        set(value) = prefs.edit().putString(KEY_QUIET_HOURS_START, value).apply()

    var quietHoursEnd: String
        get() = prefs.getString(KEY_QUIET_HOURS_END, "08:00") ?: "08:00"
        set(value) = prefs.edit().putString(KEY_QUIET_HOURS_END, value).apply()

    var isReduceMotion: Boolean
        get() = prefs.getBoolean(KEY_REDUCE_MOTION, false)
        set(value) = prefs.edit().putBoolean(KEY_REDUCE_MOTION, value).apply()

    var cachedRemindersJson: String?
        get() = prefs.getString(KEY_CACHED_REMINDERS, null)
        set(value) = prefs.edit().putString(KEY_CACHED_REMINDERS, value).apply()

    var isAuthPausedAlertShown: Boolean
        get() = prefs.getBoolean(KEY_AUTH_PAUSED_ALERT_SHOWN, false)
        set(value) = prefs.edit().putBoolean(KEY_AUTH_PAUSED_ALERT_SHOWN, value).apply()

    fun clearSession() {
        prefs.edit()
            .remove(KEY_SESSION_TOKEN)
            .remove(KEY_COMMAND_TOKEN)
            .remove(KEY_USER_EMAIL)
            .remove(KEY_USER_ID)
            .remove(KEY_CACHED_REMINDERS)
            .remove(KEY_LAST_POLL_TIME)
            .remove(KEY_LAST_HTTP_STATUS)
            .remove(KEY_LAST_ERROR)
            .remove(KEY_WS_CONNECTED)
            .remove(KEY_LAST_WS_ERROR)
            .putBoolean(KEY_AUTH_PAUSED_ALERT_SHOWN, false)
            .apply()
    }
}
