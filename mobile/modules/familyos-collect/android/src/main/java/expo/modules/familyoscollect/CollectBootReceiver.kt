package expo.modules.familyoscollect

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import expo.modules.familyoscollect.CollectSession.liveSms

// After the phone restarts, live SMS starts again by itself if it was on (Mobile-UI-Agent BootReceiver.kt). The 15-minute
// background collection (WorkManager) survives a restart on its own.
class CollectBootReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent) {
    val action = intent.action ?: return
    // Not LOCKED_BOOT_COMPLETED: before the first unlock the app's storage and Keystore key are not open yet.
    if (action != Intent.ACTION_BOOT_COMPLETED && action != Intent.ACTION_MY_PACKAGE_REPLACED) return
    if (!context.liveSms || CollectSession.token(context) == null) return
    try {
      CollectSmsService.start(context)
    } catch (e: Exception) {
      Log.w("FamilyOS.Boot", "live SMS did not start: ${e.message}")
    }
  }
}
