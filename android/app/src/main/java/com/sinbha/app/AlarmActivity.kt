package com.sinbha.app

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.Locale
import java.util.Timer
import java.util.TimerTask

/**
 * Full-screen clock-app alarm experience.
 * Wakes the screen, shows above the lockscreen, loops audio on STREAM_ALARM
 * with gradually rising volume and vibration, supports custom songs,
 * Android Text-to-Speech voice, or voice then tone.
 */
class AlarmActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private var taskId: Int = -1
    private var taskTitle: String = "Task Reminder"
    private var dueText: String = "Due now"
    private var soundOption: String = "voice_then_tone"
    private var songUriStr: String? = null
    private var userName: String = "friend"
    private var spokenText: String = ""

    private var mediaPlayer: MediaPlayer? = null
    private var vibrator: Vibrator? = null
    private var textToSpeech: TextToSpeech? = null
    private var volumeTimer: Timer? = null
    private var isDismissedOrSnoozed = false
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = PreferencesManager(this)
        if (prefs.isEmergencyStopped) {
            finish()
            return
        }

        // Configure full screen & screen wake above lockscreen
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

        setContentView(R.layout.activity_alarm)

        taskId = intent.getIntExtra(AlarmScheduler.EXTRA_TASK_ID, -1)
        taskTitle = intent.getStringExtra(AlarmScheduler.EXTRA_TASK_TITLE) ?: "Task Reminder"
        dueText = intent.getStringExtra(AlarmScheduler.EXTRA_DUE_TEXT) ?: "Due now"
        soundOption = intent.getStringExtra(AlarmScheduler.EXTRA_SOUND_OPTION) ?: "voice_then_tone"
        songUriStr = intent.getStringExtra(AlarmScheduler.EXTRA_SONG_URI)
        userName = intent.getStringExtra(AlarmScheduler.EXTRA_USER_NAME) ?: "friend"
        spokenText = intent.getStringExtra(AlarmScheduler.EXTRA_SPOKEN_TEXT)
            ?: "Hey $userName, it is time to $taskTitle"

        findViewById<TextView>(R.id.alarmTaskTitle).text = taskTitle
        findViewById<TextView>(R.id.alarmSpokenText).text = spokenText
        findViewById<TextView>(R.id.alarmDueText).text = dueText

        findViewById<Button>(R.id.btnDismissAlarm).setOnClickListener {
            handleDismiss()
        }

        findViewById<Button>(R.id.btnSnoozeAlarm).setOnClickListener {
            handleSnooze()
        }

        startVibration()

        // Initialize Audio or TTS according to soundOption
        when (soundOption) {
            "tts_voice", "voice_then_tone" -> {
                initTTS()
            }
            "custom_song" -> {
                playCustomSongOrFallback()
            }
            else -> {
                playAlarmTone()
            }
        }
    }

    private fun initTTS() {
        try {
            textToSpeech = TextToSpeech(this, this)
        } catch (e: Exception) {
            // Never crash if TTS is unavailable; seamlessly fall back to alarm tone
            playAlarmTone()
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS && textToSpeech != null) {
            try {
                textToSpeech?.language = Locale.getDefault()
                val audioAttributes = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
                textToSpeech?.setAudioAttributes(audioAttributes)

                textToSpeech?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) {
                        if (!isDismissedOrSnoozed) {
                            mainHandler.post {
                                if (soundOption == "voice_then_tone") {
                                    playAlarmTone()
                                } else if (soundOption == "tts_voice") {
                                    // Repeat spoken voice after 3-second delay
                                    mainHandler.postDelayed({
                                        if (!isDismissedOrSnoozed) {
                                            speakMessage()
                                        }
                                    }, 3000L)
                                }
                            }
                        }
                    }
                    override fun onError(utteranceId: String?) {
                        mainHandler.post { playAlarmTone() }
                    }
                })

                speakMessage()
            } catch (e: Exception) {
                playAlarmTone()
            }
        } else {
            playAlarmTone()
        }
    }

    private fun speakMessage() {
        if (isDismissedOrSnoozed) return
        try {
            val params = Bundle().apply {
                putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, android.media.AudioManager.STREAM_ALARM)
                putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
            }
            textToSpeech?.speak(spokenText, TextToSpeech.QUEUE_FLUSH, params, "alarm_spoken_utterance")
        } catch (e: Exception) {
            playAlarmTone()
        }
    }

    private fun playCustomSongOrFallback() {
        if (!songUriStr.isNullOrEmpty()) {
            try {
                val songUri = Uri.parse(songUriStr)
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
                    start()
                }
                startGradualVolumeRise()
                return
            } catch (e: Exception) {
                // Song file moved or unreadable: fallback to standard alarm tone
            }
        }
        playAlarmTone()
    }

    private fun playAlarmTone() {
        if (isDismissedOrSnoozed || mediaPlayer?.isPlaying == true) return
        try {
            val alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)

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
                start()
            }
            startGradualVolumeRise()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun startGradualVolumeRise() {
        volumeTimer?.cancel()
        var currentVol = 0.1f
        mediaPlayer?.setVolume(currentVol, currentVol)

        volumeTimer = Timer().apply {
            scheduleAtFixedRate(object : TimerTask() {
                override fun run() {
                    currentVol += 0.05f
                    if (currentVol >= 1.0f) {
                        currentVol = 1.0f
                        cancel()
                    }
                    mainHandler.post {
                        try {
                            mediaPlayer?.setVolume(currentVol, currentVol)
                        } catch (e: Exception) {}
                    }
                }
            }, 1000L, 1000L)
        }
    }

    private fun startVibration() {
        try {
            @Suppress("DEPRECATION")
            vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            val pattern = longArrayOf(0, 1000, 500, 1000, 500)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 0))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, 0)
            }
        } catch (e: Exception) {}
    }

    private fun stopAllAlerts() {
        isDismissedOrSnoozed = true
        volumeTimer?.cancel()
        volumeTimer = null

        try {
            if (textToSpeech?.isSpeaking == true) {
                textToSpeech?.stop()
            }
            textToSpeech?.shutdown()
            textToSpeech = null
        } catch (e: Exception) {}

        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
            mediaPlayer = null
        } catch (e: Exception) {}

        try {
            vibrator?.cancel()
            vibrator = null
        } catch (e: Exception) {}
    }

    private fun handleDismiss() {
        stopAllAlerts()
        if (taskId > 0) {
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val client = SinbhaApiClient(applicationContext)
                    client.markTaskDone(taskId)
                } catch (e: Exception) {}
            }
        }
        finish()
    }

    private fun handleSnooze() {
        stopAllAlerts()
        val snoozeMinutes = 10
        if (taskId > 0) {
            val snoozeMillis = System.currentTimeMillis() + (snoozeMinutes * 60 * 1000L)
            AlarmScheduler.scheduleExactAlarm(
                context = applicationContext,
                taskId = taskId,
                taskTitle = taskTitle,
                dueText = "Snoozed (+${snoozeMinutes}m)",
                reminderId = "snooze_$taskId",
                triggerAtMillis = snoozeMillis,
                soundOption = soundOption,
                songUri = songUriStr,
                userName = userName,
                spokenText = spokenText
            )

            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val client = SinbhaApiClient(applicationContext)
                    client.snoozeTask(taskId, snoozeMinutes)
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
