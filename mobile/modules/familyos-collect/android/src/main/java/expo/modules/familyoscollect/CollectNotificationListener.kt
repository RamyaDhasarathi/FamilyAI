package expo.modules.familyoscollect

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

// Notifications from other apps, as they arrive (Mobile-UI-Agent CollectorNotificationListenerService.kt). Kept in a
// small on-phone buffer (the newest 500) until the app takes them (FamilyosCollectModule.drainNotifications) and sends
// them to the backend, which keeps only those from apps the person switched on. Android shows this as FamilyOS under
// Settings → Notification access, and runs it only once the person allows it there.
class CollectNotificationListener : NotificationListenerService() {
  companion object {
    const val PREFS = "familyos_collect"
    const val KEY = "notifications"
    private const val MAX = 500
  }

  override fun onNotificationPosted(sbn: StatusBarNotification) {
    if (sbn.packageName == applicationContext.packageName) return
    val extras = sbn.notification.extras
    val item = JSONObject()
      .put("package", sbn.packageName)
      .put("title", extras.getCharSequence("android.title")?.toString() ?: "")
      .put("text", extras.getCharSequence("android.text")?.toString() ?: "")
      .put("postTime", sbn.postTime)
    synchronized(CollectNotificationListener::class.java) {
      val prefs = applicationContext.getSharedPreferences(PREFS, MODE_PRIVATE)
      val arr = JSONArray(prefs.getString(KEY, "[]"))
      arr.put(item)
      val kept = JSONArray()
      for (i in maxOf(0, arr.length() - MAX) until arr.length()) kept.put(arr.get(i))
      prefs.edit().putString(KEY, kept.toString()).apply()
    }
  }
}
