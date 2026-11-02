package expo.modules.familyoscollect

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.database.ContentObserver
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.provider.Telephony
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

private const val CHANNEL_ID = "familyos_collect_live"
private const val NOTIFICATION_ID = 4711

// Live SMS (ported from Mobile-UI-Agent's CollectorForegroundService.kt): a foreground service that watches the SMS
// provider and sends each new SMS to FamilyOS within seconds -- so a one-time code reaches the browser agent while it
// waits -- instead of at the next 15-minute run. Its notification says so, always. "Special use" type: on Android 14+ a
// data-sync service is capped at 6 hours a day and may not start at boot. Started when SMS is switched on in Data
// sources (and at boot, by CollectBootReceiver); stopped when SMS is switched off or the member signs out.
class CollectSmsService : Service() {
  private var thread: HandlerThread? = null
  private var observer: ContentObserver? = null

  companion object {
    fun start(context: Context) {
      ContextCompat.startForegroundService(context, Intent(context, CollectSmsService::class.java))
    }

    fun stop(context: Context) {
      context.stopService(Intent(context, CollectSmsService::class.java))
    }

    @Volatile var running = false
      private set
  }

  override fun onCreate() {
    super.onCreate()
    val t = HandlerThread("FamilyOS.LiveSms").apply { start() }
    thread = t
    val handler = Handler(t.looper)
    val o = object : ContentObserver(handler) {
      override fun onChange(selfChange: Boolean) {
        SmsReader.sync(applicationContext)
      }
    }
    observer = o
    contentResolver.registerContentObserver(Telephony.Sms.CONTENT_URI, true, o)
    handler.post { SmsReader.sync(applicationContext) }          // catch up at once
    running = true
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      getSystemService(NotificationManager::class.java)?.createNotificationChannel(
        NotificationChannel(CHANNEL_ID, "FamilyOS live SMS", NotificationManager.IMPORTANCE_LOW))
    }
    val notification = NotificationCompat.Builder(this, CHANNEL_ID)
      .setContentTitle("FamilyOS")
      .setContentText("Collecting new SMS as they arrive")
      .setSmallIcon(android.R.drawable.stat_notify_sync)
      .setOngoing(true)
      .build()
    val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
    ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
    return START_STICKY
  }

  override fun onDestroy() {
    observer?.let { contentResolver.unregisterContentObserver(it) }
    thread?.quitSafely()
    running = false
    super.onDestroy()
  }

  override fun onBind(intent: Intent?): IBinder? = null
}
