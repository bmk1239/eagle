from io import BytesIO
from PIL import Image
import cv2
import numpy as np
import requests
import time
import random
import re
import hashlib
import uuid
import warnings
from urllib.parse import quote, urlparse, parse_qs, urlencode
from typing import Optional, Tuple, Dict, Any, List
import base64
import os
import json
import sys
from collections import OrderedDict
from datetime import datetime, date, timezone
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')

# ==================== CONFIGURATION ====================
MAIL_API_KEY = ""   # <-- Replace with your real key
DEBUG = False   # set to True for verbose output

# ==================== TempMailService using MailSlurper ====================
class TempMailService:
    """Temporary email service using Boomlify Temp Mail API."""

    def __init__(self, api_key: str):
        """
        Initialize the Boomlify Temp Mail service.

        Args:
            api_key: Your Boomlify API key
        """
        self.api_key = api_key
        self.base_url = "https://v1.boomlify.com"
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Current email state
        self.email = None
        self.email_id = None

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                      data: Optional[Dict] = None) -> Dict:
        """
        Make a REST API request to Boomlify.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=data,
                timeout=30
            )

            # Handle different response status codes
            if response.status_code in [200, 201]:
                return response.json() if response.content else {"status": "success"}
            elif response.status_code == 204:
                return {"status": "success", "message": "No content"}
            elif response.status_code == 400:
                error_data = response.json() if response.content else {}
                raise Exception(f"Bad Request (400): {error_data.get('error', 'Invalid parameters')}")
            elif response.status_code == 401:
                raise Exception("Unauthorized (401): Invalid API key")
            elif response.status_code == 403:
                raise Exception("Forbidden (403): Premium feature requires higher plan")
            elif response.status_code == 404:
                raise Exception(f"Not Found (404): Endpoint {endpoint} not found")
            elif response.status_code == 409:
                error_data = response.json() if response.content else {}
                raise Exception(f"Conflict (409): {error_data.get('error', 'Resource already exists')}")
            elif response.status_code == 429:
                raise Exception("Too Many Requests (429): Rate limit exceeded")
            else:
                response.raise_for_status()
                return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response")

    def generate_email(self,
                       custom_username: Optional[str] = None,
                       expiration: str = "1hour",
                       domain: Optional[str] = None):
        """
        Generate a new temporary email address.

        Args:
            custom_username: Optional custom username (3-30 chars)
            expiration: Expiration time (10min, 1hour, 1day, permanent)
            domain: Optional custom domain (must be verified)

        Returns:
            The generated email address
        """
        endpoint = "/api/v1/emails/create"

        # Build query parameters
        params = {"time": expiration}

        if custom_username:
            params["custom_username"] = custom_username
            if DEBUG:
                print(f"  ℹ️ Using custom username: {custom_username}")

        if domain:
            params["domain"] = domain
            if DEBUG:
                print(f"  ℹ️ Using custom domain: {domain}")

        try:
            if DEBUG:
                print(f"  📡 Creating email with params: {params}")

            res = self._make_request("POST", endpoint, params=params)
            if 'email' not in res:
                raise Exception(f"Could not extract email from response: {res}")

            email_data = res['email']
            # Extract email address from response (handle different response formats)
            self.email = email_data.get("address")
            self.email_id = email_data.get("id")

            if not self.email:
                raise Exception(f"Could not extract email from response: {email_data}")

            print(f"  ✓ Created Boomlify email: {self.email}")
            if DEBUG:
                print(f"  📦 Full response: {json.dumps(email_data, indent=2)}")

            return self.email

        except Exception as e:
            print(f"  ❌ Boomlify error: {e}")

    def get_messages(self):
        """
        Get all messages for the current email address.

        REAL ENDPOINT: GET /api/v1/emails/{id}/messages
        """
        if not self.email_id:
            raise Exception("Could not find email ID in creation response")

        endpoint = f"/api/v1/emails/{self.email_id}/messages"

        try:
            if DEBUG:
                print(f"  📡 GET {self.base_url}{endpoint}")

            response = requests.get(
                f"{self.base_url}{endpoint}",
                headers=self.headers
            )

            if response.status_code == 200:
                messages = response.json().get('messages')
                if DEBUG:
                    print(f"  ✅ Found {len(messages) if isinstance(messages, list) else 'some'} messages")
                return messages if isinstance(messages, list) else []
            elif response.status_code == 401:
                raise Exception("Unauthorized - check your API key")
            elif response.status_code == 404:
                print(f"  📭 No messages found or invalid email ID")
                return []
            else:
                response.raise_for_status()

        except Exception as e:
            if DEBUG:
                print(f"  ⚠️ Error getting messages: {e}")
            return []

    @staticmethod
    def extract_verification_code(html_content: str) -> Optional[str]:
        """
        Extracts the 6‑digit verification code from the HTML email body.

        Args:
            html_content: HTML content of the email

        Returns:
            6-digit verification code or None if not found
        """
        if not html_content:
            return None

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Try to find code in styled div (common pattern)
            code_div = soup.find('div', style=lambda s: s and '#667eea' in s and 'border' in s)
            if code_div:
                span = code_div.find('span')
                if span:
                    code = span.get_text(strip=True)
                    if code and code.isdigit() and len(code) == 6:
                        return code

            # Try to find any 6-digit number in the body
            # Look for patterns like: verification code is 123456 or 123456 is your code
            text_content = soup.get_text()

            # Pattern 1: Standalone 6-digit number
            match = re.search(r'\b(\d{6})\b', text_content)
            if match:
                return match.group(1)

            # Pattern 2: Code in context
            patterns = [
                r'verification code[:\s]*(\d{6})',
                r'code[:\s]*(\d{6})',
                r'pin[:\s]*(\d{6})',
                r'(\d{6})\s+is your',
                r'your.*?(\d{6})'
            ]

            for pattern in patterns:
                match = re.search(pattern, text_content, re.IGNORECASE)
                if match:
                    return match.group(1)

            # Last resort: find any 6-digit number
            numbers = re.findall(r'\b\d{6}\b', text_content)
            if numbers:
                return numbers[0]

        except Exception as e:
            if DEBUG:
                print(f"  ⚠️ Error extracting code: {e}")

        return None

    def get_verification_code(self, timeout: int = 300, since: Optional[datetime] = None) -> Optional[str]:
        """
        Wait for and extract a verification code from incoming emails.

        Args:
            timeout: Maximum time to wait in seconds
            since: Only consider emails after this datetime

        Returns:
            Verification code or None if not found
        """
        if not self.email:
            raise Exception("No email generated. Call generate_email() first.")

        print(f"  ⏳ Waiting for verification code (timeout: {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Check for new messages
                messages = self.get_messages()
                for msg in messages:
                    body = msg.get('body_html')
                    if body:
                        if since:
                            timestamp = msg.get('received_at')
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            if since > dt:
                                continue
                        verify_code = self.extract_verification_code(body)
                        if verify_code:
                            print(f"  ✅ Found verification code: {verify_code}")
                            return verify_code

                # Show progress
                elapsed = int(time.time() - start_time)
                print(f"  ⏱️  {elapsed}s elapsed - No verification code yet...", end="\r")

                # Wait before next check
                time.sleep(3)

            except Exception as e:
                if DEBUG:
                    print(f"  ⚠️ Error checking messages: {e}")
                time.sleep(5)

        print(f"\n  ⏰ Timeout reached after {timeout} seconds")
        return None

    def delete_inbox(self):
        """
        Delete the current temporary email inbox.

        DELETE /api/v1/emails/{id}

        Returns:
            Dict: Response from the API confirming deletion
        """
        if not self.email_id:
            print("No email ID available. Call generate_email() first.")

        endpoint = f"/api/v1/emails/{self.email_id}"

        if DEBUG:
            print(f"  📡 DELETE {self.base_url}{endpoint}")

        try:
            response = requests.delete(
                f"{self.base_url}{endpoint}",
                headers=self.headers
            )

            if response.status_code in [200, 204]:
                result = response.json() if response.content else {"status": "deleted"}
                if DEBUG:
                    print(f"  ✅ Inbox deleted successfully")

                # Clear local state
                self.email = None
                self.email_id = None
                return result

            elif response.status_code == 401:
                raise Exception("Unauthorized - invalid API key")
            elif response.status_code == 404:
                raise Exception(f"Email ID {self.email_id} not found")
            else:
                response.raise_for_status()

        except Exception as e:
            if DEBUG:
                print(f"  ⚠️ Error deleting inbox: {e}")

# ==================== REST OF SCRIPT ====================

class SessionManager:
    """Manages session rotation and fingerprint changes"""

    @staticmethod
    def generate_fingerprint() -> Dict[str, str]:
        """Generate new device fingerprint with enhanced entropy and realistic attributes"""

        # Use more entropy sources for fingerprint ID
        import secrets
        import platform
        import hashlib
        import time
        import random

        # Generate cryptographically strong fingerprint ID
        entropy_sources = [
            secrets.token_bytes(32),
            str(uuid.uuid4()),
            str(time.time_ns()),
            str(random.getrandbits(128)),
            str(platform.processor()),
            str(secrets.randbits(256))
        ]

        # FIX: Convert all sources to strings before joining
        fingerprint_id = hashlib.blake2b(
            "".join(str(s) for s in entropy_sources).encode(),  # Convert each item to string
            digest_size=32
        ).hexdigest()

        # Expanded and more realistic resolutions
        resolutions = [
            # Desktop
            "1920x1080", "1366x768", "1536x864", "1440x900",
            "1280x720", "1600x900", "2560x1440", "3840x2160",
            "1680x1050", "1280x1024", "1920x1200", "2560x1600",
            # Mobile/Tablet
            "375x812", "390x844", "414x896", "360x800",
            "768x1024", "810x1080", "1280x800", "1920x1080"
        ]

        # Weighted timezone selection (more realistic distribution)
        timezones = {
            "Europe/Moscow": 0.25,
            "Europe/Kiev": 0.15,
            "Europe/Minsk": 0.10,
            "Asia/Yerevan": 0.05,
            "Europe/London": 0.10,
            "Europe/Berlin": 0.10,
            "America/New_York": 0.10,
            "America/Los_Angeles": 0.05,
            "Asia/Dubai": 0.05,
            "Asia/Singapore": 0.05
        }

        # Weighted language selection with common combinations
        languages = {
            "en-US,en;q=0.9": 0.25,
            "ru-RU,ru;q=0.9,en;q=0.8": 0.20,
            "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7": 0.15,
            "en-GB,en;q=0.9": 0.10,
            "de-DE,de;q=0.9,en;q=0.8": 0.08,
            "fr-FR,fr;q=0.9,en;q=0.8": 0.07,
            "es-ES,es;q=0.9,en;q=0.8": 0.05,
            "ar-AE,ar;q=0.9,en;q=0.8": 0.05,
            "zh-CN,zh;q=0.9,en;q=0.8": 0.05
        }

        # Expanded user agents with more browsers and versions
        user_agents = [
            # Firefox
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",

            # Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",

            # Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",

            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
        ]

        # Additional fingerprint attributes for stronger identification
        platforms = ["Windows", "macOS", "Linux", "iOS", "Android"]
        architectures = ["x86", "x64", "arm", "arm64"]
        browsers = ["Chrome", "Firefox", "Safari", "Edge"]

        # WebGL renderer variations (spoofing)
        webgl_renderers = [
            "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0)",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
            "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0)",
            "Apple M1 GPU",
            "Apple M2 GPU",
            "Intel Iris OpenGL Engine"
        ]

        # Canvas fingerprint variations
        canvas_hashes = [
            hashlib.md5(f"canvas_fingerprint_{secrets.token_hex(8)}".encode()).hexdigest()
            for _ in range(10)
        ]

        # AudioContext fingerprint variations
        audio_hashes = [
            hashlib.md5(f"audio_fingerprint_{secrets.token_hex(8)}".encode()).hexdigest()
            for _ in range(10)
        ]

        # Generate random but consistent additional attributes
        def weighted_choice(choices_dict):
            items = list(choices_dict.items())
            values, weights = zip(*items)
            return random.choices(values, weights=weights)[0]

        # Generate realistic created_at with some timezone offset consideration
        created_at = int(time.time() * 1000)

        # Determine device type based on resolution
        selected_resolution = random.choice(resolutions)
        device_type = "mobile" if int(selected_resolution.split('x')[0]) < 800 else "desktop"

        # --- CHANGE STARTS HERE ---
        # Return fingerprint in API-expected format
        fingerprint = {
            "ua": random.choice(user_agents),  # was "user_agent"
            "lang": weighted_choice(languages),  # was "language"
            "scr": f"{selected_resolution}x24",  # was "resolution", add color depth
            "dpr": round(random.uniform(1.0, 3.0), 1),  # NEW: device pixel ratio
            "tz": weighted_choice(timezones),  # was "timezone" (keep same)
            "tzo": random.randint(-720, 720),  # NEW: timezone offset in minutes
            "plt": random.choice(platforms),  # was "platform"
            "hc": random.choice([2, 4, 6, 8, 12, 16]),  # was "hardware_concurrency"
            "dm": random.choice([2, 4, 8, 16, 32]),  # was "device_memory"
            "tp": 1 if device_type == "mobile" else 0,  # NEW: touch points
            "cvs": random.choice(canvas_hashes),  # was "canvas_hash"
            "wgl": random.choice(webgl_renderers),  # was "webgl_renderer"
            "aud": f"{random.choice([44100, 48000])}|{random.choice([2, 4, 6])}|{random.choice([1024, 2048, 4096])}",
            "did": fingerprint_id,  # was "fingerprint"
            "idb": hashlib.md5(f"idb_{fingerprint_id}".encode()).hexdigest()[:20],  # NEW: indexedDB fingerprint
            "fonts": "Arial,Helvetica,Georgia,Times New Roman,Verdana",  # NEW: simplified font list
            "mq": f"prefers-color-scheme:{random.choice(['dark', 'light'])}",  # NEW: media queries
            "nav": f"ce:{1 if random.random() > 0.05 else 0},dnt:{random.choice([0, 1])},pdf:1,wd:0",
        }

        return fingerprint

    @staticmethod
    def generate_session_id() -> str:
        """Generate session ID"""
        return base64.b64encode(
            f"{int(time.time())}{random.randint(1000, 9999)}".encode()
        ).decode()[:32]

class TVTeamAccount:
    """Complete TV.Team account management with username/password registration and login"""

    def __init__(self, proxy: Optional[str] = None,
                 enable_erotica: bool = True,
                 playlist_app_id: int = 41):
        self.base_url = "https://new.tv.team"
        self.session = requests.Session()
        self.enable_erotica = enable_erotica
        self.playlist_app_id = playlist_app_id

        # Generate fresh fingerprint
        self.fingerprint_data = SessionManager.generate_fingerprint()
        self.session_id = SessionManager.generate_session_id()

        # Setup proxy
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            if DEBUG: print(f"  🔗 Using proxy: {proxy[:50]}...")

        # SSL handling
        self.session.verify = False

        # Setup headers
        self.setup_headers()

        # Account state
        self.account_created = False
        self.csrf_token = None
        self.is_authenticated = False
        self.username = None
        self.password = None
        self.email = None

        if DEBUG:
            print(f"  🆕 New session created")
            print(f"  Fingerprint: {self.fingerprint_data['did'][:20]}...")
            print(f"  User Agent: {self.fingerprint_data['ua'][:50]}...")

    def setup_headers(self):
        """Setup headers with fingerprint"""
        headers = {
            "User-Agent": self.fingerprint_data["ua"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": f"{self.fingerprint_data['lang']};q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Device-Fingerprint": self.fingerprint_data["did"],
            "X-Session-Id": self.session_id,
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/login",
        }

        self.session.headers.update(headers)

    def human_delay(self, min_sec=0.5, max_sec=2.0):
        """Human-like delay"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return delay

    def safe_request(self, method, url, max_retries=3, debug=False, **kwargs):
        """Make request with retries and delays"""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    if DEBUG: print(f"  ⏳ Retry {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    self.human_delay(1, 3)

                if "referer" not in kwargs:
                    if "login" in url:
                        self.session.headers["Referer"] = f"{self.base_url}/login"
                    elif "packages" in url:
                        self.session.headers["Referer"] = f"{self.base_url}/packages"
                    else:
                        self.session.headers["Referer"] = self.base_url

                if debug or DEBUG:
                    print(f"  🔍 Request: {method} {url}")
                    if "headers" in kwargs:
                        print(f"  Headers: {kwargs['headers']}")
                    if "data" in kwargs:
                        d = kwargs['data']
                        print(f"  Data: {d[:200] if isinstance(d, list) else d}...")

                resp = self.session.request(method, url, timeout=30, **kwargs)

                if debug or DEBUG:
                    print(f"  Response Status: {resp.status_code}")
                    print(f"  Response Headers: {dict(resp.headers)}")
                    print(f"  Response Preview: {resp.text[:500]}...")

                if resp.status_code == 429:
                    if DEBUG: print(f"  ⚠️ Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                    continue

                if resp.status_code >= 500:
                    if DEBUG: print(f"  ⚠️ Server error {resp.status_code}, retrying...")
                    continue

                return resp

            except Exception as e:
                if DEBUG: print(f"  ⚠️ Request error: {str(e)[:100]}, retrying... ({attempt + 1}/{max_retries})")
                continue

        return None

    def get_captcha(self) -> Optional[Dict]:
        """Get captcha"""
        if DEBUG: print("  🔍 Getting captcha...")
        resp = self.safe_request("GET", f"{self.base_url}/v3/auth/captcha/generate", debug=False)

        if not resp:
            if DEBUG: print(f"  ❌ Failed to get captcha: No response")
            return None

        if DEBUG: print(f"  Captcha response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Failed to get captcha: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return None

        try:
            data = resp.json()
            if "data" in data:
                captcha_data = data.get("data")
                if captcha_data:
                    if DEBUG: print(f"  ✓ Got captcha ID: {captcha_data.get('captchaId', 'N/A')[:20]}...")
                    return captcha_data
                else:
                    if DEBUG: print(f"  ❌ No data in captcha response")
            else:
                if DEBUG: print(f"  ❌ No 'data' field in captcha response")
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing captcha: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")

        return None

    def calculate_slider_offset(self, challenge_data: Dict[str, Any]) -> int:
        """
        Deterministically compute the correct offset using edge‑based template matching
        restricted to a realistic range (x >= 30). Raises an exception if matching fails.
        """
        try:
            base_b64 = challenge_data["baseImage"].split(',', 1)[-1]
            piece_b64 = challenge_data["pieceImage"].split(',', 1)[-1]

            base_bytes = base64.b64decode(base_b64)
            piece_bytes = base64.b64decode(piece_b64)

            base_pil = Image.open(BytesIO(base_bytes)).convert('RGB')
            base_img = cv2.cvtColor(np.array(base_pil), cv2.COLOR_RGB2BGR)

            piece_pil = Image.open(BytesIO(piece_bytes)).convert('RGBA')
            piece_arr = np.array(piece_pil)
            piece_rgb = piece_arr[:, :, :3]
            piece_alpha = piece_arr[:, :, 3]

            if np.all(piece_alpha == 0):
                mask = (np.sum(piece_rgb, axis=2) > 0).astype(np.uint8) * 255
                if DEBUG:
                    print(f"  ⚠️ Alpha all zeros, created mask from RGB, non‑zero pixels: {np.count_nonzero(mask)}")
            else:
                mask = piece_alpha

            if np.count_nonzero(mask) == 0:
                raise ValueError("Piece has no visible pixels")

            coords = np.column_stack(np.where(mask > 0))
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0) + 1
            piece_crop = piece_rgb[y0:y1, x0:x1]
            mask_crop = mask[y0:y1, x0:x1]

            base_gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
            piece_gray = cv2.cvtColor(piece_crop, cv2.COLOR_BGR2GRAY)

            base_edges = cv2.Canny(base_gray, 50, 150)
            piece_edges = cv2.Canny(piece_gray, 50, 150)
            piece_edges = cv2.bitwise_and(piece_edges, piece_edges, mask=mask_crop)

            result = cv2.matchTemplate(base_edges, piece_edges, cv2.TM_SQDIFF, mask=mask_crop)

            start_x = 30
            base_w = base_edges.shape[1]
            piece_w = piece_edges.shape[1]
            end_x = base_w - piece_w

            result[:, :start_x] = 1e9
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            offset_x = min_loc[0]

            if offset_x < start_x or offset_x > end_x:
                raise ValueError(f"Match outside allowed range: {offset_x}")

            if min_val > 1e8:
                raise ValueError(f"Match score too high: {min_val}")

            offset_x += random.randint(-1, 1)
            offset_x = max(start_x, min(offset_x, end_x))

            if DEBUG:
                print(f"  ✓ Image‑based offset: {offset_x} (score: {min_val:.2f})")
            return offset_x

        except Exception as e:
            raise RuntimeError(f"Could not determine captcha offset: {e}")

    def generate_trail(self, target_x: int) -> List[Dict[str, int]]:
        """
        Generate a realistic drag trail with acceleration, deceleration,
        optional overshoot, and a final hold.
        """
        trail = []
        trail.append({"x": 0, "t": 0})

        drag_time = random.randint(800, 1500)
        steps = random.randint(20, 30)

        times = sorted([random.randint(10, drag_time) for _ in range(steps)])
        times = [0] + times + [drag_time]

        for t in times[1:]:
            progress = t / drag_time
            x = target_x * (1 - (1 - progress) ** 2)
            noise = random.randint(-2, 2)
            x_candidate = int(round(x + noise))
            prev_x = trail[-1]["x"]
            new_x = max(prev_x, min(target_x, x_candidate))
            trail.append({"x": new_x, "t": t})

        if random.random() < 0.3:
            overshoot_x = min(target_x + random.randint(5, 15), 384 - 44)
            overshoot_t = drag_time + random.randint(50, 150)
            trail.append({"x": overshoot_x, "t": overshoot_t})
            correct_t = overshoot_t + random.randint(50, 150)
            trail.append({"x": target_x, "t": correct_t})
            drag_time = correct_t

        hold_time = drag_time + random.randint(500, 2000)
        trail.append({"x": target_x, "t": hold_time})

        seen = set()
        unique_trail = []
        for p in trail:
            if p["t"] not in seen:
                unique_trail.append(p)
                seen.add(p["t"])
        return unique_trail

    def solve_captcha(self, captcha_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Solve captcha with dynamic offset and realistic trail."""
        captcha_id = captcha_data.get("captchaId")
        challenge = captcha_data.get("challenge", {})

        if not captcha_id:
            return None, None

        offset_x = self.calculate_slider_offset(challenge)
        trail = self.generate_trail(offset_x)

        payload = {
            "captchaId": captcha_id,
            "offsetX": offset_x,
            "trail": trail
        }

        if DEBUG: print(f"  Payload: {payload}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/captcha/verify",
            json=payload,
            headers={"Content-Type": "application/json"},
            debug=False
        )

        if not resp or resp.status_code != 200:
            return None, None

        try:
            result = resp.json()
            if "data" in result and "proof" in result["data"]:
                proof_token = result["data"]["proof"]
                return captcha_id, proof_token
        except:
            pass
        return None, None

    def register_start(self, login: str, password: str, email: str) -> bool:
        """Start registration with login, password and email"""
        print(f"  📝 Registering {login} <{email}>...")

        captcha_data = self.get_captcha()
        if not captcha_data:
            if DEBUG: print("  ❌ Could not get captcha data")
            return False

        captcha_id, proof_token = self.solve_captcha(captcha_data)
        if not captcha_id or not proof_token:
            if DEBUG: print("  ❌ Could not solve captcha")
            return False

        form_data = f"login={quote(login)}&password={quote(password)}&email={quote(email)}&captchaId={quote(captcha_id)}&captchaSolution={quote(proof_token)}&lang=US"

        if DEBUG: print(f"  Registration form data: {form_data[:200]}...")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/register/start",  # CHANGED: removed /register, added /register/start
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            debug=False
        )

        if not resp:
            if DEBUG: print(f"  ❌ Registration start failed: No response")
            return False

        if DEBUG: print(f"  Registration response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Registration start failed: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return False

        try:
            result = resp.json().get("data", {})
            if "ok" in result and result["ok"] or "success" in result and result["success"]:
                if DEBUG: print(f"  ✓ Registration started successfully")
                return True
            else:
                if DEBUG: print(f"  ❌ Registration not successful according to response")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing registration response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def register_verify(self, login: str, email: str, code: str) -> bool:
        """Verify email with the given code"""
        print(f"  ✅ Verifying with code {code}...")
        form_data = f"login={quote(login)}&email={quote(email)}&code={code}&lang=US"

        if DEBUG: print(f"  Verification form data: {form_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/register/verify",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            debug=False
        )

        if not resp:
            if DEBUG: print(f"  ❌ Verification failed: No response")
            return False

        if DEBUG: print(f"  Verification response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Verification failed: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return False

        try:
            result = resp.json().get("data", {})
            if "ok" in result and result["ok"] or "success" in result and result["success"]:
                print(f"  🎉 Account verified successfully!")
                self.account_created = True
                return True
            else:
                if DEBUG: print(f"  ❌ Verification not successful according to response")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing verification response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def login(self, username: str, password: str) -> bool:
        """
        Perform username/password login.
        """
        print(f"  🔐 Logging in as {username}...")

        captcha_data = self.get_captcha()
        if not captcha_data:
            if DEBUG: print("  ❌ Could not get CAPTCHA for login")
            return False

        captcha_id, proof_token = self.solve_captcha(captcha_data)
        if not captcha_id or not proof_token:
            if DEBUG: print("  ❌ Could not solve CAPTCHA for login")
            return False

        form_data = f"userLogin={quote(username)}&userPasswd={quote(password)}&rememberMe=1&captchaId={quote(captcha_id)}&captchaSolution={quote(proof_token)}"

        if DEBUG: print(f"  Login form data: {form_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/login",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            debug=False
        )

        if not resp:
            if DEBUG: print(f"  ❌ Login failed: No response")
            return False

        if DEBUG: print(f"  Login response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Login failed: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return False

        try:
            result = resp.json().get("data", {})
            if "authorized" in result and result["authorized"]:
                print(f"  ✅ Login successful!")
                self.is_authenticated = True
                self.username = username
                self.password = password
                return True
            else:
                if DEBUG: print(f"  ❌ Login failed: {result.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing login response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def get_csrf_token(self) -> Optional[str]:
        """Get CSRF token for authenticated requests"""
        if not self.is_authenticated:
            if DEBUG: print("  ❌ Not authenticated - cannot get CSRF token")
            return None

        resp = self.safe_request("GET", f"{self.base_url}/v3/auth/csrf", debug=False)
        if not resp or resp.status_code != 200:
            if DEBUG: print("  ❌ Failed to get CSRF token")
            return None

        try:
            data = resp.json()
            self.csrf_token = data.get("data", {}).get("csrf", "")
            return self.csrf_token
        except Exception as e:
            if DEBUG: print(f"  ❌ Failed to parse CSRF token: {str(e)[:100]}")
            return None

    def check_trial_status(self) -> Optional[Dict]:
        """Check trial status of the account"""
        if not self.is_authenticated:
            if DEBUG: print("  ❌ Cannot check trial status - not authenticated")
            return None

        print("  📊 Checking trial status...")
        self.session.headers["Referer"] = f"{self.base_url}/packages"
        resp = self.safe_request("GET", f"{self.base_url}/v3/trial/status", debug=False)

        if not resp or resp.status_code != 200:
            if DEBUG: print(f"  ❌ Trial check failed: {resp.status_code if resp else 'No response'}")
            return None

        try:
            data = resp.json()
            trial_data = data.get("data", {})

            if DEBUG:
                print(f"\n  {'=' * 50}")
                print(f"  📋 TRIAL STATUS REPORT")
                print(f"  {'=' * 50}")
                print(f"  Enabled: {trial_data.get('enabled', 'N/A')}")
                print(f"  Eligible: {trial_data.get('eligible', 'N/A')}")
                print(f"  Reason: {trial_data.get('reason', 'N/A')}")
                print(f"  Reason Text: {trial_data.get('reasonText', 'N/A')}")
                print(f"  Has Paid History: {trial_data.get('hasPaidHistory', 'N/A')}")
                print(f"  Ever Had Package: {trial_data.get('everHadPackage', 'N/A')}")
                print(f"  Has Trial History: {trial_data.get('hasTrialHistory', 'N/A')}")
                print(f"  Has Active Trial: {trial_data.get('hasActiveTrial', 'N/A')}")
                print(f"  Remaining Daily: {trial_data.get('remainingDaily', 'N/A')}")
                print(f"  {'=' * 50}")

            if trial_data.get("eligible"):
                print(f"  🎉🎉🎉 ACCOUNT IS ELIGIBLE FOR TRIAL! 🎉🎉🎉")
            else:
                if DEBUG:
                    print(f"  ❌ Account is NOT eligible for trial")
                    print(f"  Reason: {trial_data.get('reasonText', 'Unknown')}")

            return trial_data

        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing trial status: {str(e)[:100]}")
            return None

    def activate_trial(self) -> bool:
        """Activate free trial for the account"""
        if not self.is_authenticated:
            if DEBUG: print("  ❌ Cannot activate trial - not authenticated")
            return False

        print("  🚀 Activating free trial...")
        if not self.get_csrf_token():
            if DEBUG: print("  ❌ Failed to get CSRF token for trial activation")
            return False

        trial_data = {
            "fingerprint": json.dumps(self.fingerprint_data, separators=(',', ':')),
            "userAgent": self.fingerprint_data["ua"]
        }

        if DEBUG: print(f"  Trial activation data: {trial_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/trial/issue",
            json=trial_data,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": self.csrf_token
            },
            debug=False
        )

        if not resp:
            if DEBUG: print("  ❌ Trial activation failed - no response")
            return False

        if DEBUG: print(f"  Trial activation response status: {resp.status_code}")

        if resp.status_code == 200:
            try:
                result = resp.json()
                if result.get("data", {}).get("ok"):
                    print("  🎉 FREE TRIAL ACTIVATED SUCCESSFULLY!")
                    return True
                else:
                    error_msg = result.get("error", {}).get("message", "Unknown error")
                    if DEBUG: print(f"  ❌ Trial activation failed: {error_msg}")
                    return False
            except Exception as e:
                if DEBUG: print(f"  ❌ Error parsing trial response: {str(e)[:100]}")
                return False
        else:
            if DEBUG: print(f"  ❌ Trial activation failed with status: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return False

    def toggle_erotica(self, enable: bool = True) -> bool:
        """Toggle erotica content on/off"""
        if not self.is_authenticated:
            if DEBUG: print("  ❌ Cannot toggle erotica - not authenticated")
            return False

        print(f"  {'🔞' if enable else '🚫'} Setting erotica content to {'ON' if enable else 'OFF'}...")

        if not self.get_csrf_token():
            if DEBUG: print("  ❌ Failed to get CSRF token")
            return False

        erotica_data = {
            "showPorno": "1" if enable else "0"
        }

        if DEBUG: print(f"  Erotica toggle data: {erotica_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/erotica/change",
            json=erotica_data,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": self.csrf_token
            },
            debug=False
        )

        if not resp:
            if DEBUG: print("  ❌ Erotica toggle failed - no response")
            return False

        if DEBUG: print(f"  Erotica toggle response status: {resp.status_code}")

        if resp.status_code == 200:
            try:
                result = resp.json()
                if result.get("data", {}).get("showPorno") == (1 if enable else 0):
                    if DEBUG: print(f"  ✅ Erotica content set to {'ON' if enable else 'OFF'} successfully!")
                    return True
                else:
                    if DEBUG: print(f"  ❌ Erotica toggle failed - unexpected response")
                    return False
            except Exception as e:
                if DEBUG: print(f"  ❌ Error parsing erotica response: {str(e)[:100]}")
                return False
        else:
            if DEBUG: print(f"  ❌ Erotica toggle failed with status: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return False

    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self.is_authenticated:
            if DEBUG: print("  ❌ Cannot get account info - not authenticated")
            return None

        if DEBUG: print("  📋 Getting account information...")
        resp = self.safe_request("GET", f"{self.base_url}/v3/profile", debug=False)

        if not resp or resp.status_code != 200:
            if DEBUG: print(f"  ❌ Failed to get account info: {resp.status_code if resp else 'No response'}")
            return None

        try:
            data = resp.json()
            profile_data = data.get("data", {})
            if DEBUG:
                print(f"  ✓ Account ID: #{profile_data.get('id', 'N/A')}")
                print(f"  ✓ Email: {profile_data.get('email', 'N/A')}")
                print(f"  ✓ Registration: {profile_data.get('regDate', 'N/A')}")
            return profile_data
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing account info: {str(e)[:100]}")
            return None

    def set_playlist_protocol(self, use_https: bool = False) -> bool:
        """Set playlist to HTTP (False) or HTTPS (True)"""
        if not self.is_authenticated:
            return False

        if DEBUG: print(f"  🔗 Setting playlist protocol to {'HTTPS' if use_https else 'HTTP'}...")

        if not self.get_csrf_token():
            return False

        form_data = f"https={'1' if use_https else '0'}"

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/playlists/https",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRF-Token": self.csrf_token
            },
            debug=False
        )

        return resp and resp.status_code == 200

    def get_playlist_session_id(self) -> Optional[str]:
        """Get playlist session ID from new API response structure"""
        if not self.is_authenticated:
            return None

        if DEBUG: print("  🔍 Getting playlist session ID...")

        resp = self.safe_request("GET", f"{self.base_url}/v3/playlists?slot=0", debug=False)

        if not resp or resp.status_code != 200:
            return None

        try:
            data = resp.json().get("data", {})
            uniq_id = data.get("uniqId")
            if uniq_id:
                if DEBUG: print(f"  ✅ Found uniqId: {uniq_id}")
                return uniq_id

            items = data.get("items", [])
            if items:
                for item in items:
                    link = item.get("link", "")
                    if "/pl/" in link:
                        parts = link.split("/")
                        if len(parts) >= 5:
                            token = parts[4]
                            if DEBUG: print(f"  ✅ Found token in link: {token}")
                            return token

            if DEBUG:
                print(f"  ❌ Could not find playlist session ID in response")
                print(f"  Response structure: {data.keys()}")
            return None

        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing playlist response: {str(e)[:100]}")
            return None

    def generate_playlist_url(self, use_https: bool = False) -> Optional[str]:
        """Generate playlist URL"""
        if not self.set_playlist_protocol(use_https):
            return None

        session_id = self.get_playlist_session_id()
        if not session_id:
            return None

        protocol = "https" if use_https else "http"
        playlist_url = f"{protocol}://tvtm.one/pl/{self.playlist_app_id}/{session_id}/playlist.m3u8"

        print(f"  📺 Playlist URL: {playlist_url}")
        return playlist_url

    def check_saved_account_trial(self, username: str, password: str) -> bool:
        """Check if saved account has active trial by logging in and checking"""
        print(f"\n  🔍 Checking trial status for saved account: {username}")

        print(f"  🔐 Attempting to login...")
        if not self.login(username, password):
            print(f"  ❌ Failed to login with saved credentials")
            return False

        print(f"  📊 Checking trial status via website...")
        trial_status = self.check_trial_status()

        if not trial_status:
            if DEBUG: print(f"  ❌ Failed to check trial status")
            return False

        has_active_trial = trial_status.get('hasActiveTrial', False)

        if has_active_trial:
            date_str = trial_status.get('activeTrialExpires', 'N/A')
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            today = date.today()
            if target_date > today:
                print(f"  ✅ Trial is ACTIVE on website till {trial_status.get('activeTrialExpires', 'NA')}")
                return True
        if DEBUG: print(f"  ❌ Trial NOT ACTIVE or eligible")
        return False


class ProxyFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.session.verify = False

    def fetch_proxy_list(self) -> List[str]:
        """Fetch fresh proxies from multiple sources"""
        print("🌐 Fetching proxies from various sources...")

        sources = [
            "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/MostStable/http.txt",
            "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/Stable/http.txt",
            "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt",
            "https://raw.githubusercontent.com/Mohammedcha/ProxRipper/refs/heads/main/full_proxies/http.txt",
            "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        ]
        proxies = []

        for source in sources:
            try:
                resp = self.session.get(source, timeout=10)
                if resp.status_code == 200:
                    source_proxies = []
                    lines = resp.text.strip().split('\n')
                    for line in lines:
                        if ':' in line and not line.startswith('#'):
                            proxy = line.strip()
                            if not proxy.startswith("http"):
                                proxy = f"http://{proxy}"
                            source_proxies.append(proxy)
                    if len(source_proxies) > 100:
                        source_proxies = random.sample(source_proxies, 100)
                    proxies.extend(source_proxies)
                    if DEBUG: print(f"✓ Got {len(lines)} proxies from {source}")
            except Exception as e:
                if DEBUG: print(f"✗ {source} failed: {e}")

        unique_proxies = list(set(proxies))
        if DEBUG: print(f"\n📊 Total unique proxies found: {len(unique_proxies)}")

        return unique_proxies

    def test_proxy(self, proxy: str, timeout: int = 5) -> Tuple[bool, float, str]:
        """Test if a proxy is working"""
        try:
            start_time = time.time()
            test_url = "http://httpbin.org/ip"

            response = requests.get(
                test_url,
                proxies={"http": proxy, "https": proxy},
                timeout=timeout,
                verify=False
            )

            if response.status_code == 200:
                speed = time.time() - start_time
                try:
                    data = response.json().get("data", {})
                    origin = data.get('origin', '')
                except:
                    origin = "unknown"
                return True, speed, origin

        except requests.exceptions.ProxyError:
            return False, 0, ""
        except requests.exceptions.ConnectTimeout:
            return False, 0, ""
        except requests.exceptions.ReadTimeout:
            return False, 0, ""
        except Exception:
            return False, 0, ""

        return False, 0, ""

    def test_proxy_simple(self, proxy: str) -> bool:
        working, speed, origin = self.test_proxy(proxy, timeout=8)
        if working and DEBUG:
            print(f"{proxy} | Speed: {speed}s")
        return working


class AccountManager:
    """Manages saved account information - saves username, password, email"""

    SAVE_FILE = "tvteam_account.json"

    @staticmethod
    def save_account(username: str, password: str, email: str) -> None:
        """Save credentials to file"""
        try:
            account_data = {
                "username": username,
                "password": password,
                "email": email,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(AccountManager.SAVE_FILE, 'w') as f:
                json.dump(account_data, f, indent=2)
            print(f"  ✅ Account credentials saved to {AccountManager.SAVE_FILE}")
        except Exception as e:
            if DEBUG: print(f"  ❌ Failed to save account: {e}")

    @staticmethod
    def load_account() -> Optional[Dict]:
        """Load account info from file"""
        if not os.path.exists(AccountManager.SAVE_FILE):
            return None

        try:
            with open(AccountManager.SAVE_FILE, 'r') as f:
                data = json.load(f)

            required_fields = ['username', 'password', 'email']
            if not all(field in data for field in required_fields):
                if DEBUG: print(f"  ⚠️ Saved account data is incomplete")
                return None

            if DEBUG: print(f"  📁 Loaded saved account: {data['username']}")
            return data
        except Exception as e:
            if DEBUG: print(f"  ❌ Failed to load account: {e}")
            return None


class M3UPlaylistUpdater:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def find_gist_file(self, filename):
        """Find a gist containing the specific filename, return (gist_id, content)"""
        try:
            response = requests.get(
                "https://api.github.com/gists",
                headers=self.headers,
                params={"per_page": 100}
            )

            if response.status_code != 200:
                if DEBUG: print(f"Error getting gists: {response.status_code}")
                return None, None

            gists = response.json()

            for gist in gists:
                files = gist.get('files', {})
                if filename in files:
                    gist_id = gist['id']
                    gist_detail = self.get_gist_detail(gist_id)
                    if gist_detail:
                        files_detail = gist_detail.get('files', {})
                        if filename in files_detail:
                            file_info = files_detail[filename]
                            content = self.get_file_content(file_info, gist_id)
                            return gist_id, content

            return None, None

        except Exception as e:
            if DEBUG: print(f"Error finding gist: {e}")
            return None, None

    def get_gist_detail(self, gist_id):
        """Get detailed gist info"""
        try:
            response = requests.get(
                f"https://api.github.com/gists/{gist_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None

    def get_file_content(self, file_info, gist_id):
        """Get file content, handling truncated content"""
        if file_info.get('content') and not file_info.get('truncated', False):
            return file_info['content']

        raw_url = file_info.get('raw_url')
        if raw_url:
            try:
                response = requests.get(raw_url)
                if response.status_code == 200:
                    return response.text
            except:
                pass

        try:
            raw_url_alt = f"https://gist.githubusercontent.com/anon/{gist_id}/raw/{file_info.get('filename', 'file')}"
            response = requests.get(raw_url_alt)
            if response.status_code == 200:
                return response.text
        except:
            pass

        return ""

    def update_gist(self, gist_id, filename, new_content):
        """Update existing gist"""
        data = {
            "files": {
                filename: {"content": new_content}
            }
        }

        try:
            response = requests.patch(
                f"https://api.github.com/gists/{gist_id}",
                json=data,
                headers=self.headers
            )

            if response.status_code == 200:
                gist = response.json()
                raw_url = f"https://gist.githubusercontent.com/anon/{gist_id}/raw/{filename}"
                return True, raw_url
            else:
                if DEBUG: print(f"Error updating gist: {response.status_code}")
                return False, None
        except Exception as e:
            if DEBUG: print(f"Error: {e}")
            return False, None

    def parse_m3u_playlist(self, content):
        """
        Parse M3U playlist into structured data
        """
        channels = OrderedDict()
        lines = content.strip().split('\n')

        i = 0
        channel_index = 0

        if lines and lines[0].startswith('#EXTM3U'):
            channels['header'] = lines[0]
            i = 1
        else:
            channels['header'] = '#EXTM3U'

        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            if line.startswith('#EXTINF:'):
                extinf_line = line
                group_line = ""
                if i + 1 < len(lines) and lines[i + 1].startswith('#EXTGRP:'):
                    group_line = lines[i + 1].strip()
                    i += 1

                url_line = ""
                if i + 1 < len(lines) and lines[i + 1].startswith('http'):
                    url_line = lines[i + 1].strip()
                    i += 1

                duration_match = re.search(r'#EXTINF:([\d.-]+)', extinf_line)
                duration = duration_match.group(1) if duration_match else "0"

                attr_pattern = r'(\S+)="([^"]*)"'
                attrs = dict(re.findall(attr_pattern, extinf_line))

                if ',' in extinf_line:
                    channel_name = extinf_line.split(',', 1)[1].strip()
                else:
                    channel_name = ""

                channel_id = attrs.get('tvg-id', '').replace('ch', '')
                if not channel_id and url_line:
                    channel_id = self.extract_channel_id_from_url(url_line)

                group = group_line.replace('#EXTGRP:', '').strip() if group_line else ""

                channel_data = {
                    'index': channel_index,
                    'extinf': extinf_line,
                    'duration': duration,
                    'attrs': attrs,
                    'name': channel_name,
                    'group': group,
                    'url': url_line,
                    'channel_id': channel_id,
                    'raw_lines': [extinf_line, group_line, url_line] if group_line else [extinf_line, url_line]
                }

                key = f"ch{channel_id}" if channel_id else f"channel_{channel_index}"
                channels[key] = channel_data

                channel_index += 1
                i += 1

            else:
                if line and not line.startswith('http'):
                    metadata_key = f"metadata_{i}"
                    channels[metadata_key] = {
                        'type': 'metadata',
                        'line': line,
                        'index': i
                    }
                i += 1

        return channels

    def extract_channel_id_from_url(self, url):
        """Extract channel ID from URL"""
        if not url:
            return None
        match = re.search(r'/ch(\d+)/', url)
        if match:
            return match.group(1)
        match = re.search(r'ch(\d+)', url)
        if match:
            return match.group(1)
        return None

    def extract_token_from_url(self, url):
        """Extract token from URL"""
        if not url:
            return None
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'token' in query_params:
            return query_params['token'][0]
        return None

    def replace_token_in_url(self, url, new_token):
        """Replace token in URL"""
        if not url or not new_token:
            return url
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params['token'] = [new_token]
        new_query = urlencode(query_params, doseq=True)
        new_url = parsed_url._replace(query=new_query).geturl()
        return new_url

    def download_playlist(self, playlist_url):
        """Download playlist from URL"""
        try:
            response = requests.get(playlist_url, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                if DEBUG: print(f"Failed to download playlist: {response.status_code}")
                return None
        except Exception as e:
            if DEBUG: print(f"Error downloading playlist: {e}")
            return None

    def update_channels_from_reference(self, gist_channels, reference_channels):
        """
        Update gist channels with tokens from reference channels
        """
        change_count = 0
        updated_channels = OrderedDict()

        for key, value in gist_channels.items():
            if key == 'header':
                updated_channels[key] = value
            elif isinstance(value, dict) and value.get('type') == 'metadata':
                updated_channels[key] = value
            elif isinstance(value, dict) and 'extinf' in value:
                channel_data = value.copy()
                channel_id = channel_data.get('channel_id')

                if channel_id and channel_id in reference_channels:
                    ref_channel = reference_channels[channel_id]
                    ref_token = self.extract_token_from_url(ref_channel.get('url', ''))
                    current_token = self.extract_token_from_url(channel_data.get('url', ''))

                    if ref_token and current_token != ref_token:
                        new_url = ref_channel.get('url', '')
                        channel_data['url'] = new_url
                        if 'raw_lines' in ref_channel:
                            channel_data['raw_lines'] = ref_channel['raw_lines']
                        else:
                            for j, line in enumerate(channel_data['raw_lines']):
                                if line == channel_data.get('url', ''):
                                    channel_data['raw_lines'][j] = new_url
                        change_count += 1

                updated_channels[key] = channel_data
            else:
                updated_channels[key] = value

        return updated_channels, change_count

    def reconstruct_m3u_from_channels(self, channels):
        """Reconstruct M3U playlist from channel data"""
        lines = []
        if 'header' in channels:
            lines.append(channels['header'])

        items_to_sort = []
        for key, value in channels.items():
            if key == 'header':
                continue
            if isinstance(value, dict):
                if 'index' in value:
                    items_to_sort.append((value['index'], key, value))
                else:
                    items_to_sort.append((999999, key, value))

        items_to_sort.sort(key=lambda x: x[0])

        for _, key, value in items_to_sort:
            if isinstance(value, dict) and value.get('type') == 'metadata':
                lines.append(value['line'])
            elif isinstance(value, dict) and 'extinf' in value:
                lines.extend(value['raw_lines'])

        return '\n'.join(lines)

    def update_gist_with_playlist(self, gist_filename, playlist_url):
        """Update a specific gist file with tokens from playlist URL"""
        print(f"\n{'=' * 80}")
        print("🎬 M3U Playlist Token Updater")
        print(f"📁 Gist file: '{gist_filename}'")
        print(f"🔗 Reference: {playlist_url}")
        print("=" * 80)

        print(f"\n🔍 Searching for gist '{gist_filename}'...")
        gist_id, gist_content = self.find_gist_file(gist_filename)

        if not gist_id:
            print(f"❌ No gist found containing '{gist_filename}'")
            return False

        print(f"✓ Found gist: {gist_id}")

        if DEBUG: print("📝 Parsing gist M3U playlist...")
        gist_channels = self.parse_m3u_playlist(gist_content)

        gist_channel_count = len([v for v in gist_channels.values()
                                  if isinstance(v, dict) and 'extinf' in v])
        if DEBUG: print(f"📊 Gist contains {gist_channel_count} channels")

        print(f"\n🌐 Downloading reference playlist...")
        playlist_content = self.download_playlist(playlist_url)

        if not playlist_content:
            print("❌ Failed to download reference playlist")
            return False

        if DEBUG: print("📝 Parsing reference M3U playlist...")
        reference_channels = self.parse_m3u_playlist(playlist_content)

        ref_channel_count = len([v for v in reference_channels.values()
                                 if isinstance(v, dict) and 'extinf' in v])
        if DEBUG: print(f"📊 Reference contains {ref_channel_count} channels")

        ref_lookup = {}
        for key, value in reference_channels.items():
            if isinstance(value, dict) and 'extinf' in value:
                channel_id = value.get('channel_id')
                if channel_id:
                    ref_lookup[channel_id] = value

        if DEBUG: print(f"📋 Reference has {len(ref_lookup)} unique channel IDs")

        if DEBUG and ref_lookup:
            print("\n📋 Sample reference channels:")
            sample_ids = list(ref_lookup.keys())[:3]
            for ch_id in sample_ids:
                channel = ref_lookup[ch_id]
                name = channel.get('name', 'Unknown')
                token = self.extract_token_from_url(channel.get('url', ''))
                if token:
                    print(f"  • ch{ch_id}: {name[:30]}...")
                    print(f"    Token: {token[:40]}...")

        if DEBUG: print(f"\n🔄 Comparing and updating channels...")
        updated_channels, change_count = self.update_channels_from_reference(
            gist_channels, ref_lookup
        )

        if change_count == 0:
            print("\n✅ No updates needed - all tokens are current")
            return True

        print(f"\n📈 Updated {change_count} channel(s)")

        if DEBUG:
            print("\n📝 Detailed changes:")
            changes_shown = 0
            for key, channel in updated_channels.items():
                if isinstance(channel, dict) and 'extinf' in channel:
                    channel_id = channel.get('channel_id')
                    if channel_id in ref_lookup:
                        original_channel = None
                        for orig_key, orig_val in gist_channels.items():
                            if isinstance(orig_val, dict) and 'extinf' in orig_val:
                                if orig_val.get('channel_id') == channel_id:
                                    original_channel = orig_val
                                    break

                        if original_channel:
                            orig_url = original_channel.get('url', '')
                            new_url = channel.get('url', '')
                            if orig_url != new_url:
                                orig_token = self.extract_token_from_url(orig_url) or "NO_TOKEN"
                                new_token = self.extract_token_from_url(new_url) or "NO_TOKEN"
                                name = channel.get('name', 'Unknown')[:30]
                                print(f"\n  📺 ch{channel_id}: {name}...")
                                print(f"    Old token: ...{orig_token[-30:]}")
                                print(f"    New token: ...{new_token[-30:]}")
                                changes_shown += 1

                                if changes_shown >= 5:
                                    print(f"\n    ... and {change_count - changes_shown} more changes")
                                    break

        if DEBUG: print(f"\n🔧 Reconstructing M3U playlist...")
        new_m3u_content = self.reconstruct_m3u_from_channels(updated_channels)

        old_lines = [l for l in gist_content.strip().split('\n') if l.strip()]
        new_lines = [l for l in new_m3u_content.strip().split('\n') if l.strip()]

        if DEBUG:
            print(f"✅ Reconstruction successful")
            print(f"   Original non-empty lines: {len(old_lines)}")
            print(f"   New non-empty lines: {len(new_lines)}")

        print(f"\n💾 Uploading updated playlist to gist...")
        success, raw_url = self.update_gist(gist_id, gist_filename, new_m3u_content)

        if success:
            print(f"✅ Gist updated successfully!")
            if DEBUG:
                print(f"🔗 Raw URL: {raw_url}")
                print(f"🆔 Gist ID: {gist_id}")
            return True
        else:
            print("❌ Failed to update gist")
            return False

def main():
    global DEBUG
    DEBUG = False

    if '--debug' in sys.argv:
        DEBUG = True
        print("🔧 Debug mode enabled")

    print(f"\n🎯 TV.Team Account Manager & Gist Updater")
    print(f"⚙️ Configuration: Erotica enabled by default, using MailSlurper")
    print(f"{'=' * 60}")

    ENABLE_EROTICA = True
    TIVIMATE_ID = 41
    GITHUB_TOKEN = ""
    GIST_FILES = ["file4", "file5"]

    playlist_url = None
    account_data = None

    # ============================================
    # FIRST: Check saved account WITHOUT proxy
    # ============================================
    saved_account = AccountManager.load_account()
    if saved_account:
        print(f"\n📋 Checking saved account (no proxy)...")
        check_manager = TVTeamAccount(proxy=None, enable_erotica=ENABLE_EROTICA,
                                      playlist_app_id=TIVIMATE_ID)
        has_active_trial = check_manager.check_saved_account_trial(
            saved_account['username'], saved_account['password']
        )

        if has_active_trial and '--force' not in sys.argv:
            print(f"\n{'=' * 60}")
            print(f"✅ USING EXISTING ACCOUNT WITH ACTIVE TRIAL")
            print(f"{'=' * 60}")
            print(f"  👤 Username: {saved_account['username']}")
            print(f"  📧 Email: {saved_account['email']}")
            print(f"  🎯 Trial: ACTIVE")
            print(f"  💾 Loaded from: {AccountManager.SAVE_FILE}")
            account_data = saved_account
        else:
            print(f"\n⚠️ Saved account trial expired or not active, creating new account...")
    else:
        print(f"\n📭 No saved account found, creating new account...")

    # ============================================
    # SECOND: Create new account with proxies, using a SINGLE email
    # ============================================
    if not account_data:
        print(f"\n🔄 Creating new account with proxies...")

        # Create one temp mail service for all attempts
        temp_mail_service = TempMailService(api_key=MAIL_API_KEY)
        email = None

        fetcher = ProxyFetcher()
        proxies = fetcher.fetch_proxy_list()

        if not proxies:
            proxies = [None]
            print("⚠️ No proxies found, using direct connection")

        print(f"\n📋 Loaded {len(proxies)} proxies")

        for current_proxy in proxies:
            try:
                print(f"\n{'=' * 50}")
                print(f"🔄 Attempting account creation with proxy: {current_proxy if current_proxy else 'Direct'}")
                print(f"{'=' * 50}")

                if current_proxy:
                    if not fetcher.test_proxy_simple(current_proxy):
                        if DEBUG: print("❌ Proxy not working, skipping...")
                        continue

                if not email:
                    # https://boomlify.com/en/edu-temp-mail
                    temp_mail_service.delete_inbox()
                    email = temp_mail_service.generate_email(expiration="1hour", domain="dev.nondon.store")
                    # email = input("Enter email: ")
                    if not email:
                        print("❌ Failed to create email. Exiting.")
                        return
                    print(f"✅ Using email: {email} for all proxy attempts")

                # Create account manager WITHOUT temp mail instance
                account_manager = TVTeamAccount(proxy=current_proxy, enable_erotica=ENABLE_EROTICA,
                                                playlist_app_id=TIVIMATE_ID)

                # Generate human-like login name and password (password length 10-32)
                first_names = ["john", "jane", "mike", "lisa", "david", "emma", "chris", "sarah", "alex", "anna"]
                login = random.choice(first_names) + str(random.randint(100, 999))          # e.g., jane42
                base_word = random.choice(first_names).capitalize()                       # e.g., Lisa
                digits = str(random.randint(1000, 9999))
                password = base_word + digits# 4 digits
                while len(password) < 10:                                                 # ensure at least 10 chars
                    password += random.choice("0123456789")
                password += "$"
                # (max length 32 is naturally satisfied with this pattern)

                # Step 1: Start registration using the correct endpoint and field name 'login'
                registration_start_time = datetime.now(timezone.utc)
                if not account_manager.register_start(login, password, email):
                    print("  ❌ Registration start failed, trying next proxy...")
                    continue

                # Step 2: Get verification code from shared temp mail
                code = temp_mail_service.get_verification_code(timeout=180, since=registration_start_time)
                # code = input("Enter verification code: ")
                if not code:
                    print("  ❌ No verification code received, trying next proxy...")
                    continue

                # Step 3: Verify email
                if not account_manager.register_verify(login, email, code):
                    print("  ❌ Email verification failed, trying next proxy...")
                    continue

                # Step 4: Login (still uses username/password – login is the same string)
                if not account_manager.login(login, password):
                    email = None
                    print("  ❌ Login failed after registration, trying next proxy...")
                    continue

                # Step 5: Check trial status
                trial_status = account_manager.check_trial_status()
                if trial_status and trial_status.get("eligible"):
                    trial_activated = account_manager.activate_trial()
                else:
                    if DEBUG: print("  ⚠️ Account not eligible for trial")
                    email = None
                    continue
                if not trial_activated:
                    email = None
                    continue

                # Step 6: Toggle erotica
                if ENABLE_EROTICA:
                    account_manager.toggle_erotica(enable=True)

                # Step 7: Generate playlist URL
                playlist_url = account_manager.generate_playlist_url(use_https=False)

                if playlist_url:
                    print(f"\n🎉🎉🎉 SUCCESS: New account created WITH TRIAL ACTIVATED! 🎉🎉🎉")
                    account_data = {
                        "username": login,          # stored as 'username' in the JSON
                        "password": password,
                        "email": email,
                        "trial_activated": trial_activated,
                        "playlist_url": playlist_url
                    }
                    # Save account – the method's first parameter is named 'username', we pass our login variable
                    AccountManager.save_account(login, password, email)
                    break
                else:
                    print("  ❌ Failed to generate playlist URL, trying next proxy...")

            except Exception as e:
                if DEBUG:
                    print(f"\n💥 Unexpected error: {e}")
                    import traceback
                    traceback.print_exc()
                continue

        # Clean up the email inbox after all attempts
        # temp_mail_service.delete_inbox()

        # Final summary
        print(f"\n\n{'=' * 60}")
        print(f"📈 FINAL RESULTS")
        print(f"{'=' * 60}")

        if account_data:
            print(f"\n✅ ACCOUNT STATUS:")
            print(f"   Username: {account_data.get('username')}")
            print(f"   Email: {account_data.get('email')}")
            print(f"   Trial: {'✅ ACTIVE' if account_data.get('trial_activated', False) else '❌ Not active'}")
            if playlist_url:
                print(f"   Playlist URL: {playlist_url}")
        else:
            print(f"\n❌ No valid account available")

    # ============================================
    # THIRD: Update gists with playlist URL
    # ============================================
    if playlist_url:
        print(f"\n{'=' * 60}")
        print(f"🔄 UPDATING GIST FILES")
        print(f"{'=' * 60}")

        updater = M3UPlaylistUpdater(GITHUB_TOKEN)

        for gist_file in GIST_FILES:
            print(f"\n📁 Updating gist file: {gist_file}")
            success = updater.update_gist_with_playlist(gist_file, playlist_url)
            if success:
                print(f"✅ {gist_file} updated successfully")
            else:
                print(f"❌ Failed to update {gist_file}")

        print(f"\n{'=' * 60}")
        print(f"✅ ALL OPERATIONS COMPLETED!")
        print(f"{'=' * 60}")
    else:
        print(f"\n❌ No playlist URL available to update gists")

    print(f"\nTVTeam playlist update {time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        import requests
        from mailslurp_client import Configuration, ApiClient, InboxControllerApi, WaitForControllerApi
        print("✅ All required packages are installed")
    except ImportError as e:
        print(f"❌ Missing package: {e}")
        print("Please install required packages:")
        print("pip install requests mailslurp-client")
        exit(1)

    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    main()