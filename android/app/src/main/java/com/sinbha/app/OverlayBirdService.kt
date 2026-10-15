package com.sinbha.app

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Native Overlay Bird Foreground Service.
 * Displays a non-intrusive floating bird with wing-flap animation,
 * curved flight path, and reminder action card over other apps.
 *
 * Touch Pass-Through: The overlay window bounds tightly wrap ONLY the bird
 * and reminder card, ensuring all outside touches pass completely unblocked.
 */
class OverlayBirdService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private lateinit var windowManager: WindowManager
    private lateinit var prefs: PreferencesManager
    private lateinit var apiClient: SinbhaApiClient

    private var rootView: FrameLayout? = null
    private var birdImageView: ImageView? = null
    private var cardLayout: LinearLayout? = null
    private var windowParams: WindowManager.LayoutParams? = null

    private var flightAnimator: ValueAnimator? = null
    private var flapHandler: Handler? = null
    private var flapIndex = 0

    private val flapSprites = arrayOf(
        R.drawable.bird_wings_up,
        R.drawable.bird_glide,
        R.drawable.bird_wings_down,
        R.drawable.bird_glide
    )

    private var currentTaskId: Int = -1
    private var currentTaskTitle: String = "Reminder"
    private var currentDueText: String = "Due now 🌸"

    companion object {
        const val ACTION_SHOW_BIRD = "com.sinbha.app.ACTION_SHOW_BIRD"
        const val ACTION_DISMISS_BIRD = "com.sinbha.app.ACTION_DISMISS_BIRD"
        const val EXTRA_TASK_ID = "extra_task_id"
        const val EXTRA_TASK_TITLE = "extra_task_title"
        const val EXTRA_DUE_TEXT = "extra_due_text"
        private const val NOTIFICATION_CHANNEL_ID = "sinbha_overlay_service_channel"
        private const val NOTIFICATION_ID = 2001

        fun launch(context: Context, taskId: Int, title: String, dueText: String) {
            val intent = Intent(context, OverlayBirdService::class.java).apply {
                action = ACTION_SHOW_BIRD
                putExtra(EXTRA_TASK_ID, taskId)
                putExtra(EXTRA_TASK_TITLE, title)
                putExtra(EXTRA_DUE_TEXT, dueText)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        prefs = PreferencesManager(this)
        apiClient = SinbhaApiClient(this)
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildForegroundNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) return START_NOT_STICKY

        when (intent.action) {
            ACTION_DISMISS_BIRD -> {
                dismissBirdGracefully()
            }
            ACTION_SHOW_BIRD -> {
                currentTaskId = intent.getIntExtra(EXTRA_TASK_ID, -1)
                currentTaskTitle = intent.getStringExtra(EXTRA_TASK_TITLE) ?: "Reminder"
                currentDueText = intent.getStringExtra(EXTRA_DUE_TEXT) ?: "Due now 🌸"

                if (canDrawOverlays()) {
                    showOverlayBird()
                } else {
                    stopSelf()
                }
            }
        }
        return START_NOT_STICKY
    }

    private fun canDrawOverlays(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(this)
        } else {
            true
        }
    }

    private fun isReduceMotionEnabled(): Boolean {
        if (prefs.isReduceMotion) return true
        return try {
            val scale = Settings.Global.getFloat(
                contentResolver,
                Settings.Global.ANIMATOR_DURATION_SCALE,
                1.0f
            )
            scale == 0f
        } catch (e: Exception) {
            false
        }
    }

    private fun showOverlayBird() {
        removeOverlayView()

        val displayMetrics = DisplayMetrics()
        windowManager.defaultDisplay.getMetrics(displayMetrics)
        val screenWidth = displayMetrics.widthPixels
        val screenHeight = displayMetrics.heightPixels

        val layoutFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            WindowManager.LayoutParams.TYPE_PHONE
        }

        // Tightly bounds view to prevent blocking clicks anywhere else
        windowParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutFlag,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = -150
            y = (screenHeight * 0.25).toInt()
        }

        val container = FrameLayout(this)
        val density = resources.displayMetrics.density

        // Bird Sprite View
        val birdIv = ImageView(this).apply {
            id = View.generateViewId()
            setImageResource(R.drawable.bird_wings_up)
            layoutParams = FrameLayout.LayoutParams((72 * density).toInt(), (72 * density).toInt()).apply {
                gravity = Gravity.TOP or Gravity.START
            }
        }
        birdImageView = birdIv

        // Reminder Note Card
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 18 * density
                setColor(Color.WHITE)
                setStroke((1.5 * density).toInt(), Color.parseColor("#FCE7F3"))
            }
            background = bg
            setPadding((14 * density).toInt(), (10 * density).toInt(), (14 * density).toInt(), (10 * density).toInt())
            elevation = 16 * density
            alpha = 0f
            visibility = View.GONE

            layoutParams = FrameLayout.LayoutParams(
                (245 * density).toInt(),
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = (74 * density).toInt()
            }
        }
        cardLayout = card

        // Task Title
        val titleTv = TextView(this).apply {
            text = currentTaskTitle
            textSize = 14f
            setTextColor(Color.parseColor("#0F172A"))
            paint.isFakeBoldText = true
            maxLines = 2
        }
        card.addView(titleTv)

        // Due text
        val dueTv = TextView(this).apply {
            text = currentDueText
            textSize = 12f
            setTextColor(Color.parseColor("#EC4899"))
            setPadding(0, (2 * density).toInt(), 0, (6 * density).toInt())
        }
        card.addView(dueTv)

        // Action Buttons Row: Done, Snooze, Chat, Dismiss
        val actionsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val btnDone = createActionButton("✓ Done", "#10B981") {
            handleDoneAction()
        }
        val btnSnooze = createActionButton("⏰ Snooze ▾", "#F59E0B") {
            // Toggled below
        }
        val btnChat = createActionButton("💬 Chat", "#EC4899") {
            handleOpenChatAction()
        }
        val btnDismiss = createActionButton("✕", "#64748B") {
            dismissBirdGracefully()
        }

        actionsRow.addView(btnDone)
        actionsRow.addView(btnSnooze)
        actionsRow.addView(btnChat)
        actionsRow.addView(btnDismiss)
        card.addView(actionsRow)

        // Expandable Snooze Options Panel (1m, 2m, custom minutes)
        var selectedSnoozeMins = 2
        val snoozePanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            setPadding(0, (8 * density).toInt(), 0, 0)
        }

        val snoozeHeaderTv = TextView(this).apply {
            text = "⏰ Snooze for:"
            textSize = 11f
            setTextColor(Color.parseColor("#D97706"))
            paint.isFakeBoldText = true
            setPadding(0, 0, 0, (4 * density).toInt())
        }
        snoozePanel.addView(snoozeHeaderTv)

        // Preset Chips Row: 1m, 2m, 5m, 15m, 30m
        val quickChipsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, (6 * density).toInt())
        }

        val presets = listOf(1, 2, 5, 15, 30)
        for (mins in presets) {
            val chip = TextView(this).apply {
                text = "${mins}m"
                textSize = 11f
                setTextColor(Color.parseColor("#92400E"))
                paint.isFakeBoldText = true
                setPadding((7 * density).toInt(), (4 * density).toInt(), (7 * density).toInt(), (4 * density).toInt())
                background = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = 8 * density
                    setColor(Color.parseColor("#FEF3C7"))
                    setStroke((1 * density).toInt(), Color.parseColor("#FDE68A"))
                }
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    marginEnd = (5 * density).toInt()
                }
                setOnClickListener {
                    handleSnoozeAction(mins)
                }
            }
            quickChipsRow.addView(chip)
        }
        snoozePanel.addView(quickChipsRow)

        // Custom Stepper Row: [-] [ 2 min ] [+] [ Set ✓ ]
        val customStepperRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val customMinsTv = TextView(this).apply {
            text = "$selectedSnoozeMins min"
            textSize = 12f
            setTextColor(Color.parseColor("#0F172A"))
            paint.isFakeBoldText = true
            gravity = Gravity.CENTER
            setPadding((8 * density).toInt(), (2 * density).toInt(), (8 * density).toInt(), (2 * density).toInt())
        }

        val btnMinus = createSmallButton("－") {
            if (selectedSnoozeMins > 1) {
                selectedSnoozeMins--
                customMinsTv.text = "$selectedSnoozeMins min"
            }
        }

        val btnPlus = createSmallButton("＋") {
            if (selectedSnoozeMins < 1440) {
                selectedSnoozeMins++
                customMinsTv.text = "$selectedSnoozeMins min"
            }
        }

        val btnSetCustom = TextView(this).apply {
            text = "Set ✓"
            textSize = 11f
            setTextColor(Color.WHITE)
            paint.isFakeBoldText = true
            setPadding((10 * density).toInt(), (4 * density).toInt(), (10 * density).toInt(), (4 * density).toInt())
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 8 * density
                setColor(Color.parseColor("#F59E0B"))
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginStart = (6 * density).toInt()
            }
            setOnClickListener {
                handleSnoozeAction(selectedSnoozeMins)
            }
        }

        customStepperRow.addView(btnMinus)
        customStepperRow.addView(customMinsTv)
        customStepperRow.addView(btnPlus)
        customStepperRow.addView(btnSetCustom)
        snoozePanel.addView(customStepperRow)

        card.addView(snoozePanel)

        btnSnooze.setOnClickListener {
            snoozePanel.visibility = if (snoozePanel.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        container.addView(card)
        container.addView(birdIv)
        rootView = container

        try {
            windowManager.addView(container, windowParams)
        } catch (e: Exception) {
            e.printStackTrace()
            stopSelf()
            return
        }

        // Draggable gesture on bird
        setupDragListener(birdIv)

        // Wing flapping timer
        startFlappingAnimation()

        // Flight trajectory animation
        if (isReduceMotionEnabled()) {
            // Resting position with gentle fade-in
            windowParams?.x = (screenWidth - (250 * density)).toInt().coerceAtLeast(30)
            windowParams?.y = (screenHeight * 0.22).toInt()
            windowManager.updateViewLayout(container, windowParams)
            birdIv.setImageResource(R.drawable.bird_landed)
            card.visibility = View.VISIBLE
            card.alpha = 1f
        } else {
            startCurvedFlightAnimation(screenWidth, screenHeight, density)
        }
    }

    private fun createActionButton(label: String, colorHex: String, onClick: () -> Unit): TextView {
        val density = resources.displayMetrics.density
        return TextView(this).apply {
            text = label
            textSize = 11f
            setTextColor(Color.WHITE)
            paint.isFakeBoldText = true
            setPadding((8 * density).toInt(), (5 * density).toInt(), (8 * density).toInt(), (5 * density).toInt())
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 10 * density
                setColor(Color.parseColor(colorHex))
            }
            background = bg
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = (6 * density).toInt()
            }
            setOnClickListener { onClick() }
        }
    }

    private fun createSmallButton(symbol: String, onClick: () -> Unit): TextView {
        val density = resources.displayMetrics.density
        return TextView(this).apply {
            text = symbol
            textSize = 13f
            setTextColor(Color.parseColor("#475569"))
            paint.isFakeBoldText = true
            gravity = Gravity.CENTER
            setPadding((8 * density).toInt(), (2 * density).toInt(), (8 * density).toInt(), (2 * density).toInt())
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 6 * density
                setColor(Color.parseColor("#F1F5F9"))
                setStroke((1 * density).toInt(), Color.parseColor("#CBD5E1"))
            }
            background = bg
            setOnClickListener { onClick() }
        }
    }

    private fun setupDragListener(view: View) {
        var initialX = 0
        var initialY = 0
        var touchX = 0f
        var touchY = 0f

        view.setOnTouchListener { _, event ->
            val params = windowParams ?: return@setOnTouchListener false
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    touchX = event.rawX
                    touchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = initialX + (event.rawX - touchX).toInt()
                    params.y = initialY + (event.rawY - touchY).toInt()
                    try {
                        rootView?.let { windowManager.updateViewLayout(it, params) }
                    } catch (e: Exception) {}
                    true
                }
                else -> false
            }
        }
    }

    private fun startFlappingAnimation() {
        flapHandler = Handler(Looper.getMainLooper())
        val flapRunnable = object : Runnable {
            override fun run() {
                birdImageView?.let { iv ->
                    iv.setImageResource(flapSprites[flapIndex % flapSprites.size])
                    flapIndex++
                }
                flapHandler?.postDelayed(this, 130)
            }
        }
        flapHandler?.post(flapRunnable)
    }

    private fun stopFlappingAnimation() {
        flapHandler?.removeCallbacksAndMessages(null)
        flapHandler = null
    }

    private fun startCurvedFlightAnimation(screenWidth: Int, screenHeight: Int, density: Float) {
        val startX = -120f
        val startY = (screenHeight * 0.40).toFloat()
        val targetX = (screenWidth - (250 * density)).coerceAtLeast(30f)
        val targetY = (screenHeight * 0.22).toFloat()
        val controlY = (screenHeight * 0.12).toFloat()

        flightAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 2400
            interpolator = DecelerateInterpolator()
            addUpdateListener { animator ->
                val t = animator.animatedValue as Float
                // Quadratic Bezier Curve for smooth curved swoop
                val currentX = (1 - t) * (1 - t) * startX + 2 * (1 - t) * t * (screenWidth * 0.4f) + t * t * targetX
                val currentY = (1 - t) * (1 - t) * startY + 2 * (1 - t) * t * controlY + t * t * targetY

                windowParams?.let { params ->
                    params.x = currentX.toInt()
                    params.y = currentY.toInt()
                    try {
                        rootView?.let { windowManager.updateViewLayout(it, params) }
                    } catch (e: Exception) {}
                }
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    stopFlappingAnimation()
                    birdImageView?.setImageResource(R.drawable.bird_landed)
                    // Reveal reminder card
                    cardLayout?.let { card ->
                        card.visibility = View.VISIBLE
                        card.animate().alpha(1f).setDuration(300).start()
                    }
                }
            })
            start()
        }
    }

    private fun handleDoneAction() {
        if (currentTaskId > 0) {
            serviceScope.launch {
                apiClient.markTaskDone(currentTaskId)
            }
        }
        dismissBirdGracefully()
    }

    private fun handleSnoozeAction(minutes: Int = 15) {
        if (currentTaskId > 0) {
            val triggerAtMillis = System.currentTimeMillis() + minutes * 60 * 1000L
            val snoozeRemId = "snooze_$currentTaskId"
            val dueLabel = "Snoozed (${minutes}m)"

            AlarmScheduler.scheduleExactAlarm(
                this,
                currentTaskId,
                currentTaskTitle,
                dueLabel,
                snoozeRemId,
                triggerAtMillis
            )
            AlarmScheduler.addOrUpdateCachedReminder(
                this,
                currentTaskId,
                currentTaskTitle,
                dueLabel,
                snoozeRemId,
                triggerAtMillis
            )

            serviceScope.launch {
                apiClient.snoozeReminder(currentTaskId, minutes)
            }
        }
        dismissBirdGracefully()
    }

    private fun handleOpenChatAction() {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("open_task_id", currentTaskId)
        }
        if (launchIntent != null) {
            startActivity(launchIntent)
        }
        dismissBirdGracefully()
    }

    private fun dismissBirdGracefully() {
        cardLayout?.animate()?.alpha(0f)?.setDuration(200)?.start()
        startFlappingAnimation()

        val params = windowParams
        val currentX = params?.x?.toFloat() ?: 0f
        val currentY = params?.y?.toFloat() ?: 0f

        val displayMetrics = resources.displayMetrics
        val exitTargetX = (displayMetrics.widthPixels + 150).toFloat()

        flightAnimator?.cancel()
        flightAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1000
            addUpdateListener { anim ->
                val t = anim.animatedValue as Float
                params?.let { p ->
                    p.x = (currentX + t * (exitTargetX - currentX)).toInt()
                    p.y = (currentY - t * 150).toInt()
                    try {
                        rootView?.let { windowManager.updateViewLayout(it, p) }
                    } catch (e: Exception) {}
                }
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    removeOverlayView()
                    stopSelf()
                }
            })
            start()
        }
    }

    private fun removeOverlayView() {
        stopFlappingAnimation()
        flightAnimator?.cancel()
        if (rootView != null) {
            try {
                windowManager.removeView(rootView)
            } catch (e: Exception) {}
            rootView = null
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "SINBHA Companion Overlay",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps active companion bird visible over apps"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildForegroundNotification(): Notification {
        val dismissIntent = Intent(this, OverlayBirdService::class.java).apply {
            action = ACTION_DISMISS_BIRD
        }
        val pDismiss = PendingIntent.getService(
            this,
            0,
            dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("SINBHA Companion Active")
            .setContentText("Tap to dismiss companion bird")
            .setSmallIcon(R.drawable.ic_sinbha)
            .setContentIntent(pDismiss)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        removeOverlayView()
        serviceScope.cancel()
    }
}
