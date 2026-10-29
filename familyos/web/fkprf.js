/* A trusted device's secret, derived inside the member's passkey (docs/family-key.md, "The PRF path").
 *
 * WebAuthn's PRF extension makes the passkey compute a 32-byte secret from a salt, inside the authenticator, behind its own user check
 * (Face ID, a fingerprint, a PIN). The browser keeps nothing: the same passkey and the same salt give the same secret every time, so a copy of
 * this browser's storage, or of the database, opens nothing. The server is handed the secret for one request to wrap or unwrap the household
 * key, and never stores it; it does see it then, which is why the family-key page does not say "end-to-end".
 *
 * Returns null where the passkey or the browser has no PRF (the caller then uses the stored device secret). Self-contained, so a test can
 * run it with a stand-in navigator.credentials.
 */
'use strict';

function fkB64u(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fkUnB64u(text) {
  let s = String(text).replace(/-/g, '+').replace(/_/g, '/');
  s += '==='.slice((s.length + 3) % 4);
  const raw = atob(s);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/* opts.credentialId and opts.salt (both base64url) re-derive an enrolled device's secret; with neither, a fresh random salt is used and any of
   the member's passkeys may answer, so the caller learns which one from the result. */
async function fkPrfDerive(opts) {
  const o = opts || {};
  if (!(window.PublicKeyCredential && navigator.credentials)) return null;
  const salt = o.salt ? fkUnB64u(o.salt) : crypto.getRandomValues(new Uint8Array(32));
  const allow = o.credentialId ? [{ type: 'public-key', id: fkUnB64u(o.credentialId) }] : [];
  const got = await navigator.credentials.get({ publicKey: {
    challenge: crypto.getRandomValues(new Uint8Array(32)), rpId: window.location.hostname, timeout: 60000, userVerification: 'required',
    allowCredentials: allow, extensions: { prf: { eval: { first: salt } } },
  } });
  const ext = got && got.getClientExtensionResults ? got.getClientExtensionResults() : {};
  const first = ext && ext.prf && ext.prf.results && ext.prf.results.first;
  if (!first) return null;
  const secret = new Uint8Array(first);
  if (secret.length !== 32) return null;
  return { secret: fkB64u(secret), credentialId: fkB64u(new Uint8Array(got.rawId)), salt: fkB64u(salt) };
}

/* The body the server's `prf` field takes. */
function fkPrfBody(derived) {
  return { secret: derived.secret, credential_id: derived.credentialId, salt: derived.salt };
}

/* A share wrapped under a passkey-derived secret, so the server keeps only ciphertext (familykey.seal_share). AES-GCM with a key from HKDF of
   the secret; the blob is the 12-byte nonce then the ciphertext. Wrong secret or a changed blob fails to open. */
async function fkShareKey(secretB64u) {
  const base = await crypto.subtle.importKey('raw', fkUnB64u(secretB64u), 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(0), info: new TextEncoder().encode('familyos share seal v1') },
    base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}

async function fkWrapShare(secretB64u, text) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await fkShareKey(secretB64u), new TextEncoder().encode(text)));
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv, 0); out.set(ct, iv.length);
  return fkB64u(out);
}

async function fkUnwrapShare(secretB64u, blobB64u) {
  const blob = fkUnB64u(blobB64u);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: blob.slice(0, 12) }, await fkShareKey(secretB64u), blob.slice(12));
  return new TextDecoder().decode(plain);
}
