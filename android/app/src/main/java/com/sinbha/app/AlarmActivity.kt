package com.sinbha.app

import android.app.KeyguardManager
import android.app.NotificationManager
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Full-screen Alarm Activity providing a Clock-app grade experience.
 * Wakes up locked screens, loops audio on STREAM_ALARM with gradually
 * rising volume, loops vibration, and supports alarm tones, custom songs,
 * and spoken voice via TextToSpeech with graceful fallbacks.
 */
class AlarmActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private var taskId: Int = -1
    private var taskTitle: String = "Task Reminder"
    private var dueText: String = "Due now 🌸"
    private var reminderId: String? = null
    private var soundMode: String = "alarm_tone"
    private var customSongUri: String? = null
    private var userName: String = "Friend"
    private var speechText: String? = null

    private var mediaPlayer: MediaPlayer? = null
    private var vibrator: Vibrator? = null
    private var tts: TextToSpeech? = null
    private var isTtsReady = false

    private val volumeHandler = Handler(Looper.getMainLooper())
    private var currentVolume = 0.15f
    private var isAlarmActive = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = PreferencesManager(this)
        if (prefs.isEmergencyStopped) {
            finish()
            return
        }

        // Configure full-screen lockscreen wakeup
        configureWindowFlags()

        setContentView(R.layout.activity_alarm)

        // Read intent extras
        taskId = intent.getIntExtra(AlarmScheduler.EXTRA_TASK_ID, -1)
        taskTitle = intent.getStringExtra(AlarmScheduler.EXTRA_TASK_TITLE) ?: "Task Reminder"
        dueText = intent.getStringExtra(AlarmScheduler.EXTRA_DUE_TEXT) ?: "Due now 🌸"
        reminderId = intent.getStringExtra(AlarmScheduler.EXTRA_REMINDER_ID)
        soundMode = intent.getStringExtra(AlarmScheduler.EXTRA_SOUND_MODE) ?: prefs.reminderSoundMode
        customSongUri = intent.getStringExtra(AlarmScheduler.EXTRA_CUSTOM_SONG_URI) ?: prefs.customSongUri
        userName = intent.getStringExtra(AlarmScheduler.EXTRA_USER_NAME) ?: (prefs.userDisplayName ?: "Friend")
        speechText = intent.getStringExtra(AlarmScheduler.EXTRA_SPEECH_TEXT)

        initViews()
        initAudioAndHaptics()
    }

    private fun configureWindowFlags() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val km = getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
            km?.requestDismissKeyguard(this, null)
        }
    }

    private fun initViews() {
        val timeTv = findViewById<TextView>(R.id.alarmTimeText)
        val greetingTv = findViewById<TextView>(R.id.alarmGreetingText)
        val titleTv = findViewById<TextView>(R.id.alarmTaskTitle)
        val dueTv = findViewById<TextView>(R.id.alarmDueSubtitle)
        val badgeTv = findViewById<TextView>(R.id.alarmSoundBadge)

        val dismissBtn = findViewById<Button>(R.id.alarmDismissBtn)
        val snooze2mBtn = findViewById<Button>(R.id.alarmSnooze2mBtn)
        val snooze5mBtn = findViewById<Button>(R.id.alarmSnooze5mBtn)
        val snooze15mBtn = findViewById<Button>(R.id.alarmSnooze15mBtn)

        timeTv.text = SimpleDateFormat("hh:mm a", Locale.getDefault()).format(Date())
        titleTv.text = taskTitle
        dueTv.text = dueText

        val cleanTitle = if (taskTitle.lowercase().startsWith("to ")) taskTitle.substring(3) else taskTitle
        greetingTv.text = "Hey $userName, it is time to:"

        badgeTv.text = when (soundMode) {
            "voice" -> "🗣️ Spoken Voice"
            "voice_then_tone" -> "🗣️ Voice ➔ 🔔 Tone"
            "song" -> "🎵 Song Mode"
            else -> "🔔 Alarm Tone"
        }

        dismissBtn.setOnClickListener {
            handleDismiss()
        }

        snooze2mBtn.setOnClickListener {
            handleSnooze(2)
        }

        snooze5mBtn.setOnClickListener {
            handleSnooze(5)
        }

        snooze15mBtn.setOnClickListener {
            handleSnooze(15)
        }
    }

    private fun initAudioAndHaptics() {
        startLoopingVibration()

        when (soundMode) {
            "voice", "voice_then_tone" -> {
                try {
                    tts = TextToSpeech(this, this)
                } catch (e: Exception) {
                    // Fall back to alarm tone if TTS engine cannot be instantiated
                    startLoopingTone()
                }
            }
            "song" -> {
                startCustomSongOrFallback()
            }
            else -> {
                startLoopingTone()
            }
        }
    }

    override fun onInit(status: Int) {
        if (!isAlarmActive) return
        if (status == TextToSpeech.SUCCESS && tts != null) {
            isTtsReady = true
            tts?.language = Locale.getDefault()
            val cleanTitle = if (taskTitle.lowercase().startsWith("to ")) taskTitle.substring(3) else taskTitle
            val message = speechText ?: "Hey $userName, it is time to $cleanTitle"

            val audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()

            tts?.setAudioAttributes(audioAttributes)

            tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}

                override fun onDone(utteranceId: String?) {
                    if (!isAlarmActive) return
                    if (soundMode == "voice_then_tone") {
                        runOnUiThread {
                            startLoopingTone()
                        }
                    } else if (soundMode == "voice") {
                        // Loop spoken message every 4 seconds
                        volumeHandler.postDelayed({
                            if (isAlarmActive && isTtsReady) {
                                speakAlarmMessage(message)
                            }
                        }, 4000)
                    }
                }

                override fun onError(utteranceId: String?) {
                    // Fallback to alarm tone on TTS speech failure
                    runOnUiThread {
                        startLoopingTone()
                    }
                }
            })

            speakAlarmMessage(message)
        } else {
            // TTS engine not installed or failed -> NEVER CRASH! Fall back to alarm tone
            startLoopingTone()
        }
    }

    private fun speakAlarmMessage(message: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            tts?.speak(message, TextToSpeech.QUEUE_FLUSH, null, "sinbha_alarm_utterance")
        } else {
            @Suppress("DEPRECATION")
            tts?.speak(message, TextToSpeech.QUEUE_FLUSH, null)
        }
    }

    private fun startCustomSongOrFallback() {
        if (!customSongUri.isNullOrEmpty()) {
            try {
                val songUri = Uri.parse(customSongUri)
                mediaPlayer = MediaPlayer().apply {
                    setDataSource(this@AlarmActivity, songUri)
                    setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                            .build()
                    )
                    isLooping = true
                    prepare()
                    setVolume(currentVolume, currentVolume)
                    start()
                }
                startGradualVolumeRamp()
                return
            } catch (e: Exception) {
                // If song URI is unreadable, fall back to alarm tone
            }
        }
        startLoopingTone()
    }

    private fun startLoopingTone() {
        if (mediaPlayer?.isPlaying == true) return
        try {
            val alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

            mediaPlayer = MediaPlayer().apply {
                setDataSource(this@AlarmActivity, alarmUri)
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                isLooping = true
                prepare()
                setVolume(currentVolume, currentVolume)
                start()
            }
            startGradualVolumeRamp()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun startGradualVolumeRamp() {
        volumeHandler.post(object : Runnable {
            override fun run() {
                if (!isAlarmActive) return
                if (currentVolume < 1.0f) {
                    currentVolume = (currentVolume + 0.10f).coerceAtMost(1.0f)
                    mediaPlayer?.setVolume(currentVolume, currentVolume)
                    volumeHandler.postDelayed(this, 2000)
                }
            }
        })
    }

    private fun startLoopingVibration() {
        try {
            val pattern = longArrayOf(0, 800, 400, 800, 400, 800)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vibrator = vm?.defaultVibrator
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 1))
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                @Suppress("DEPRECATION")
                vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 1))
            } else {
                @Suppress("DEPRECATION")
                vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, 1)
            }
        } catch (e: Exception) {}
    }

    private fun stopAllAlerts() {
        isAlarmActive = false
        volumeHandler.removeCallbacksAndMessages(null)

        try {
            tts?.stop()
            tts?.shutdown()
            tts = null
        } catch (e: Exception) {}

        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
            mediaPlayer = null
        } catch (e: Exception) {}

        try {
            vibrator?.cancel()
        } catch (e: Exception) {}

        // Clear notification if showing
        try {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (taskId > 0) {
                nm.cancel(taskId)
            }
        } catch (e: Exception) {}
    }

    private fun handleDismiss() {
        stopAllAlerts()
        if (taskId > 0) {
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val client = SinbhaApiClient(this@AlarmActivity)
                    client.markTaskDone(taskId)
                } catch (e: Exception) {}
            }
        }
        finish()
    }

    private fun handleSnooze(minutes: Int) {
        stopAllAlerts()
        if (taskId > 0) {
            val nextMillis = System.currentTimeMillis() + (minutes * 60 * 1000L)
            AlarmScheduler.addOrUpdateCachedReminder(
                context = this,
                taskId = taskId,
                taskTitle = taskTitle,
                label = "Snoozed $minutes min",
                reminderId = "snooze_$taskId",
                triggerAtMillis = nextMillis,
                soundMode = soundMode,
                customSongUri = customSongUri,
                userName = userName,
                speechText = speechText
            )
            AlarmScheduler.scheduleExactAlarm(
                context = this,
                taskId = taskId,
                taskTitle = taskTitle,
                dueText = "Snoozed $minutes min",
                reminderId = "snooze_$taskId",
                triggerAtMillis = nextMillis,
                soundMode = soundMode,
                customSongUri = customSongUri,
                userName = userName,
                speechText = speechText
            )

            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val client = SinbhaApiClient(this@AlarmActivity)
                    client.snoozeReminder(taskId, minutes)
                } catch (e: Exception) {}
            }
        }
        finish()
    }

    override fun onDestroy() {
        stopAllAlerts()
        super.onDestroy()
    }
}
