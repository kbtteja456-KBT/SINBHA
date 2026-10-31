package com.sinbha.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Persistent Foreground Service that keeps Android Companion connected to the SINBHA
 * device mesh even when swiped away from recent apps or screen is locked.
 *
 * Step C2.6:
 * - Uses native OkHttp WebSocket with exponential reconnect & ping/pong keepalive
 * - Polling loop as reliable fallback
 * - Correct Android 14/15 foregroundServiceType (dataSync)
 * - Reports full command lifecycle (received, started, succeeded, failed, needs_tap)
 * - OnePlus / Oppo Android 15 robustness (START_STICKY, boot restart)
 */
class SinbhaCompanionService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefs: PreferencesManager
    private lateinit var apiClient: SinbhaApiClient

    private var okHttpClient: OkHttpClient? = null
    private var webSocket: WebSocket? = null
    private var isWsConnecting = false
    private var reconnectAttempts = 0

    companion object {
        const val PERSISTENT_CHANNEL_ID = "sinbha_companion_persistent_channel"
        const val PERSISTENT_NOTIF_ID = 2002

        fun start(context: Context) {
            val intent = Intent(context, SinbhaCompanionService::class.java)
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = PreferencesManager(this)
        apiClient = SinbhaApiClient(this)

        createNotificationChannel()

        // Android 14 & 15: Correct ServiceInfo foregroundServiceType
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                PERSISTENT_NOTIF_ID,
                buildForegroundNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(PERSISTENT_NOTIF_ID, buildForegroundNotification())
        }

        initOkHttp()
        startWebSocketConnection()
        startPollingLoop()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Return START_STICKY to guarantee restart if killed by OS
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            webSocket?.close(1000, "Service destroyed")
        } catch (e: Exception) {}
        serviceScope.cancel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                PERSISTENT_CHANNEL_ID,
                "SINBHA Companion Sync",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps device commands & reminders synced across your phone and laptop"
                setShowBadge(false)
            }
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildForegroundNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pi = PendingIntent.getActivity(
            this,
            PERSISTENT_NOTIF_ID,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, PERSISTENT_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("SINBHA Companion Connected 🌸")
            .setContentText("Listening for phone & laptop commands in background")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setOngoing(true)
            .setContentIntent(pi)
            .build()
    }

    private fun initOkHttp() {
        okHttpClient = OkHttpClient.Builder()
            .pingInterval(30, TimeUnit.SECONDS)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS) // Infinite read timeout for long-lived WebSocket
            .build()
    }

    private fun ensureDeviceId(): String {
        var deviceId = prefs.deviceId
        if (deviceId.isNullOrEmpty()) {
            val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
            deviceId = "android_" + (androidId ?: UUID.randomUUID().toString().substring(0, 8))
            prefs.deviceId = deviceId
        }
        return deviceId
    }

    private fun startWebSocketConnection() {
        serviceScope.launch {
            while (isActive) {
                val token = prefs.commandToken ?: prefs.sessionToken
                if (!token.isNullOrEmpty() && !prefs.wsConnected && !isWsConnecting) {
                    connectWebSocket(token)
                }
                delay(5000L)
            }
        }
    }

    private fun connectWebSocket(token: String) {
        val client = okHttpClient ?: return
        isWsConnecting = true

        val deviceId = ensureDeviceId()
        val backend = prefs.backendUrl
        val wsBase = backend.replace("https://", "wss://").replace("http://", "ws://")
        val wsUrl = "$wsBase/api/ws/devices?token=$token&device_id=$deviceId"

        val request = Request.Builder()
            .url(wsUrl)
            .addHeader("Cookie", "sinbha_session=$token")
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isWsConnecting = false
                reconnectAttempts = 0
                prefs.wsConnected = true
                prefs.lastWsError = null

                // Send capability handshake with installed apps
                serviceScope.launch {
                    try {
                        val installedAppsList = SinbhaAppLauncher.getInstalledApps(applicationContext)
                        val appsArr = JSONArray()
                        for (app in installedAppsList) {
                            appsArr.put(JSONObject().apply {
                                put("name", app["name"])
                                put("package", app["package"])
                            })
                        }
                        val toolsArr = JSONArray().apply {
                            put("open_app")
                            put("open_url")
                            put("send_note")
                            put("ring_phone")
                            put("sync_tasks")
                        }
                        val handshake = JSONObject().apply {
                            put("type", "device_status")
                            put("platform", "android")
                            put("version", "1.4.7")
                            put("supported_tools", toolsArr)
                            put("installed_apps", appsArr)
                        }
                        ws.send(handshake.toString())
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                }
            }

            override fun onMessage(ws: WebSocket, text: String) {
                try {
                    val msg = JSONObject(text)
                    val type = msg.optString("type")
                    if (type in listOf("open_app", "ring_phone", "send_note", "emergency_stop")) {
                        serviceScope.launch {
                            executeAndReportCommand(msg)
                        }
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                ws.close(1000, "Normal closure")
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                prefs.wsConnected = false
                isWsConnecting = false
                scheduleWsReconnect()
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                prefs.wsConnected = false
                isWsConnecting = false
                val err = t.message ?: "WebSocket failure"
                prefs.lastWsError = err
                scheduleWsReconnect()
            }
        })
    }

    private fun scheduleWsReconnect() {
        serviceScope.launch {
            reconnectAttempts++
            // Exponential backoff: 1s, 2s, 4s, 8s, up to 30s
            val backoffMs = minOf(1000L * (1 shl minOf(reconnectAttempts, 5)), 30_000L)
            delay(backoffMs)
            val token = prefs.commandToken ?: prefs.sessionToken
            if (!token.isNullOrEmpty() && !prefs.wsConnected) {
                connectWebSocket(token)
            }
        }
    }

    private fun sendWsStatus(commandId: String, status: String, result: JSONObject? = null, error: String? = null) {
        try {
            if (prefs.wsConnected && webSocket != null) {
                val payload = JSONObject().apply {
                    put("type", "command_status")
                    put("command_id", commandId)
                    put("status", status)
                    if (result != null) put("result", result)
                    if (!error.isNullOrBlank()) put("error", error)
                }
                webSocket?.send(payload.toString())
            }
        } catch (e: Exception) {}
    }

    private fun startPollingLoop() {
        serviceScope.launch {
            var lastAlarmSyncTime = 0L

            while (isActive) {
                try {
                    val token = prefs.commandToken ?: prefs.sessionToken
                    if (!token.isNullOrEmpty()) {
                        val deviceId = ensureDeviceId()

                        // Poll for pending remote commands as fallback
                        val commands = apiClient.fetchPendingCommands(deviceId)
                        for (cmd in commands) {
                            executeAndReportCommand(cmd)
                        }

                        // Periodically sync alarms (every 60s)
                        val now = System.currentTimeMillis()
                        if (now - lastAlarmSyncTime > 60_000L) {
                            lastAlarmSyncTime = now
                            try {
                                AlarmScheduler.syncAndScheduleUpcoming(applicationContext)
                            } catch (e: Exception) {}
                        }
                    }
                } catch (e: Exception) {
                    prefs.lastError = e.message
                }

                // If WebSocket is active, poll less aggressively (every 8s); if disconnected, poll every 3s
                val pollDelay = if (prefs.wsConnected) 8000L else 3000L
                delay(pollDelay)
            }
        }
    }

    /**
     * Step C2.6 Item 2: Reports full lifecycle of every command to /api/devices/command-status
     * (received, started, succeeded, failed, needs_tap) with real results and exact reasons.
     */
    private suspend fun executeAndReportCommand(cmd: JSONObject) {
        val cmdId = cmd.optString("command_id").takeIf { it.isNotBlank() }
            ?: cmd.optString("id").takeIf { it.isNotBlank() } ?: return
        val type = cmd.optString("type")
        val payload = cmd.optJSONObject("payload") ?: JSONObject()
        val sender = cmd.optString("sender_name", "Paired Companion")

        // 1. Report "received"
        apiClient.reportCommandStatus(cmdId, "received")
        sendWsStatus(cmdId, "received")

        // 2. Report "started"
        apiClient.reportCommandStatus(cmdId, "started")
        sendWsStatus(cmdId, "started")

        // 3. Execute command and report result
        when (type) {
            "open_app" -> {
                val launchResult = SinbhaAppLauncher.launchFromPayload(applicationContext, payload)
                if (launchResult.success) {
                    val resObj = JSONObject().apply {
                        put("app", launchResult.app)
                        put("package", launchResult.packageName ?: "")
                        put("method", launchResult.method ?: "overlay_exemption")
                    }
                    apiClient.reportCommandStatus(cmdId, "succeeded", result = resObj)
                    sendWsStatus(cmdId, "succeeded", result = resObj)
                } else if (launchResult.needsTap) {
                    val resObj = JSONObject().apply {
                        put("app", launchResult.app)
                        put("package", launchResult.packageName ?: "")
                        put("needs_tap", true)
                        put("reason", "background launch blocked")
                    }
                    val err = launchResult.error ?: "needs a tap"
                    apiClient.reportCommandStatus(cmdId, "needs_tap", result = resObj, error = err)
                    sendWsStatus(cmdId, "needs_tap", result = resObj, error = err)
                } else {
                    val err = launchResult.error ?: "App '${launchResult.app}' is not installed on this Android device."
                    apiClient.reportCommandStatus(cmdId, "failed", error = err)
                    sendWsStatus(cmdId, "failed", error = err)
                }
            }
            "ring_phone" -> {
                val ok = SinbhaPlugin.startAlarmRing(applicationContext, sender)
                if (ok) {
                    val resObj = JSONObject().put("status", "ringing")
                    apiClient.reportCommandStatus(cmdId, "succeeded", result = resObj)
                    sendWsStatus(cmdId, "succeeded", result = resObj)
                } else {
                    val err = "Failed to start phone ring"
                    apiClient.reportCommandStatus(cmdId, "failed", error = err)
                    sendWsStatus(cmdId, "failed", error = err)
                }
            }
            "send_note" -> {
                showNoteHeadsUp(
                    payload.optString("title", "Note from Paired Device"),
                    payload.optString("text", "")
                )
                val resObj = JSONObject().put("delivered", true)
                apiClient.reportCommandStatus(cmdId, "succeeded", result = resObj)
                sendWsStatus(cmdId, "succeeded", result = resObj)
            }
            "emergency_stop" -> {
                prefs.isEmergencyStopped = true
                val resObj = JSONObject().put("emergency_stopped", true)
                apiClient.reportCommandStatus(cmdId, "succeeded", result = resObj)
                sendWsStatus(cmdId, "succeeded", result = resObj)
            }
            else -> {
                val err = "Unsupported command type: $type"
                apiClient.reportCommandStatus(cmdId, "failed", error = err)
                sendWsStatus(cmdId, "failed", error = err)
            }
        }
    }

    private fun showNoteHeadsUp(title: String, text: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pi = PendingIntent.getActivity(
            this,
            (System.currentTimeMillis() % 10000).toInt(),
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notif = NotificationCompat.Builder(this, SinbhaPlugin.DEVICE_COMMANDS_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()

        nm.notify((System.currentTimeMillis() % 10000).toInt() + 1000, notif)
    }
}
