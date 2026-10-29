"""The wallet card's browser half (familyos/web/wallet.js) under node: the message is hex-encoded as personal_sign expects, a transfer's words are
escaped before they reach the page, the right buttons appear for the right person and state, and a browser without a wallet says so. The real
browser wallet and the DOM are not exercised here."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "familyos" / "web" / "wallet.js"

HARNESS = r"""
const fs = require('fs'); const vm = require('vm');
const sandbox = { TextEncoder, window: {}, esc: (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const run = (code) => vm.runInContext(code, sandbox);
(async () => {
  const out = {};
  out.hex = run("walletHex('Aé')");
  out.short = run("walletShort('0x1234567890abcdef1234567890abcdef12345678')");
  const t = { id: 'T1', status: 'proposed', amount: '2', token: 'USDC', payee_label: '<img src=x onerror=alert(1)>', payee_address: '0x1234567890abcdef1234567890abcdef12345678', payee_new: true, memo: '"quoted"', proposed_by: 'M2' };
  sandbox.t = t;
  out.guardianProposed = run("walletTransferHtml(t, { role: 'guardian', id: 'M1' }, {})");
  out.proposerProposed = run("walletTransferHtml(t, { role: 'adult', id: 'M2' }, {})");
  out.otherProposed = run("walletTransferHtml(t, { role: 'adult', id: 'M3' }, {})");
  sandbox.t2 = { ...t, status: 'approved', payee_label: null, memo: null };
  out.approvedGuardian = run("walletTransferHtml(t2, { role: 'guardian', id: 'M1' }, {})");
  out.approvedAdult = run("walletTransferHtml(t2, { role: 'adult', id: 'M2' }, {})");
  try { await run("walletAccount()"); out.noWallet = 'no error'; } catch (e) { out.noWallet = e.message; }
  let asked;
  sandbox.window.ethereum = { request: async (r) => { asked = r; return r.method === 'eth_requestAccounts' ? ['0xabc'] : '0xsig'; } };
  out.account = await run("walletAccount()");
  out.sig = await run("walletSign('0xabc', 'hi')"); out.asked = asked;
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_wallet_card_script():
    r = subprocess.run(["node", "-e", HARNESS, str(JS)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["hex"] == "0x41c3a9" and o["short"] == "0x1234…5678"
    assert "<img" not in o["guardianProposed"] and "&lt;img" in o["guardianProposed"] and "&quot;quoted&quot;" in o["guardianProposed"]
    assert "data-wallet-approve" in o["guardianProposed"] and "data-wallet-reject" in o["guardianProposed"]
    assert "data-wallet-approve" not in o["proposerProposed"] and "Withdraw" in o["proposerProposed"]
    assert "data-wallet-" not in o["otherProposed"]
    assert "data-wallet-send" in o["approvedGuardian"] and "data-wallet-send" not in o["approvedAdult"]
    assert "No wallet found" in o["noWallet"] and o["account"] == "0xabc"
    assert o["asked"]["method"] == "personal_sign" and o["asked"]["params"] == ["0x6869", "0xabc"]
