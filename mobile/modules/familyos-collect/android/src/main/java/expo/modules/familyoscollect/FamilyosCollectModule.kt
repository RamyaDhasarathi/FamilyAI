package expo.modules.familyoscollect

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.provider.CallLog
import android.provider.MediaStore
import android.provider.Settings
import androidx.core.content.ContextCompat
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONArray
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

// FamilyOS collecting layer on Android (famos-notes/COLLECTION_PLAN.md). Reads what the person switched on, in the
// shapes the user's own collector app sent (Mobile-UI-Agent KT/collector/*): the app's JS sends them to our backend
// (/v1/collect/device/…), which keeps them in its local cache. Nothing here stores or sends anything itself, except the
// notification listener's small on-phone buffer (CollectNotificationListener). A source without its permission
// answers an empty list, never an error, so one refusal never stops the others.
class FamilyosCollectModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  // Waits are native: React Native pauses JS timers while FamilyOS is in the background, which is exactly when the phone
  // agent works in another app (Mobile-UI-Agent AgentModule.settle).
  private val waits = Executors.newSingleThreadScheduledExecutor()

  private fun allowed(permission: String) =
    ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

  override fun definition() = ModuleDefinition {
    Name("FamilyosCollect")

    // The apps a person can open: package and name (Mobile-UI-Agent AgentModule.getInstalledApps).
    AsyncFunction("listApps") {
      val pm = context.packageManager
      val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
      pm.queryIntentActivities(launcher, 0)
        .map { it.activityInfo.packageName to it.loadLabel(pm).toString() }
        .filter { it.first != context.packageName }
        .distinctBy { it.first }
        .sortedBy { it.second.lowercase() }
        .map { mapOf("package" to it.first, "label" to it.second) }
    }

    // Inbox SMS newer than `sinceMs`, oldest first (Mobile-UI-Agent SmsSync.kt).
    AsyncFunction("readSms") { sinceMs: Double, limit: Int ->
      SmsReader.read(context, sinceMs.toLong(), limit)
    }

    // Live SMS (CollectSmsService): the session it sends with, and on / off.
    Function("setSession") { baseUrl: String, token: String ->
      CollectSession.set(context, baseUrl, token)
    }

    Function("clearSession") {
      CollectSession.clear(context)
      CollectSmsService.stop(context)
    }

    Function("startLiveSms") {
      with(CollectSession) { context.liveSms = true }
      CollectSmsService.start(context)
    }

    Function("stopLiveSms") {
      with(CollectSession) { context.liveSms = false }
      CollectSmsService.stop(context)
    }

    Function("liveSmsRunning") {
      CollectSmsService.running
    }

    // Calls newer than `sinceMs`: number, direction, start, seconds (Mobile-UI-Agent CallLogSyncWorker.kt).
    AsyncFunction("readCallLog") { sinceMs: Double, limit: Int ->
      if (!allowed(Manifest.permission.READ_CALL_LOG)) return@AsyncFunction emptyList<Map<String, Any?>>()
      val out = mutableListOf<Map<String, Any?>>()
      context.contentResolver.query(
        CallLog.Calls.CONTENT_URI,
        arrayOf(CallLog.Calls.NUMBER, CallLog.Calls.TYPE, CallLog.Calls.DATE, CallLog.Calls.DURATION),
        "${CallLog.Calls.DATE} > ?", arrayOf(sinceMs.toLong().toString()), "${CallLog.Calls.DATE} ASC"
      )?.use { c ->
        while (c.moveToNext() && out.size < limit) {
          val kind = when (c.getInt(1)) {
            CallLog.Calls.INCOMING_TYPE -> "incoming"
            CallLog.Calls.OUTGOING_TYPE -> "outgoing"
            CallLog.Calls.MISSED_TYPE -> "missed"
            else -> "other"
          }
          out.add(mapOf("number" to (c.getString(0) ?: ""), "type" to kind, "date" to c.getLong(2).toDouble(),
                        "duration" to c.getLong(3).toDouble()))
        }
      }
      out
    }

    // The newest fix Android already holds, GPS or network; no fresh fix is asked for (Mobile-UI-Agent LocationSyncWorker.kt).
    AsyncFunction("lastLocation") {
      if (!allowed(Manifest.permission.ACCESS_FINE_LOCATION) && !allowed(Manifest.permission.ACCESS_COARSE_LOCATION)) {
        return@AsyncFunction null
      }
      val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
      val best = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
        .mapNotNull { p -> try { lm.getLastKnownLocation(p) } catch (_: SecurityException) { null } }
        .maxByOrNull { it.time } ?: return@AsyncFunction null
      mapOf("lat" to best.latitude, "lng" to best.longitude, "accuracy" to best.accuracy.toDouble(), "time" to best.time.toDouble())
    }

    // Photos added since `sinceSeconds`: name, size and type only, never the picture (Mobile-UI-Agent FileSyncWorker.kt).
    AsyncFunction("recentPhotos") { sinceSeconds: Double, limit: Int ->
      val perm = if (android.os.Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE
      if (!allowed(perm)) return@AsyncFunction emptyList<Map<String, Any?>>()
      val out = mutableListOf<Map<String, Any?>>()
      context.contentResolver.query(
        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
        arrayOf(MediaStore.Images.Media._ID, MediaStore.Images.Media.DISPLAY_NAME, MediaStore.Images.Media.SIZE,
                MediaStore.Images.Media.MIME_TYPE, MediaStore.Images.Media.DATE_ADDED),
        "${MediaStore.Images.Media.DATE_ADDED} > ?", arrayOf(sinceSeconds.toLong().toString()),
        "${MediaStore.Images.Media.DATE_ADDED} ASC"
      )?.use { c ->
        while (c.moveToNext() && out.size < limit) {
          out.add(mapOf("id" to c.getLong(0).toString(), "name" to (c.getString(1) ?: ""), "size" to c.getLong(2).toDouble(),
                        "mimeType" to (c.getString(3) ?: ""), "date" to c.getLong(4).toDouble()))
        }
      }
      out
    }

    // Whether the person has allowed FamilyOS in Settings → Notification access.
    Function("notificationAccess") {
      val enabled = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: ""
      val me = ComponentName(context, CollectNotificationListener::class.java).flattenToString()
      enabled.split(":").any { it == me }
    }

    Function("openNotificationAccessSettings") {
      context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    // Take what the listener buffered since the last call (it then starts empty again).
    Function("drainNotifications") {
      val prefs = context.getSharedPreferences(CollectNotificationListener.PREFS, Context.MODE_PRIVATE)
      val raw = prefs.getString(CollectNotificationListener.KEY, "[]") ?: "[]"
      prefs.edit().putString(CollectNotificationListener.KEY, "[]").apply()
      val arr = JSONArray(raw)
      (0 until arr.length()).map { i ->
        val o = arr.getJSONObject(i)
        mapOf("package" to o.optString("package"), "title" to o.optString("title"), "text" to o.optString("text"),
              "postTime" to o.optDouble("postTime"))
      }
    }

    // ── The phone agent (FamilyosAgentService.kt; the loop is services/phoneAgent.ts) ──────────────────────

    // Allowed under Settings → Accessibility, and connected.
    Function("agentAccess") {
      val enabled = Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
      val me = ComponentName(context, FamilyosAgentService::class.java).flattenToString()
      enabled.split(":").any { it.equals(me, ignoreCase = true) } && FamilyosAgentService.instance != null
    }

    Function("openAccessibilitySettings") {
      context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    // What the screen shows: the app, its elements, a small screenshot (or "" when the phone gives none), the size.
    AsyncFunction("observe") { promise: Promise ->
      val agent = FamilyosAgentService.instance
      if (agent == null) {
        promise.reject("NO_AGENT", "Allow FamilyOS phone agent under Settings → Accessibility first", null)
        return@AsyncFunction
      }
      val app = agent.currentPackage()
      val tree = agent.tree()
      val (w, h) = agent.screenSize()
      agent.screenshot { shot ->
        promise.resolve(mapOf("currentApp" to app, "tree" to tree, "screenshot" to (shot ?: ""), "width" to w, "height" to h))
      }
    }

    // One action, as the backend gave it (phone_agent.py valid_action): true when the phone did it.
    AsyncFunction("act") { action: Map<String, Any?>, promise: Promise ->
      val agent = FamilyosAgentService.instance
      if (agent == null) {
        promise.reject("NO_AGENT", "the phone agent is not allowed under Accessibility", null)
        return@AsyncFunction
      }
      val (w, h) = agent.screenSize()
      @Suppress("UNCHECKED_CAST")
      val target = action["target"] as? Map<String, Any?>
      @Suppress("UNCHECKED_CAST")
      val point = target?.get("point") as? Map<String, Any?>
      val x = (point?.get("x") as? Number)?.toFloat()?.times(w)
      val y = (point?.get("y") as? Number)?.toFloat()?.times(h)
      val done = when (action["action"]) {
        "tap" -> agent.tap(target?.get("description") as? String ?: "", x, y, long = false)
        "long_press" -> agent.tap(target?.get("description") as? String ?: "", x, y, long = true)
        "type" -> agent.type(action["text"] as? String ?: "")
        "swipe" -> agent.swipe(action["direction"] as? String ?: "up")
        "press_back" -> agent.back()
        "press_home" -> agent.home()
        "launch_app" -> context.packageManager.getLaunchIntentForPackage(action["package"] as? String ?: "")
          ?.let { agent.start(it) } ?: false
        "wait" -> {
          waits.schedule({ promise.resolve(true) }, 1500, TimeUnit.MILLISECONDS)
          return@AsyncFunction
        }
        "done" -> true
        else -> false
      }
      promise.resolve(done)
    }

    AsyncFunction("settle") { ms: Double, promise: Promise ->
      waits.schedule({ promise.resolve(null) }, ms.toLong(), TimeUnit.MILLISECONDS)
    }

    // Back to FamilyOS when a run ends (started from the service, which Android allows from the background).
    Function("bringToFront") {
      val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
      if (intent != null) {
        intent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        FamilyosAgentService.instance?.start(intent) ?: context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
      }
    }
  }
}
