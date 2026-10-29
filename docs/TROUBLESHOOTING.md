# Family OS — Troubleshooting Guide

This guide provides diagnostic procedures and resolutions for common issues encountered during setup, testing, and development.

---

## 1. Network Connectivity Issues (Phone Cannot Reach Laptop)

### Symptom: `Network Error` or `Cannot reach server` in Mobile App
- **Cause 1: Mobile App using `localhost` instead of laptop IP**
  - *Fix:* `localhost` on your Android phone refers to the phone itself, not your laptop. In `apps/mobile/.env`, set:
    ```ini
    EXPO_PUBLIC_API_BASE_URL=http://<YOUR_LAPTOP_LAN_IP>:8000
    ```
    Find your laptop's IP via `ipconfig` (Windows) or `ifconfig` (macOS/Linux).

- **Cause 2: Backend listening on `127.0.0.1`**
  - *Fix:* Ensure the backend is started with `--host 0.0.0.0`:
    ```powershell
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```

- **Cause 3: Windows Firewall blocking incoming traffic on Port 8000**
  - *Fix:* Open an administrative PowerShell prompt on your laptop and run:
    ```powershell
    New-NetFirewallRule -DisplayName "Family OS Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
    ```

- **Cause 4: Wi-Fi Router "AP Client Isolation"**
  - *Fix:* Many public or guest Wi-Fi networks (and some home routers) prevent devices on the Wi-Fi network from communicating with one another. Ensure both phone and laptop are connected to your primary home Wi-Fi network, or use a mobile hotspot created from your phone.

- **Testing Connectivity:** Open Chrome on your Android phone and navigate to `http://<YOUR_LAPTOP_IP>:8000/health`. If you see `{"status":"ok","version":"0.1.0"}`, network routing is functioning correctly.

---

## 2. Database Migration Issues

### Symptom: `alembic.util.exc.CommandError: Can't locate revision identified by '...'`
- **Cause:** Desynchronized `alembic_version` table.
- **Fix:** In development SQLite, remove the local database file `backend/family_os.db` and re-run migrations from scratch:
  ```powershell
  cd d:\FamilyOS\backend
  Remove-Item family_os.db -ErrorAction SilentlyContinue
  python -m alembic upgrade head
  python -m app.bootstrap
  ```

---

## 3. Voice Recording & Audio Issues

### Symptom: Microphone button does not record or app crashes on recording
- **Cause 1: Android permissions denied**
  - *Fix:* Open **Settings > Apps > Expo Go > Permissions > Microphone** on your Android phone and set to **Allow while using app**.
- **Cause 2: `expo-av` recording mode failed**
  - *Fix:* Ensure no other audio app (such as YouTube or a phone call) is holding exclusive audio focus on your device.

### Symptom: Voice transcribe endpoint returns `is_available: false`
- **Cause:** `STT_PROVIDER` is set to `disabled` (the default development setting).
- **Explanation:** In the base development milestone, local voice transcription defaults to graceful fallback without throwing errors. Text input is always active and available in the composer.

---

## 4. AI Model Connection & Timeout Issues

### Symptom: Chat messages hang or return `AI service unavailable`
- **Cause 1: Local Ollama daemon is not running**
  - *Fix:* Open a terminal and run `ollama serve`. Verify with `curl http://localhost:11434/v1/models`.
- **Cause 2: Selected model is not pulled**
  - *Fix:* Ensure the model specified in `LLM_MODEL` is installed (e.g. `ollama run llama3:8b`).
- **Cause 3: Cloud inference disabled**
  - *Fix:* If pointing to OpenAI (`https://api.openai.com/v1`), `ENABLE_EXTERNAL_CLOUD_INFERENCE` must be set to `true` in `backend/.env`. By default, Family OS rejects external network inference to prevent silent data exfiltration.
- **Fallback:** Switch to mock mode for instant deterministic responses:
  ```ini
  LLM_PROVIDER=mock
  ```

---

## 5. FGP Permission Denials (`403 Forbidden`)

### Symptom: User receives `FGP_ACCESS_DENIED: NO_GRANT`
- **Cause:** Default-deny policy enforcement.
- **Explanation:** Family OS does not give members blanket privileges. New members must be granted permissions by a family administrator.
- **Fix:** Log in as an administrator (`admin@familyos.local`), open the **Family Governance** tab in the mobile app drawer, select the member, and enable the required permission grant.

---

## 6. Expo / Mobile App Bundling Issues

### Symptom: Metro bundler error `Unable to resolve module`
- **Fix:** Clear the Metro packager cache and restart:
  ```powershell
  cd d:\FamilyOS\apps\mobile
  npx expo start -c
  ```
