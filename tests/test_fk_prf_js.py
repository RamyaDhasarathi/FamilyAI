"""The browser half of passkey-derived device secrets (familyos/web/fkprf.js), run under node with a stand-in for navigator.credentials: the
request asks the passkey for a PRF secret from the salt, a returned secret comes back as base64url, and a passkey or browser without PRF gives
null so the caller falls back. The real authenticator is not exercised here."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "familyos" / "web" / "fkprf.js"

HARNESS = r"""
const fs = require('fs'); const vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const make = (results, rawId) => ({ rawId: rawId.buffer, getClientExtensionResults: () => ({ prf: results }) });
const sandbox = { btoa: (s) => Buffer.from(s, 'binary').toString('base64'), atob: (s) => Buffer.from(s, 'base64').toString('binary'),
  crypto: require('crypto').webcrypto, Uint8Array, TextEncoder, TextDecoder, window: { PublicKeyCredential: function () {}, location: { hostname: 'home.example' } }, console };
sandbox.navigator = { credentials: { get: async (o) => { calls.push(o.publicKey); return globalThis.__answer(o.publicKey); } } };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const out = {};
(async () => {
  const secret = new Uint8Array(32).fill(7), cred = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
  globalThis.__answer = () => make({ results: { first: secret.buffer } }, cred);
  vm.runInContext('globalThis.__go = async (o) => fkPrfDerive(o)', sandbox);
  const fresh = await sandbox.__go({});
  out.fresh = { secretLen: Buffer.from(fresh.secret, 'base64url').length, cred: fresh.credentialId, saltLen: Buffer.from(fresh.salt, 'base64url').length,
    allow: calls[0].allowCredentials.length, rp: calls[0].publicKey ? 1 : calls[0].rpId, uv: calls[0].userVerification };
  const again = await sandbox.__go({ credentialId: fresh.credentialId, salt: fresh.salt });
  out.again = { sameSalt: again.salt === fresh.salt, allowed: Buffer.from(Buffer.from(calls[1].allowCredentials[0].id).toString('hex'), 'hex').length,
    sent: Buffer.from(calls[1].extensions.prf.eval.first).toString('base64url') === fresh.salt };
  globalThis.__answer = () => make(undefined, cred);
  out.none = await sandbox.__go({});
  globalThis.__answer = () => make({ results: { first: new Uint8Array(16).buffer } }, cred);
  out.short = await sandbox.__go({});
  vm.runInContext('globalThis.__body = fkPrfBody({ secret: "s", credentialId: "c", salt: "t" })', sandbox);
  out.body = sandbox.__body;
  vm.runInContext('globalThis.__wrap = async (k, t) => fkWrapShare(k, t); globalThis.__unwrap = async (k, b) => fkUnwrapShare(k, b)', sandbox);
  const k1 = Buffer.alloc(32, 5).toString('base64url'), k2 = Buffer.alloc(32, 6).toString('base64url');
  const blob = await sandbox.__wrap(k1, 'word '.repeat(33).trim());
  out.share = { len: Buffer.from(blob, 'base64url').length, back: (await sandbox.__unwrap(k1, blob)).split(' ').length };
  try { await sandbox.__unwrap(k2, blob); out.share.wrong = 'opened'; } catch (e) { out.share.wrong = 'refused'; }
  const tampered = Buffer.from(blob, 'base64url'); tampered[20] ^= 1;
  try { await sandbox.__unwrap(k1, tampered.toString('base64url')); out.share.tampered = 'opened'; } catch (e) { out.share.tampered = 'refused'; }
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_passkey_prf_helper_asks_for_a_secret_returns_it_encoded_and_falls_back_when_there_is_none(tmp_path):
    script = tmp_path / "harness.js"
    script.write_text(HARNESS)
    run = subprocess.run(["node", str(script), str(JS)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["fresh"]["secretLen"] == 32 and out["fresh"]["saltLen"] == 32 and out["fresh"]["allow"] == 0 and out["fresh"]["uv"] == "required"
    assert out["fresh"]["cred"] == "AQIDBAUGBwg"
    assert out["again"]["sameSalt"] is True and out["again"]["sent"] is True and out["again"]["allowed"] == 8
    assert out["none"] is None and out["short"] is None
    assert out["body"] == {"secret": "s", "credential_id": "c", "salt": "t"}
    # a share wrapped under a passkey-derived secret opens only under that secret, and a changed byte is refused
    assert out["share"]["back"] == 33 and 40 <= out["share"]["len"] <= 1024 and out["share"]["wrong"] == "refused" and out["share"]["tampered"] == "refused"
