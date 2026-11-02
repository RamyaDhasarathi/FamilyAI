package expo.modules.familyoscollect

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.view.Display
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

private const val TAG = "FamilyOS.Agent"
private const val MAX_TREE_NODES = 400
private const val MAX_SCREENSHOT_WIDTH = 540

// The phone agent's eyes and hands (ported from Mobile-UI-Agent's MobileUseAccessibilityService.kt): the screen as an
// element tree and a small screenshot, and the actions tap / long press / type / swipe / back / home / open an app. No
// decisions here -- the backend chooses each action (familyos/collect/phone_agent.py) and checks it first; the JS loop
// (services/phoneAgent.ts) asks and acts. It does nothing until the person allows it under Accessibility, and is
// used only while they run the agent on an app they switched on.
class FamilyosAgentService : AccessibilityService() {
  private val screenshotExecutor = Executors.newSingleThreadExecutor()
  // Its own scheduler, not the main Looper: a hang there (seen on vivo builds) must not take the timeout with it.
  private val watchdog = Executors.newSingleThreadScheduledExecutor()

  companion object {
    var instance: FamilyosAgentService? = null
      private set
  }

  override fun onServiceConnected() {
    super.onServiceConnected()
    instance = this
  }

  override fun onDestroy() {
    instance = null
    super.onDestroy()
  }

  // Pull-based: the loop asks for the screen when it needs it.
  override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

  override fun onInterrupt() {}

  fun currentPackage(): String = rootInActiveWindow?.packageName?.toString() ?: ""

  /** Elements with words or that can be acted on; a password field's text is never read. */
  fun tree(): List<Map<String, Any?>> {
    val out = mutableListOf<Map<String, Any?>>()
    val root = rootInActiveWindow ?: return out
    walk(root, out)
    return out
  }

  private fun walk(node: AccessibilityNodeInfo, out: MutableList<Map<String, Any?>>) {
    if (out.size >= MAX_TREE_NODES) return
    val text = if (node.isPassword) "" else node.text?.toString().orEmpty()
    val desc = node.contentDescription?.toString().orEmpty()
    if (text.isNotBlank() || desc.isNotBlank() || node.isClickable || node.isEditable || node.isScrollable) {
      val b = Rect()
      node.getBoundsInScreen(b)
      out.add(mapOf(
        "text" to text, "contentDescription" to desc,
        "className" to (node.className?.toString()?.substringAfterLast('.') ?: ""),
        "clickable" to node.isClickable, "scrollable" to node.isScrollable, "editable" to node.isEditable,
        "password" to node.isPassword, "focused" to node.isFocused,
        "bounds" to mapOf("left" to b.left, "top" to b.top, "right" to b.right, "bottom" to b.bottom)
      ))
    }
    for (i in 0 until node.childCount) {
      val child = node.getChild(i) ?: continue
      walk(child, out)
    }
  }

  /** The smallest clickable element under a point, so the tap is the element's own click, not a gesture. */
  private fun clickableAt(x: Int, y: Int): AccessibilityNodeInfo? {
    val root = rootInActiveWindow ?: return null
    var best: AccessibilityNodeInfo? = null
    var bestArea = Long.MAX_VALUE
    fun search(node: AccessibilityNodeInfo) {
      val b = Rect()
      node.getBoundsInScreen(b)
      if (!b.contains(x, y)) return
      if (node.isClickable && node.isVisibleToUser) {
        val area = b.width().toLong() * b.height().toLong()
        if (area < bestArea) {
          best = node
          bestArea = area
        }
      }
      for (i in 0 until node.childCount) node.getChild(i)?.let { search(it) }
    }
    search(root)
    return best
  }

  /** By words (Mobile-UI-Agent findClickableNodeByDescription): the first match, up to its clickable parent. */
  private fun clickableByWords(words: String): AccessibilityNodeInfo? {
    val root = rootInActiveWindow ?: return null
    val needle = words.trim().lowercase()
    if (needle.isEmpty()) return null
    var found: AccessibilityNodeInfo? = null
    fun search(node: AccessibilityNodeInfo) {
      if (found != null) return
      val text = node.text?.toString()?.lowercase().orEmpty()
      val desc = node.contentDescription?.toString()?.lowercase().orEmpty()
      if ((text.isNotEmpty() && text == needle) || (desc.isNotEmpty() && desc == needle)) {
        found = node
        return
      }
      for (i in 0 until node.childCount) node.getChild(i)?.let { search(it) }
    }
    search(root)
    var c = found
    var depth = 0
    while (c != null && !c.isClickable && depth < 6) {
      c = c.parent
      depth++
    }
    return c
  }

