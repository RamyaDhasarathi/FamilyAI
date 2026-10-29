# Family OS — Installation and Setup Guide

This guide provides step-by-step instructions for running the complete Family OS system in a local development environment with:
1. **The Backend** running on your development laptop.
2. **The Mobile Application** running on a physical Android phone (or emulator) connected over your local Wi-Fi network.
3. **The AI Runtime** running locally via Ollama / vLLM or deterministic mock mode.

---

## 1. Prerequisites

### Laptop Requirements
- **Operating System:** Windows 10/11, macOS, or Linux.
- **Python:** Python 3.12 or newer.
- **Node.js:** Node.js v18 or newer (v20+ recommended), with `npm`.
- **Git**

### Phone Requirements
- **Device:** Physical Android phone with Wi-Fi connectivity.
- **Application:** Install the official **Expo Go** app from the Google Play Store.
- **Network:** The phone and laptop must be connected to the **same local Wi-Fi router / network**.

---

## 2. Backend Setup

### 2.1 Clone and Prepare Virtual Environment
Open a terminal in the root repository folder:

```powershell
# Navigate to backend directory
cd d:\FamilyOS\backend

# Optional: Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # On Windows PowerShell
# or: source .venv/bin/activate  # On macOS/Linux
```

### 2.2 Install Dependencies
Install all required Python packages:

```powershell
pip install -r requirements.txt
```

### 2.3 Configure Environment Variables
Copy or edit the `.env` file in `d:\FamilyOS\backend`:

```ini
APP_ENV=development
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./family_os.db
SECRET_KEY=family-os-secure-dev-secret-key-change-in-production-min32chars
BOOTSTRAP_TOKEN=dev-bootstrap-token-change-in-production
BOOTSTRAP_ADMIN_EMAIL=admin@familyos.local
BOOTSTRAP_ADMIN_PASSWORD=AdminPass123!
LLM_PROVIDER=mock
PRODUCT_PROVIDER=development_catalogue
STT_PROVIDER=disabled
TTS_PROVIDER=disabled
```

> [!IMPORTANT]
> The backend `HOST` must be set to `0.0.0.0` (not `127.0.0.1` or `localhost`). Binding to `0.0.0.0` allows the server to accept connections from external devices on your local Wi-Fi network (such as your Android phone).

### 2.4 Apply Database Migrations
Initialize the SQLite database schema with Alembic:

```powershell
python -m alembic upgrade head
```

### 2.5 Bootstrap Initial Administrator Account
Seed the initial family and administrator account:

```powershell
python -m app.bootstrap
```

This creates:
- Family Name: `The Miller Family`
- Admin User: `admin@familyos.local`
- Password: `AdminPass123!`
- Initial FGP Permission Grants granting full administrative and member access.

### 2.6 Run Backend Tests
Verify your backend environment:

```powershell
python -m pytest tests/ -v
```
All 30 tests should pass.

### 2.7 Launch Backend Server
Run the backend with:

```powershell
# Using the PowerShell launcher:
..\scripts\dev_backend.ps1

# Or directly:
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 3. Local Network Discovery & Phone Connectivity

Your Android phone cannot reach `localhost` or `127.0.0.1` on your laptop because `localhost` on the phone refers to the phone itself.

### 3.1 Discover Laptop LAN IP Address
Open a terminal on your laptop:

- **Windows:** Run `ipconfig`
  Look for your active **Wireless LAN adapter Wi-Fi** and note the **IPv4 Address** (e.g. `192.168.1.105`).
- **macOS / Linux:** Run `ifconfig` or `ip addr show`
  Look for `wlan0` or `en0` `inet` address.

### 3.2 Configure Windows Firewall
If running on Windows, ensure inbound traffic on port 8000 is permitted over Private networks:

```powershell
# Run once in an elevated PowerShell if needed:
New-NetFirewallRule -DisplayName "Family OS Backend (8000)" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### 3.3 Verify Phone Connectivity
Open Chrome or another browser on your Android phone and navigate to:
```
http://192.168.1.105:8000/health
```
*(Replace `192.168.1.105` with your laptop's actual IP)*.
You should see:
```json
{"status":"ok","version":"0.1.0"}
```

---

## 4. Mobile Application Setup

### 4.1 Install Mobile Dependencies
In a new terminal window:

```powershell
cd d:\FamilyOS\apps\mobile
npm install --legacy-peer-deps
```

### 4.2 Configure Mobile API Endpoint
Create a `.env` file in `d:\FamilyOS\apps\mobile\`:

```ini
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.105:8000
```
*(Substitute your actual laptop IP address. If using the Android Studio Emulator on the same laptop, you may use `http://10.0.2.2:8000`)*.

### 4.3 Type-Check Verification
Ensure all TypeScript definitions compile cleanly:

```powershell
npm run type-check
```

### 4.4 Launch the Mobile Application
Start the Expo packager:

```powershell
npx expo start
```

- A large QR code will appear in the terminal.
- Open **Expo Go** on your physical Android phone.
- Tap **Scan QR code** and point your camera at the terminal screen.
- The JavaScript bundle will build and load onto your device.

---

## 5. AI Model Provider Configuration

Family OS supports flexible LLM provider routing configured via backend environment variables.

### 5.1 Development Mock Mode (Default)
```ini
LLM_PROVIDER=mock
```
- No external model dependencies required.
- Fast, 100% deterministic intent extraction for testing mice, laptops, washing machines, and backpacks.
- Flags responses with `is_mock=True` and shows transparent `Development Data` banners in the UI.

### 5.2 Local Ollama Inference (Recommended for Private AI)
1. Install Ollama on your laptop from [ollama.ai](https://ollama.ai).
2. Pull a structured model (e.g., Llama 3 or Mistral):
   ```bash
   ollama pull llama3:8b
   ```
3. Update `backend/.env`:
   ```ini
   LLM_PROVIDER=openai_compatible
   LLM_BASE_URL=http://localhost:11434/v1
   LLM_API_KEY=ollama
   LLM_MODEL=llama3:8b
   ENABLE_EXTERNAL_CLOUD_INFERENCE=false
   ```

### 5.3 Local vLLM Inference
For high-performance GPU workstations:
```ini
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=none
LLM_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
ENABLE_EXTERNAL_CLOUD_INFERENCE=false
```

### 5.4 External Cloud Providers (Strict Opt-In)
By default, `ENABLE_EXTERNAL_CLOUD_INFERENCE` is set to `false`. To prevent accidental cloud leakage, external cloud endpoints (such as OpenAI) are rejected unless you explicitly toggle:
```ini
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
ENABLE_EXTERNAL_CLOUD_INFERENCE=true
```
