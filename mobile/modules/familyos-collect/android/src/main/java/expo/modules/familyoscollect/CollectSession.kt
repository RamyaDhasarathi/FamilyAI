package expo.modules.familyoscollect

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

// The signed-in member's FamilyOS address and session token, for the live SMS service (CollectSmsService), which sends new
// SMS by itself while FamilyOS is closed. Ported from Mobile-UI-Agent's auth/SessionStore.kt: the token is encrypted with
// an AES key that lives in the Android Keystore (it never leaves the phone's secure store); the app's JS sets it after
// signing in and clears it on signing out. Whether live SMS is on is kept here too, for the boot receiver.
object CollectSession {
  private const val PREFS = "familyos_collect_session"
  private const val KEY_ALIAS = "familyos_collect_session_key"

  private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

  private fun key(): SecretKey {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
    val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
    gen.init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
      .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    return gen.generateKey()
  }

  fun set(context: Context, baseUrl: String, token: String) {
    val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
    val sealed = cipher.iv + cipher.doFinal(token.toByteArray())
    prefs(context).edit().putString("base", baseUrl.trimEnd('/')).putString("token", Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
  }

  fun clear(context: Context) {
    prefs(context).edit().remove("base").remove("token").putBoolean("live_sms", false).apply()
  }

  fun base(context: Context): String? = prefs(context).getString("base", null)

  fun token(context: Context): String? = try {
    val sealed = Base64.decode(prefs(context).getString("token", null) ?: return null, Base64.NO_WRAP)
    val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, 12)) }
    String(cipher.doFinal(sealed, 12, sealed.size - 12))
  } catch (e: Exception) {
    null
  }

  var Context.liveSms: Boolean
    get() = prefs(this).getBoolean("live_sms", false)
    set(v) = prefs(this).edit().putBoolean("live_sms", v).apply()

  fun mark(context: Context, fallback: Long): Long = prefs(context).getLong("sms_mark", fallback)
  fun setMark(context: Context, value: Long) = prefs(context).edit().putLong("sms_mark", value).apply()
}