  fun tap(words: String, x: Float?, y: Float?, long: Boolean): Boolean {
    if (x != null && y != null) {
      if (!long) clickableAt(x.toInt(), y.toInt())?.let { if (it.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true }
      return press(x, y, if (long) 600 else 50)
    }
    val node = clickableByWords(words) ?: return false
    return node.performAction(if (long) AccessibilityNodeInfo.ACTION_LONG_CLICK else AccessibilityNodeInfo.ACTION_CLICK)
  }

  private fun press(x: Float, y: Float, ms: Long): Boolean {
    val path = Path().apply { moveTo(x, y) }
    return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, ms)).build(), null, null)
  }

  fun swipe(direction: String): Boolean {
    val m = resources.displayMetrics
    val w = m.widthPixels.toFloat()
    val h = m.heightPixels.toFloat()
    val path = Path()
    when (direction) {
      "up" -> { path.moveTo(w / 2, h * 0.75f); path.lineTo(w / 2, h * 0.25f) }
      "down" -> { path.moveTo(w / 2, h * 0.25f); path.lineTo(w / 2, h * 0.75f) }
      "left" -> { path.moveTo(w * 0.75f, h / 2); path.lineTo(w * 0.25f, h / 2) }
      "right" -> { path.moveTo(w * 0.25f, h / 2); path.lineTo(w * 0.75f, h / 2) }
      else -> return false
    }
    return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 250)).build(), null, null)
  }

  /** Into the focused field (else the first one), never a password field. */
  fun type(text: String): Boolean {
    val root = rootInActiveWindow ?: return false
    var field: AccessibilityNodeInfo? = null
    var first: AccessibilityNodeInfo? = null
    fun search(node: AccessibilityNodeInfo) {
      if (field != null) return
      if (node.isEditable && !node.isPassword) {
        if (node.isFocused) { field = node; return }
        if (first == null) first = node
      }
      for (i in 0 until node.childCount) node.getChild(i)?.let { search(it) }
    }
    search(root)
    val target = field ?: first ?: return false
    val args = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text) }
    return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
  }

  /** The whole display in pixels: what the screenshot shows and the element bounds are measured in. */
  fun screenSize(): Pair<Int, Int> {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
      val b = (getSystemService(WINDOW_SERVICE) as WindowManager).maximumWindowMetrics.bounds
      return b.width() to b.height()
    }
    val m = resources.displayMetrics
    return m.widthPixels to m.heightPixels
  }

  fun back(): Boolean = performGlobalAction(GLOBAL_ACTION_BACK)
  fun home(): Boolean = performGlobalAction(GLOBAL_ACTION_HOME)

  /** Starts an activity from the service (Android allows that from the background, where the loop runs). */
  fun start(intent: Intent): Boolean = try {
    startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    true
  } catch (e: Exception) {
    Log.w(TAG, "start failed: ${e.message}")
    false
  }

  /** A JPEG of the screen, 540 px wide, as base64; null below Android 11 or when the phone never answers (4 s). */
  fun screenshot(done: (String?) -> Unit) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return done(null)
    val settled = AtomicBoolean(false)
    fun settle(v: String?) { if (settled.compareAndSet(false, true)) done(v) }
    val timeout = watchdog.schedule({ settle(null) }, 4, TimeUnit.SECONDS)
    try {
      takeScreenshot(Display.DEFAULT_DISPLAY, screenshotExecutor, object : TakeScreenshotCallback {
        override fun onSuccess(result: ScreenshotResult) {
          timeout.cancel(false)
          try {
            val hw = Bitmap.wrapHardwareBuffer(result.hardwareBuffer, result.colorSpace) ?: return settle(null)
            val full = hw.copy(Bitmap.Config.ARGB_8888, false)
            val scale = MAX_SCREENSHOT_WIDTH.toFloat() / full.width
            val small = if (scale < 1f) Bitmap.createScaledBitmap(full, MAX_SCREENSHOT_WIDTH, (full.height * scale).toInt(), true) else full
            val out = ByteArrayOutputStream()
            small.compress(Bitmap.CompressFormat.JPEG, 60, out)
            settle(Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP))
            if (small !== full) small.recycle()
            full.recycle()
            hw.recycle()
          } catch (e: Exception) {
            settle(null)
          } finally {
            result.hardwareBuffer.close()
          }
        }

        override fun onFailure(errorCode: Int) {
          timeout.cancel(false)
          settle(null)
        }
      })
    } catch (e: Exception) {
      timeout.cancel(false)
      settle(null)
    }
  }
}
