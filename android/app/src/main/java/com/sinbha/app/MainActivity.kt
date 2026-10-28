package com.sinbha.app

import android.content.Intent
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.getcapacitor.BridgeActivity
import com.getcapacitor.JSObject

class MainActivity : BridgeActivity() {

    companion object {
        const val TRUSTED_HOST = "sinbha-backend.onrender.com"
        const val FALLBACK_URL = "file:///android_asset/public/index.html"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // Register our custom native plugin before super.onCreate
        registerPlugin(SinbhaPlugin::class.java)
        super.onCreate(savedInstanceState)

        try {
            SinbhaCompanionService.start(this)
        } catch (e: Exception) {}

        // Security Requirement 6: Disable WebView remote debugging in production release builds
        if (!BuildConfig.DEBUG) {
            WebView.setWebContentsDebuggingEnabled(false)
        }

        // Configure WebView security & error recovery
        bridge?.webView?.let { webView ->
            webView.setDownloadListener { url, _, _, _, _ ->
                try {
                    val downloadIntent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(downloadIntent)
                } catch (e: Exception) {}
            }

            val existingClient = webView.webViewClient
            webView.webViewClient = object : WebViewClient() {

                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    val url = request?.url ?: return false
                    val host = url.host ?: ""
                    val urlString = url.toString()

                    if (urlString.endsWith(".apk") || host.contains("github.com")) {
                        try {
                            val externalIntent = Intent(Intent.ACTION_VIEW, url).apply {
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            startActivity(externalIntent)
                            return true
                        } catch (e: Exception) {}
                    }

                    // Restrict navigation strictly to our domain or local assets
                    if (host == TRUSTED_HOST || url.scheme == "file" || url.scheme == "capacitor") {
                        return false // Allow WebView to load
                    }

                    // Handle intent: URIs (e.g. intent:#Intent;package=com.whatsapp...)
                    if (url.scheme == "intent") {
                        try {
                            val parsed = Intent.parseUri(url.toString(), Intent.URI_INTENT_SCHEME).apply {
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            startActivity(parsed)
                            return true
                        } catch (e: Exception) {}
                    }

                    // Open any external URLs safely in external browser
                    try {
                        val externalIntent = Intent(Intent.ACTION_VIEW, url).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        startActivity(externalIntent)
                    } catch (e: Exception) {}
                    return true
                }

                override fun onReceivedError(
                    view: WebView?,
                    request: WebResourceRequest?,
                    error: WebResourceError?
                ) {
                    super.onReceivedError(view, request, error)
                    // If main page fails to load (e.g. cold start / offline), load friendly waking page
                    if (request?.isForMainFrame == true) {
                        view?.loadUrl(FALLBACK_URL)
                    }
                }
            }
        }

        handleTaskIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleTaskIntent(intent)
    }

    private fun handleTaskIntent(intent: Intent?) {
        val taskId = intent?.getIntExtra("open_task_id", -1) ?: -1
        if (taskId > 0) {
            val eventData = JSObject().apply {
                put("taskId", taskId)
            }
            bridge?.triggerWindowJSEvent("sinbha:openTaskChat", eventData.toString())
        }
    }
}
