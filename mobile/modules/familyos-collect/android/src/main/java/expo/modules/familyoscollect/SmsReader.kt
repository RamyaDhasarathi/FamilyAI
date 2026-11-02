package expo.modules.familyoscollect

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.Telephony
import android.util.Log
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val BACKFILL_MS = 5L * 24 * 60 * 60 * 1000

// Inbox SMS with every field the collector app read (Mobile-UI-Agent SmsSync.kt), one-time codes included -- the backend
// pulls the code out (familyos/collect/otp.py). Used by the app's "collect now" (FamilyosCollectModule.readSms) and by the
// live SMS service, which sends them itself (`sync`).
object SmsReader {
  fun read(context: Context, sinceMs: Long, limit: Int): List<Map<String, Any?>> {
    if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) return emptyList()
    val out = mutableListOf<Map<String, Any?>>()
    context.contentResolver.query(
      Telephony.Sms.Inbox.CONTENT_URI,
      arrayOf(Telephony.Sms._ID, Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE, Telephony.Sms.THREAD_ID,
        Telephony.Sms.DATE_SENT, Telephony.Sms.TYPE, Telephony.Sms.READ, Telephony.Sms.SEEN, Telephony.Sms.SUBJECT,
        Telephony.Sms.SERVICE_CENTER, Telephony.Sms.PERSON, Telephony.Sms.PROTOCOL),
      "${Telephony.Sms.DATE} > ?", arrayOf(sinceMs.toString()), "${Telephony.Sms.DATE} ASC"
    )?.use { c ->
      while (c.moveToNext() && out.size < limit) {
        out.add(mapOf(
          "id" to c.getLong(0).toString(), "sender" to (c.getString(1) ?: ""), "body" to (c.getString(2) ?: ""),
          "date" to c.getLong(3).toDouble(), "threadId" to c.getLong(4).toString(), "dateSent" to c.getLong(5).toDouble(),
          "type" to c.getInt(6), "read" to c.getInt(7), "seen" to c.getInt(8), "subject" to c.getString(9),
          "serviceCenter" to c.getString(10), "person" to c.getString(11), "protocol" to c.getInt(12)
        ))
      }
    }
    return out
  }

  /** Sends the SMS that arrived since the service's own mark; the mark moves only after the backend said yes. */
  @Synchronized
  fun sync(context: Context) {
    val base = CollectSession.base(context) ?: return
    val token = CollectSession.token(context) ?: return
    val since = CollectSession.mark(context, System.currentTimeMillis() - BACKFILL_MS)
    val items = read(context, since, 200)
    if (items.isEmpty()) return
    val body = JSONObject().put("items", JSONArray(items.map { JSONObject(it) }))
    try {
      val conn = (URL("$base/v1/collect/device/sms").openConnection() as HttpURLConnection).apply {
        requestMethod = "POST"
        connectTimeout = 15000
        readTimeout = 30000
        doOutput = true
        setRequestProperty("Content-Type", "application/json")
        setRequestProperty("Authorization", "Bearer $token")
      }
      conn.outputStream.use { it.write(body.toString().toByteArray()) }
      val code = conn.responseCode
      conn.disconnect()
      if (code in 200..299) CollectSession.setMark(context, items.maxOf { (it["date"] as Double).toLong() })
      else Log.w("FamilyOS.Sms", "sending SMS: HTTP $code")
    } catch (e: Exception) {
      Log.w("FamilyOS.Sms", "sending SMS failed: ${e.message}")
    }
  }
}
