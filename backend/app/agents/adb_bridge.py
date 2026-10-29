"""Android Debug Bridge (ADB) controller for real-device control over Wi-Fi or USB."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ADBBridge:
    """Manages ADB connectivity and executes low-level gestures on Android devices."""

    def __init__(self, adb_path: Optional[str] = None, default_serial: Optional[str] = None) -> None:
        self._adb_path = adb_path or self._discover_adb_path()
        self.default_serial = default_serial or get_settings().ADB_DEVICE_SERIAL

    @classmethod
    def _discover_adb_path(cls) -> str:
        """Find adb executable in repo tools, PATH, or standard Android SDK directories."""
        settings = get_settings()
        for attr in ("ADB_BINARY_PATH", "ADB_PATH"):
            if hasattr(settings, attr) and getattr(settings, attr, None):
                custom = getattr(settings, attr)
                if custom and os.path.exists(custom):
                    return custom

        # 1. Check local repo tools directory (portable bundled)
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        repo_adb = repo_root / "tools" / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if repo_adb.exists():
            return str(repo_adb)

        # 2. Check system PATH
        path_adb = shutil.which("adb")
        if path_adb:
            return path_adb

        # 3. Check Windows LocalAppData
        if os.name == "nt":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                sdk_adb = Path(local_appdata) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
                if sdk_adb.exists():
                    return str(sdk_adb)

        # Default fallback
        return "adb"

    @property
    def adb_executable(self) -> str:
        return self._adb_path

    def is_available(self) -> bool:
        """Check if ADB executable exists and runs."""
        try:
            res = shutil.which(self._adb_path) or os.path.exists(self._adb_path)
            return bool(res)
        except Exception:
            return False

    async def _run_cmd(self, *args: str, timeout: float = 10.0) -> Tuple[int, str, str]:
        """Execute an ADB command asynchronously."""
        cmd = [self._adb_path, *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode if proc.returncode is not None else 1,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.warning(f"ADB command timed out: {' '.join(cmd)}")
            return -1, "", "Command timed out"
        except Exception as exc:
            logger.error(f"Failed to execute ADB command: {exc}")
            return -1, "", str(exc)

    async def get_version(self) -> Optional[str]:
        """Return the ADB version string."""
        rc, out, _ = await self._run_cmd("version")
        if rc == 0:
            first_line = out.strip().split("\n")[0]
            return first_line
        return None

    async def list_devices(self) -> List[Dict[str, str]]:
        """List all connected ADB devices (USB and Wireless)."""
        rc, out, _ = await self._run_cmd("devices")
        devices: List[Dict[str, str]] = []
        if rc == 0:
            for line in out.strip().split("\n")[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    devices.append({
                        "serial": parts[0],
                        "state": parts[1],
                        "type": "wireless" if ":" in parts[0] else "usb",
                    })
        return devices

    async def connect(self, host_port: str) -> Dict[str, Any]:
        """Connect to an Android device over Wi-Fi (e.g. 192.168.1.50:5555)."""
        rc, out, err = await self._run_cmd("connect", host_port)
        combined = f"{out} {err}".strip()
        success = "connected to" in combined.lower() and "unable" not in combined.lower()
        if success:
            self.default_serial = host_port
        return {
            "success": success,
            "target": host_port,
            "output": combined,
        }

    async def disconnect(self, host_port: Optional[str] = None) -> Dict[str, Any]:
        """Disconnect wireless device."""
        target = host_port or self.default_serial
        if not target:
            return {"success": False, "message": "No target specified"}
        rc, out, err = await self._run_cmd("disconnect", target)
        return {
            "success": rc == 0,
            "target": target,
            "output": f"{out} {err}".strip(),
        }

    def _resolve_target(self, serial: Optional[str] = None) -> List[str]:
        target = serial or self.default_serial
        return ["-s", target] if target else []

    async def get_screen_size(self, serial: Optional[str] = None) -> Tuple[int, int]:
        """Query physical screen resolution (e.g. 1080, 2400)."""
        target = self._resolve_target(serial)
        rc, out, _ = await self._run_cmd(*target, "shell", "wm", "size")
        if rc == 0:
            match = re.search(r"(\d+)\s*x\s*(\d+)", out)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return (min(width, height), max(width, height))
        return (1080, 2400)

    async def wake_up(self, serial: Optional[str] = None) -> bool:
        """Wake up device screen if asleep."""
        target = self._resolve_target(serial)
        rc, _, _ = await self._run_cmd(*target, "shell", "input", "keyevent", "224")
        return rc == 0

    async def tap(self, x: int, y: int, serial: Optional[str] = None) -> bool:
        """Perform a touch tap at screen pixel coordinates."""
        target = self._resolve_target(serial)
        rc, _, _ = await self._run_cmd(*target, "shell", "input", "tap", str(x), str(y))
        return rc == 0

    async def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 350,
        serial: Optional[str] = None,
    ) -> bool:
        """Perform a swipe/scroll gesture from (x1, y1) to (x2, y2)."""
        target = self._resolve_target(serial)
        rc, _, _ = await self._run_cmd(
            *target,
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        )
        return rc == 0

    async def input_text(self, text: str, serial: Optional[str] = None) -> bool:
        """Input text on focused field (escapes spaces and special characters)."""
        target = self._resolve_target(serial)
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("'", "\\'")
        rc, _, _ = await self._run_cmd(*target, "shell", "input", "text", escaped)
        return rc == 0

    async def keyevent(self, key_code: int, serial: Optional[str] = None) -> bool:
        """Dispatch Android keycode (4=BACK, 3=HOME, 66=ENTER)."""
        target = self._resolve_target(serial)
        rc, _, _ = await self._run_cmd(*target, "shell", "input", "keyevent", str(key_code))
        return rc == 0

    async def open_url(self, url: str, serial: Optional[str] = None, package: Optional[str] = None) -> bool:
        """Open a web URL in the default Android browser or specific app package via VIEW intent."""
        target = self._resolve_target(serial)
        cmd = ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url]
        if package:
            cmd.append(package)
        rc, _, _ = await self._run_cmd(*target, *cmd)
        return rc == 0

    async def execute_shell(self, cmd_str: str, serial: Optional[str] = None) -> Tuple[int, str, str]:
        """Execute an arbitrary adb shell command."""
        target = self._resolve_target(serial)
        import shlex
        parts = shlex.split(cmd_str)
        return await self._run_cmd(*target, "shell", *parts)

    async def open_app(self, package_name: str, serial: Optional[str] = None) -> bool:
        """Launch an app package using monkey launcher."""
        target = self._resolve_target(serial)
        rc, _, _ = await self._run_cmd(
            *target,
            "shell",
            "monkey",
            "-p",
            package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )
        return rc == 0

    async def dump_ui_hierarchy(self, serial: Optional[str] = None) -> str:
        """Dump and retrieve current screen UI hierarchy XML via UIAutomator."""
        target = self._resolve_target(serial)
        rc, out, _ = await self._run_cmd(
            *target,
            "shell",
            "uiautomator dump /sdcard/familyos_dump.xml && cat /sdcard/familyos_dump.xml",
            timeout=15.0,
        )
        if rc == 0 and "<?xml" in out:
            xml_start = out.find("<?xml")
            xml_end = out.find("</hierarchy>", xml_start)
            if xml_end != -1:
                return out[xml_start : xml_end + len("</hierarchy>")]
            return out[xml_start:]
        return ""

    @staticmethod
    def extract_otp_from_text(text: str, card_last4: Optional[str] = None) -> Optional[str]:
        """Extract a 4 to 8 digit credit card / bank transaction OTP from message text."""
        if not text:
            return None

        # Pattern 1: "<OTP> is (the|your) OTP / verification code"
        m1 = re.search(
            r"\b(\d{4,8})\b\s+(?:is\s+(?:the|your)?\s*(?:secret\s*)?(?:one\s*time\s*password|otp|verification\s*code|code))",
            text,
            re.IGNORECASE,
        )
        if m1:
            code = m1.group(1)
            if not (card_last4 and code == card_last4):
                return code

        # Pattern 2: "OTP (is|:|=)\s*<OTP>" or "Use code <OTP>"
        m2 = re.search(
            r"(?:otp|code|one\s*time\s*password|passcode|secret)[^0-9\n]{0,25}\b(\d{4,8})\b",
            text,
            re.IGNORECASE,
        )
        if m2:
            code = m2.group(1)
            if code not in ("2024", "2025", "2026", "2027"):
                if not (card_last4 and code == card_last4):
                    return code

        # Pattern 3: Look for standalone numbers in SMS containing banking keywords
        if re.search(r"\b(?:otp|card|bank|credit|purchase|amazon|transaction|txn|inr|rs)\b", text, re.IGNORECASE):
            candidates = re.findall(r"\b(\d{4,8})\b", text)
            for c in candidates:
                if card_last4 and c == card_last4:
                    continue
                if c in ("2024", "2025", "2026", "2027"):
                    continue
                return c

        return None

    async def get_active_notifications(self, serial: Optional[str] = None) -> List[str]:
        """Retrieve recent notification texts from dumpsys."""
        target = self._resolve_target(serial)
        # Try --noredact first, then fallback
        rc, out, _ = await self._run_cmd(*target, "shell", "dumpsys", "notification", "--noredact", timeout=6.0)
        if rc != 0 or not out:
            rc, out, _ = await self._run_cmd(*target, "shell", "dumpsys", "notification", timeout=6.0)

        texts: List[str] = []
        if rc == 0 and out:
            # Extract android.text, tickerText, android.bigText, android.title
            found = re.findall(
                r"(?:android\.(?:text|bigText|title)|tickerText)=(?:String\s*\((.*?)\)|(.*?))\r?$",
                out,
                re.MULTILINE,
            )
            for match in found:
                val = match[0] or match[1]
                val = val.strip()
                if val and val != "null" and len(val) > 4:
                    texts.append(val)
        return texts

    async def get_latest_sms_messages(self, serial: Optional[str] = None, limit: int = 5) -> List[str]:
        """Query recent SMS inbox messages via Android content provider."""
        target = self._resolve_target(serial)
        rc, out, _ = await self._run_cmd(
            *target,
            "shell",
            "content",
            "query",
            "--uri",
            "content://sms/inbox",
            "--projection",
            "body,date",
            "--sort",
            "date DESC",
            "--limit",
            str(limit),
            timeout=6.0,
        )
        messages: List[str] = []
        if rc == 0 and out:
            for line in out.split("\n"):
                if "body=" in line:
                    body_part = line.split("body=", 1)[1]
                    # May end with comma before next column
                    if ", date=" in body_part:
                        body_part = body_part.split(", date=")[0]
                    clean_msg = body_part.strip()
                    if clean_msg:
                        messages.append(clean_msg)
        return messages

    async def wait_for_otp(
        self,
        timeout_seconds: float = 45.0,
        poll_interval: float = 2.0,
        card_last4: Optional[str] = None,
        serial: Optional[str] = None,
    ) -> Optional[str]:
        """Poll incoming notifications and SMS inbox for bank payment OTP."""
        elapsed = 0.0
        logger.info(f"ADB OTP listener started. Polling for OTP (timeout={timeout_seconds}s, card_last4={card_last4})...")

        while elapsed < timeout_seconds:
            # 1. Check notifications
            notifications = await self.get_active_notifications(serial)
            for notif in notifications:
                otp = self.extract_otp_from_text(notif, card_last4=card_last4)
                if otp:
                    logger.info(f"Successfully captured OTP from notification: {otp}")
                    return otp

            # 2. Check SMS inbox
            sms_list = await self.get_latest_sms_messages(serial, limit=3)
            for sms in sms_list:
                otp = self.extract_otp_from_text(sms, card_last4=card_last4)
                if otp:
                    logger.info(f"Successfully captured OTP from SMS inbox: {otp}")
                    return otp

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(f"OTP listener timed out after {timeout_seconds} seconds.")
        return None
