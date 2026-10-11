// ========================================================
// SINBHA Desktop Configuration
// Single source of truth for backend URL and desktop settings.
// ========================================================

module.exports = {
  // Hosted backend URL (change here if you ever update your domain)
  BACKEND_URL: 'https://sinbha-backend.onrender.com',

  // Application metadata
  APP_NAME: 'SINBHA',
  APP_ID: 'com.sinbha.desktop',

  // Reminder polling interval in seconds
  REMINDER_POLL_INTERVAL_SECONDS: 45,

  // Auto-updater check interval in milliseconds (4 hours)
  UPDATE_CHECK_INTERVAL_MS: 4 * 60 * 60 * 1000,

  // Version features for "What's New" popup
  WHATS_NEW: {
        '1.0.1': [
      '✨ Fixed natural language reminder parsing & regional date formats',
      '🕊️ Instant desktop bird flight notification on due tasks',
      '☁️ High-speed direct connection to Render cloud backend',
      '🔄 Automatic background updates & seamless upgrade delivery'
    ],
    '1.0.0': [
      '🌸 Initial desktop release connected to cloud backend',
      '🕊️ Transparent desktop bird companion with reminder flights',
      '💬 Instant AI chat with habit & task intelligence',
      '🔒 Secure cloud synchronization & zero-knowledge database storage',
      '⚡ Per-user silent install with automatic desktop shortcut'
    ]
  }
};
