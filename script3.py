import requests
import time
import random
import string
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

warnings.filterwarnings('ignore')


class TempMailService:
    """Service to get temporary emails using mail.tm API"""

    def __init__(self):
        self.email = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        })
        self.account_id = None
        self.token = None
        self.session.verify = False

    def generate_email(self) -> Optional[str]:
        """Generate a random temporary email using mail.tm API"""
        try:
            # First get available domains
            if DEBUG: print("  Getting available domains...")
            response = self.session.get(
                "https://api.mail.tm/domains",
                timeout=10
            )

            if response.status_code != 200:
                if DEBUG: print(f"  Failed to get domains: {response.status_code}")
                if DEBUG: print(f"  Response: {response.text[:200]}")
                return None

            domains_data = response.json()
            domains = domains_data.get('hydra:member', [])

            if not domains:
                if DEBUG: print("  No domains available")
                return None

            # Get first available domain
            domain = domains[0].get('domain')
            if not domain:
                return None

            # Generate random username
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
            email = f"{username}@{domain}"

            # Create account
            account_data = {
                "address": email,
                "password": "".join(random.choices(string.ascii_letters + string.digits, k=16))
            }

            if DEBUG: print(f"  Creating account for {email}...")
            account_response = self.session.post(
                "https://api.mail.tm/accounts",
                json=account_data,
                timeout=10
            )

            if account_response.status_code == 201:
                account_info = account_response.json()
                self.account_id = account_info.get('id')
                self.email = email
                print(f"  ✓ Created temporary email: {email}")

                # Get token for accessing emails
                token_response = self.session.post(
                    "https://api.mail.tm/token",
                    json={"address": email, "password": account_data["password"]},
                    timeout=10
                )

                if token_response.status_code == 200:
                    token_data = token_response.json()
                    self.token = token_data.get('token')
                    self.session.headers.update({
                        "Authorization": f"Bearer {self.token}"
                    })
                    if DEBUG: print(f"  ✓ Got mail.tm token")

                return email
            else:
                if DEBUG: print(f"  Failed to create account: {account_response.status_code}")
                if DEBUG: print(f"  Response: {account_response.text[:200]}")
                return None

        except Exception as e:
            if DEBUG: print(f"  Error generating email: {str(e)[:100]}")
            return None

    def check_emails(self) -> List[Dict]:
        """Check for new emails"""
        if not self.email or not self.token:
            return []

        try:
            response = self.session.get(
                "https://api.mail.tm/messages",
                timeout=10
            )

            if response.status_code == 200:
                messages_data = response.json()
                messages = messages_data.get('hydra:member', [])

                formatted_messages = []
                for msg in messages:
                    formatted_messages.append({
                        'id': msg.get('id'),
                        'subject': msg.get('subject', ''),
                        'from': msg.get('from', {}).get('address', ''),
                        'intro': msg.get('intro', ''),
                        'text': msg.get('text', '')
                    })

                return formatted_messages
            else:
                if DEBUG: print(f"  Mail check failed: {response.status_code}")
            return []

        except Exception as e:
            if DEBUG: print(f"  Error checking emails: {str(e)[:100]}")
            return []

    def get_verification_code(self, timeout=180) -> Optional[str]:
        """Wait for verification code email and extract the code"""
        if not self.email:
            return None

        print(f"\n  📧 Waiting for verification code to {self.email}")
        print(f"  ⏳ Checking every 10 seconds (timeout: {timeout}s)")

        start_time = time.time()
        check_interval = 10
        last_check_time = 0
        email_found = False

        while time.time() - start_time < timeout:
            current_time = time.time()

            # Only check at intervals
            if current_time - last_check_time >= check_interval:
                last_check_time = current_time

                try:
                    messages = self.check_emails()

                    for msg in messages:
                        subject = msg.get('subject', '')
                        intro = msg.get('intro', '')
                        text = msg.get('text', '')
                        sender = msg.get('from', '')

                        # Check if it's from TV.Team or contains verification
                        if 'tv.team' in sender.lower() or 'verification' in subject.lower():
                            email_found = True
                            if DEBUG: print(f"\n  📨 Found email from: {sender}")
                            if DEBUG: print(f"     Subject: {subject[:50]}...")
                            if DEBUG: print(f"     Intro: {intro[:100]}...")
                            if DEBUG: print(f"     Text preview: {text[:200]}...")

                            # Combine all text fields for searching
                            search_text = f"{subject} {intro} {text}"

                            # Search for 6-digit code
                            code_patterns = [
                                r'\b\d{6}\b',
                                r'code[:\s]+(\d{6})',
                                r'verification[:\s]+(\d{6})',
                                r'is[:\s]+(\d{6})',
                                r'Your code: (\d{6})',
                                r'код: (\d{6})',
                                r'code is: (\d{6})',
                                r'code: (\d{6})',
                            ]

                            for pattern in code_patterns:
                                match = re.search(pattern, search_text, re.IGNORECASE)
                                if match:
                                    code = match.group(1) if match.groups() else match.group(0)
                                    if code.isdigit() and len(code) == 6:
                                        print(f"  ✅ Found verification code: {code}")
                                        return code

                except Exception as e:
                    if DEBUG: print(f"  ⚠️ Error checking emails: {str(e)[:100]}")

            # Show progress
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed

            if remaining > 0 and DEBUG:
                status = "Found email, scanning..." if email_found else "Still waiting for email..."
                print(f"\r  ⏱️ Elapsed: {elapsed}s | Remaining: {remaining}s | {status}", end="", flush=True)

            time.sleep(1)

        print(f"\n  ❌ Timeout waiting for verification code")

        # Fallback to manual input
        print("\n  ⚠️ Could not find verification code automatically.")
        print(f"  Please check your email at: https://mail.tm (login with token)")
        manual_code = input("  Enter the 6-digit verification code (or press Enter to skip): ").strip()

        if manual_code and len(manual_code) == 6 and manual_code.isdigit():
            return manual_code

        return None


class SessionManager:
    """Manages session rotation and fingerprint changes"""

    @staticmethod
    def generate_fingerprint() -> Dict[str, str]:
        """Generate new device fingerprint"""
        fingerprint_id = hashlib.sha256(
            f"{uuid.uuid4()}{time.time()}{random.random()}".encode()
        ).hexdigest()

        # Generate screen resolution
        resolutions = [
            "1920x1080", "1366x768", "1536x864",
            "1440x900", "1280x720", "1600x900"
        ]

        # Generate timezone
        timezones = ["Europe/Moscow", "Europe/Kiev", "Europe/Minsk", "Asia/Yerevan"]

        # Generate language
        languages = ["en-US", "ru-RU", "uk-UA", "en-GB"]

        # Generate user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        ]

        return {
            "fingerprint": fingerprint_id,
            "user_agent": random.choice(user_agents),
            "resolution": random.choice(resolutions),
            "timezone": random.choice(timezones),
            "language": random.choice(languages),
            "created_at": int(time.time() * 1000)
        }

    @staticmethod
    def generate_session_id() -> str:
        """Generate session ID"""
        return base64.b64encode(
            f"{int(time.time())}{random.randint(1000, 9999)}".encode()
        ).decode()[:32]


class TVTeamAccount:
    """Complete TV.Team account management with trial activation"""

    def __init__(self, proxy: Optional[str] = None,
                 enable_erotica: bool = True,
                 playlist_app_id: int = 41):
        self.base_url = "https://new.tv.team"
        self.session = requests.Session()
        self.enable_erotica = enable_erotica  # Boolean to control erotica toggle
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

        # Services
        self.temp_mail = TempMailService()
        self.account_created = False
        self.csrf_token = None
        self.is_authenticated = False

        if DEBUG:
            print(f"  🆕 New session created")
            print(f"  Fingerprint: {self.fingerprint_data['fingerprint'][:20]}...")
            print(f"  User Agent: {self.fingerprint_data['user_agent'][:50]}...")

    def setup_headers(self):
        """Setup headers with fingerprint"""
        headers = {
            "User-Agent": self.fingerprint_data["user_agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": f"{self.fingerprint_data['language']};q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Device-Fingerprint": self.fingerprint_data["fingerprint"],
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
                # Add delay before request
                if attempt > 0:
                    wait_time = 2 ** attempt
                    if DEBUG: print(f"  ⏳ Retry {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    self.human_delay(1, 3)

                # Update referer if not specified
                if "referer" not in kwargs:
                    if "login" in url:
                        self.session.headers["Referer"] = f"{self.base_url}/login"
                    elif "packages" in url:
                        self.session.headers["Referer"] = f"{self.base_url}/packages"
                    else:
                        self.session.headers["Referer"] = self.base_url

                if debug and DEBUG:
                    print(f"  🔍 Request: {method} {url}")
                    if "headers" in kwargs:
                        print(f"  Headers: {kwargs['headers']}")
                    if "data" in kwargs:
                        d = kwargs['data']
                        print(f"  Data: {d[:200] if isinstance(d, List) else d}...")

                # Make request
                resp = self.session.request(method, url, timeout=30, **kwargs)

                if debug and DEBUG:
                    print(f"  Response Status: {resp.status_code}")
                    print(f"  Response Headers: {dict(resp.headers)}")
                    print(f"  Response Preview: {resp.text[:500]}...")

                # Handle rate limits
                if resp.status_code == 429:
                    if DEBUG: print(f"  ⚠️ Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                    continue

                # Handle server errors
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
        """Calculate the slider offset for the puzzle captcha"""
        try:
            # Get challenge parameters
            slot_x = challenge_data.get("slotX", 110)
            knob_size = challenge_data.get("knob", 44)
            img_width = challenge_data.get("width", 384)

            if DEBUG:
                print(f"  - Target slot X: {slot_x}")
                print(f"  - Knob size: {knob_size}")

            # Add human-like variation (±3 pixels)
            variation = random.randint(-3, 3)
            offset = slot_x + variation

            # Ensure offset is within bounds
            offset = max(0, min(offset, img_width - knob_size))

            if DEBUG:
                print(f"  - Calculated offset: {offset} (with variation: {variation})")
            return offset

        except Exception as e:
            if DEBUG: print(f"  ⚠️ Error calculating offset: {str(e)[:100]}")
            return challenge_data.get("slotX", 110)

    def solve_captcha(self, captcha_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Solve captcha and get proof token"""
        captcha_id = captcha_data.get("captchaId")
        challenge = captcha_data.get("challenge", {})

        if not captcha_id:
            if DEBUG: print("  ❌ No captcha ID provided")
            return None, None

        if DEBUG:
            print(f"  Captcha ID: {captcha_id}")
            print(f"  Challenge data: {challenge}")

        # Calculate offset
        offset_x = self.calculate_slider_offset(challenge)

        if DEBUG: print(f"  🎯 Using offset: {offset_x}")

        # Verify captcha
        payload = {"captchaId": captcha_id, "offsetX": offset_x}
        if DEBUG: print(f"  Payload: {payload}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/captcha/verify",
            json=payload,
            headers={"Content-Type": "application/json"},
            debug=False
        )

        if not resp:
            if DEBUG: print(f"  ❌ Captcha verification failed - no response")
            return None, None

        if DEBUG: print(f"  Verification response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Captcha verification failed with status: {resp.status_code}")
            if DEBUG: print(f"  Response: {resp.text[:200]}")
            return None, None

        try:
            result = resp.json()

            if "data" in result and "proof" in result["data"]:
                proof_token = result["data"]["proof"]
                if DEBUG: print(f"  ✓ Got proof token: {proof_token[:30]}...")
                return captcha_id, proof_token
            else:
                if DEBUG: print(f"  ❌ No proof token in response")
                if DEBUG: print(f"  Response structure: {result}")
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing verification: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")

        return None, None

    def start_registration(self, username: str, password: str, email: str) -> bool:
        """Start the registration process"""
        print(f"  📝 Registering {username}...")

        # Get captcha
        captcha_data = self.get_captcha()
        if not captcha_data:
            if DEBUG: print("  ❌ Could not get captcha data")
            return False

        # Solve captcha
        captcha_id, proof_token = self.solve_captcha(captcha_data)
        if not captcha_id or not proof_token:
            if DEBUG: print("  ❌ Could not solve captcha")
            return False

        # Start registration
        form_data = f"login={quote(username)}&password={quote(password)}&email={quote(email)}&captchaId={quote(captcha_id)}&captchaSolution={quote(proof_token)}"

        if DEBUG: print(f"  Registration form data: {form_data[:200]}...")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/register/start",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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

            if "success" in result and result["success"]:
                if DEBUG: print(f"  ✓ Registration started successfully")
                return True
            else:
                if DEBUG: print(f"  ❌ Registration not successful according to response")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing registration response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def verify_email(self, username: str, email: str) -> bool:
        """Verify email with code"""
        # Get verification code
        code = self.temp_mail.get_verification_code(timeout=180)
        if not code:
            if DEBUG: print("  ❌ No verification code received")
            return False

        # Complete registration
        print(f"  ✅ Verifying with code {code}...")
        form_data = f"login={quote(username)}&email={quote(email)}&code={code}"

        if DEBUG: print(f"  Verification form data: {form_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/register/verify",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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

            if "success" in result and result["success"]:
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
        """Login to the account with correct parameter names"""
        print(f"  🔐 Logging in as {username}...")

        # First get captcha for login
        if DEBUG: print("  🔍 Getting captcha for login...")
        captcha_data = self.get_captcha()
        if not captcha_data:
            if DEBUG: print("  ❌ Could not get captcha for login")
            return False

        # Solve captcha
        captcha_id, proof_token = self.solve_captcha(captcha_data)
        if not captcha_id or not proof_token:
            if DEBUG: print("  ❌ Could not solve captcha for login")
            return False

        # Prepare login data with CORRECT parameter names
        form_data = (
            f"userLogin={quote(username)}&"
            f"userPasswd={quote(password)}&"
            f"rememberMe=1&"
            f"captchaId={quote(captcha_id)}&"
            f"captchaSolution={quote(proof_token)}"
        )

        if DEBUG: print(f"  Login form data prepared...")

        login_resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/login",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            debug=False
        )

        if not login_resp:
            if DEBUG: print(f"  ❌ Login failed: No response")
            return False

        if DEBUG: print(f"  Login response status: {login_resp.status_code}")

        if login_resp.status_code != 200:
            if DEBUG: print(f"  ❌ Login failed with status: {login_resp.status_code}")
            if DEBUG: print(f"  Response: {login_resp.text[:200]}")
            return False

        try:
            login_result = login_resp.json()
            if DEBUG: print(f"  Login result: {login_result}")

            # Check for success in different possible formats
            if (login_result.get("success") or
                    login_result.get("authorized") == 1 or
                    login_result.get("data", {}).get("authorized") == 1):
                print(f"  ✅ Login successful!")
                self.is_authenticated = True
                return True
            else:
                error_msg = login_result.get("message") or login_result.get("data", {}).get("message", "Unknown error")
                if DEBUG: print(f"  ❌ Login failed: {error_msg}")

                # Check if it's a captcha issue
                if "captcha" in str(error_msg).lower():
                    if DEBUG: print("  ⚠️ Captcha validation failed, retrying with new captcha...")
                    # Retry once with fresh captcha
                    return self._retry_login_with_fresh_captcha(username, password)

                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing login response: {e}")
            if DEBUG: print(f"  Raw response: {login_resp.text[:200]}")
            return False

    def _retry_login_with_fresh_captcha(self, username: str, password: str) -> bool:
        """Retry login with fresh captcha"""
        if DEBUG: print("  🔄 Retrying login with fresh captcha...")

        # Get fresh captcha
        captcha_data = self.get_captcha()
        if not captcha_data:
            return False

        # Solve fresh captcha
        captcha_id, proof_token = self.solve_captcha(captcha_data)
        if not captcha_id or not proof_token:
            return False

        # Prepare login data
        form_data = (
            f"userLogin={quote(username)}&"
            f"userPasswd={quote(password)}&"
            f"rememberMe=1&"
            f"captchaId={quote(captcha_id)}&"
            f"captchaSolution={quote(proof_token)}"
        )

        login_resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/login",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            debug=False
        )

        if not login_resp or login_resp.status_code != 200:
            return False

        try:
            login_result = login_resp.json()
            if (login_result.get("success") or
                    login_result.get("authorized") == 1 or
                    login_result.get("data", {}).get("authorized") == 1):
                if DEBUG: print(f"  ✅ Login successful on retry!")
                self.is_authenticated = True
                return True
        except:
            pass

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

        # Update referer for packages page
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

        # Get CSRF token first
        if not self.get_csrf_token():
            if DEBUG: print("  ❌ Failed to get CSRF token for trial activation")
            return False

        # Activate trial
        trial_data = {
            "fingerprint": self.fingerprint_data["fingerprint"],
            "userAgent": self.fingerprint_data["user_agent"]
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

        # Get CSRF token
        if not self.get_csrf_token():
            if DEBUG: print("  ❌ Failed to get CSRF token")
            return False

        # Toggle erotica
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

    def complete_account_creation(self) -> Optional[Dict]:
        """Complete account creation flow including trial activation and erotica toggle"""
        print(f"\n{'=' * 60}")
        print(f"🚀 Creating New Account with Trial Activation")
        print(f"{'=' * 60}")

        # Generate credentials
        username = f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}"
        password = f"Pass{random.randint(1000, 9999)}!{''.join(random.choices(string.ascii_letters, k=8))}"

        print(f"  👤 Username: {username}")
        print(f"  🔐 Password: {password}")

        # Get email
        print(f"\n  📧 Getting temporary email...")
        email = self.temp_mail.generate_email()
        if not email:
            print("  ❌ Cannot proceed without email - stopping")
            return None

        print(f"  📨 Email: {email}")

        # Register account
        print(f"\n  🔄 Step 1/5: Starting registration...")
        if not self.start_registration(username, password, email):
            print("  ❌ Registration failed")
            return None

        # Verify email
        print(f"\n  🔄 Step 2/5: Verifying email...")
        if not self.verify_email(username, email):
            print("  ❌ Email verification failed")
            return None

        # Login to account
        print(f"\n  🔄 Step 3/5: Logging in...")
        if not self.login(username, password):
            print("  ❌ Login failed after registration")
            return None

        # Get account info
        print(f"\n  🔄 Step 4/5: Getting account info...")
        account_info = self.get_account_info()
        if not account_info:
            if DEBUG: print("  ⚠️ Could not get account info, but continuing...")

        # Check trial status
        print(f"\n  🔄 Step 5/6: Checking trial status...")
        trial_status = self.check_trial_status()

        # Activate trial if eligible
        trial_activated = False
        if trial_status and trial_status.get("eligible"):
            print(f"\n  🔄 Step 6/7: Activating trial...")
            trial_activated = self.activate_trial()
        else:
            if DEBUG: print("  ⚠️ Skipping trial activation - account not eligible")

        # Toggle erotica based on user setting
        erotica_set = False
        if self.enable_erotica:
            print(f"\n  🔄 Step 7/7: Setting erotica preference...")
            erotica_set = self.toggle_erotica(enable=True)
        else:
            if DEBUG: print("  ⚠️ Skipping erotica toggle - disabled by user setting")

        # Get playlist URL
        print(f"\n  🔄 Getting playlist URL...")
        playlist_url = self.generate_playlist_url(use_https=False)

        # Prepare account data
        account_data = {
            "username": username,
            "password": password,
            "email": email,
            "fingerprint": self.fingerprint_data["fingerprint"],
            "user_agent": self.fingerprint_data["user_agent"],
            "account_id": account_info.get("id") if account_info else "N/A",
            "trial_status": trial_status,
            "trial_eligible": trial_status.get("eligible", False) if trial_status else False,
            "trial_activated": trial_activated,
            "erotica_enabled": self.enable_erotica,
            "erotica_set": erotica_set,
            "playlist_url": playlist_url,
            "playlist_app_id": self.playlist_app_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return account_data

    def check_saved_account_trial(self) -> Tuple[bool, Optional[Dict]]:
        """Check if saved account has active trial by logging in and checking"""
        # Load saved account
        saved_account = AccountManager.load_account()

        if not saved_account:
            if DEBUG: print("  📭 No saved account found")
            return False, None

        print(f"\n  🔍 Checking trial status for saved account: {saved_account['username']}")

        # Try to login
        print(f"  🔐 Attempting to login...")
        if not self.login(saved_account['username'], saved_account['password']):
            print(f"  ❌ Failed to login with saved credentials")
            if DEBUG: print(f"  🗑️ Removing invalid saved account...")
            try:
                os.remove(AccountManager.SAVE_FILE)
            except:
                pass
            return False, None

        # Check trial status via website
        print(f"  📊 Checking trial status via website...")
        trial_status = self.check_trial_status()

        if not trial_status:
            if DEBUG: print(f"  ❌ Failed to check trial status")
            return False, saved_account

        # Check if trial is still active
        has_active_trial = trial_status.get('hasActiveTrial', False)

        if has_active_trial:
            print(f"  ✅ Trial is ACTIVE on website")
            return True, saved_account
        else:
            if DEBUG: print(f"  ❌ Trial NOT ACTIVE or eligible")
            return False, saved_account

    def create_and_save_account(self) -> Optional[Dict]:
        """Create new account and save credentials if trial activated"""
        # Create account using existing method
        account = self.complete_account_creation()

        if account and account.get("trial_activated"):
            # Save ONLY username/password/email
            AccountManager.save_account(
                account['username'],
                account['password'],
                account['email']
            )

        return account

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

            # Check for uniqId in the response data
            uniq_id = data.get("uniqId")
            if uniq_id:
                if DEBUG: print(f"  ✅ Found uniqId: {uniq_id}")
                return uniq_id

            # Alternative: try to extract from items if available
            items = data.get("items", [])
            if items:
                # Check if any item has a link that contains the token
                for item in items:
                    link = item.get("link", "")
                    if "/pl/" in link:
                        # Extract token from link like http://tvtm.one/pl/41/ukq6cx5ef47m/playlist.m3u8
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

        proxies = []

        # Source 1: FreeProxyList
        try:
            resp = self.session.get("https://free-proxy-list.net/", timeout=10)
            if resp.status_code == 200:
                pattern = r'(\d+\.\d+\.\d+\.\d+):(\d+)'
                matches = re.findall(pattern, resp.text)
                for ip, port in matches[:50]:
                    proxies.append(f"http://{ip}:{port}")
                if DEBUG: print(f"✓ Got {len(matches)} proxies from FreeProxyList")
        except Exception as e:
            if DEBUG: print(f"✗ FreeProxyList failed: {e}")

        # Source 2: SSLProxies
        try:
            resp = self.session.get("https://www.sslproxies.org/", timeout=10)
            if resp.status_code == 200:
                pattern = r'(\d+\.\d+\.\d+\.\d+):(\d+)'
                matches = re.findall(pattern, resp.text)
                for ip, port in matches[:50]:
                    proxies.append(f"http://{ip}:{port}")
                if DEBUG: print(f"✓ Got {len(matches)} proxies from SSLProxies")
        except Exception as e:
            if DEBUG: print(f"✗ SSLProxies failed: {e}")

        # Source 3: ProxyScrape
        try:
            resp = self.session.get(
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
                timeout=10)
            if resp.status_code == 200:
                lines = resp.text.strip().split('\n')
                for line in lines[:100]:
                    if ':' in line:
                        proxies.append(f"http://{line.strip()}")
                if DEBUG: print(f"✓ Got {len(lines)} proxies from ProxyScrape")
        except Exception as e:
            if DEBUG: print(f"✗ ProxyScrape failed: {e}")

        # Source 4: Geonode
        try:
            resp = self.session.get(
                "https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc",
                timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for proxy in data.get('data', []):
                    ip = proxy.get('ip')
                    port = proxy.get('port')
                    if ip and port:
                        proxies.append(f"http://{ip}:{port}")
                if DEBUG: print(f"✓ Got {len(data.get('data', []))} proxies from Geonode")
        except Exception as e:
            if DEBUG: print(f"✗ Geonode failed: {e}")

        # Remove duplicates
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
    """Manages saved account information - only saves username/password/email"""

    SAVE_FILE = "tvteam_account.json"

    @staticmethod
    def save_account(username: str, password: str, email: str) -> None:
        """Save only username, password, email to file"""
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

            # Validate the data has required fields
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
        Format exactly as shown:
        #EXTM3U
        #EXTINF:0 tvg-id="ch2934" tvg-name="..." tvg-logo="..." timeshift="6", Channel Name
        #EXTGRP:28. Israel
        http://11.tvtm.one/ch2934/mono.m3u8?token=...
        """
        channels = OrderedDict()
        lines = content.strip().split('\n')

        i = 0
        channel_index = 0

        # Check for M3U header
        if lines and lines[0].startswith('#EXTM3U'):
            channels['header'] = lines[0]
            i = 1
        else:
            # No header, start from beginning
            channels['header'] = '#EXTM3U'

        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            # Check for channel entry
            if line.startswith('#EXTINF:'):
                # This is a channel block
                extinf_line = line

                # The next line should be #EXTGRP:
                group_line = ""
                if i + 1 < len(lines) and lines[i + 1].startswith('#EXTGRP:'):
                    group_line = lines[i + 1].strip()
                    i += 1

                # The next line should be the URL
                url_line = ""
                if i + 1 < len(lines) and lines[i + 1].startswith('http'):
                    url_line = lines[i + 1].strip()
                    i += 1

                # Parse EXTINF line
                # Format: #EXTINF:0 tvg-id="ch2934" tvg-name="IL: Aruch Sdarot Hahodiot" tvg-logo="http://..." timeshift="6", IL: Aruch Sdarot Hahodiot
                attrs = {}
                channel_name = ""

                # Extract duration (0)
                duration_match = re.search(r'#EXTINF:([\d.-]+)', extinf_line)
                duration = duration_match.group(1) if duration_match else "0"

                # Extract attributes using regex
                attr_pattern = r'(\S+)="([^"]*)"'
                attrs = dict(re.findall(attr_pattern, extinf_line))

                # Extract channel name (after comma)
                if ',' in extinf_line:
                    channel_name = extinf_line.split(',', 1)[1].strip()

                # Extract channel ID from tvg-id attribute or URL
                channel_id = attrs.get('tvg-id', '').replace('ch', '')
                if not channel_id and url_line:
                    # Fallback: extract from URL
                    channel_id = self.extract_channel_id_from_url(url_line)

                # Extract group from #EXTGRP line
                group = ""
                if group_line:
                    group = group_line.replace('#EXTGRP:', '').strip()

                # Create channel object
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

                # Use channel_id as key
                key = f"ch{channel_id}" if channel_id else f"channel_{channel_index}"
                channels[key] = channel_data

                channel_index += 1
                i += 1  # Move to next line

            else:
                # Store other lines as metadata
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

        # Try pattern /ch2934/
        match = re.search(r'/ch(\d+)/', url)
        if match:
            return match.group(1)

        # Try pattern ch2934 in query string
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
        Returns: (updated_gist_channels, change_count)
        """
        change_count = 0
        updated_channels = OrderedDict()

        # First, copy all metadata and structure
        for key, value in gist_channels.items():
            if key == 'header':
                updated_channels[key] = value
            elif isinstance(value, dict) and value.get('type') == 'metadata':
                updated_channels[key] = value
            elif isinstance(value, dict) and 'extinf' in value:
                # This is a channel
                channel_data = value.copy()
                channel_id = channel_data.get('channel_id')

                if channel_id and channel_id in reference_channels:
                    ref_channel = reference_channels[channel_id]
                    ref_token = self.extract_token_from_url(ref_channel.get('url', ''))
                    current_token = self.extract_token_from_url(channel_data.get('url', ''))

                    if ref_token and current_token != ref_token:
                        # Update the URL with new token
                        old_url = channel_data['url']
                        new_url = self.replace_token_in_url(old_url, ref_token)
                        channel_data['url'] = new_url

                        # Update the raw lines
                        for j, line in enumerate(channel_data['raw_lines']):
                            if line == old_url:
                                channel_data['raw_lines'][j] = new_url

                        change_count += 1

                updated_channels[key] = channel_data
            else:
                # Keep other elements as-is
                updated_channels[key] = value

        return updated_channels, change_count

    def reconstruct_m3u_from_channels(self, channels):
        """Reconstruct M3U playlist from channel data while preserving structure"""
        lines = []

        # Add header
        if 'header' in channels:
            lines.append(channels['header'])

        # Sort items to maintain original order
        items_to_sort = []
        for key, value in channels.items():
            if key == 'header':
                continue
            if isinstance(value, dict):
                if 'index' in value:
                    items_to_sort.append((value['index'], key, value))
                else:
                    items_to_sort.append((999999, key, value))

        # Sort by original index
        items_to_sort.sort(key=lambda x: x[0])

        for _, key, value in items_to_sort:
            if isinstance(value, dict) and value.get('type') == 'metadata':
                lines.append(value['line'])
            elif isinstance(value, dict) and 'extinf' in value:
                # Add channel with all its original lines
                lines.extend(value['raw_lines'])

        return '\n'.join(lines)

    def update_gist_with_playlist(self, gist_filename, playlist_url):
        """Update a specific gist file with tokens from playlist URL"""
        print(f"\n{'=' * 80}")
        print("🎬 M3U Playlist Token Updater")
        print(f"📁 Gist file: '{gist_filename}'")
        print(f"🔗 Reference: {playlist_url}")
        print("=" * 80)

        # Step 1: Find and parse gist playlist
        print(f"\n🔍 Searching for gist '{gist_filename}'...")
        gist_id, gist_content = self.find_gist_file(gist_filename)

        if not gist_id:
            print(f"❌ No gist found containing '{gist_filename}'")
            return False

        print(f"✓ Found gist: {gist_id}")

        # Parse gist content
        if DEBUG: print("📝 Parsing gist M3U playlist...")
        gist_channels = self.parse_m3u_playlist(gist_content)

        gist_channel_count = len([v for v in gist_channels.values()
                                  if isinstance(v, dict) and 'extinf' in v])
        if DEBUG: print(f"📊 Gist contains {gist_channel_count} channels")

        # Step 2: Download and parse reference playlist
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

        # Create lookup dict for reference channels
        ref_lookup = {}
        for key, value in reference_channels.items():
            if isinstance(value, dict) and 'extinf' in value:
                channel_id = value.get('channel_id')
                if channel_id:
                    ref_lookup[channel_id] = value

        if DEBUG: print(f"📋 Reference has {len(ref_lookup)} unique channel IDs")

        # Show sample of reference channels
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

        # Step 3: Update channels
        if DEBUG: print(f"\n🔄 Comparing and updating channels...")
        updated_channels, change_count = self.update_channels_from_reference(
            gist_channels, ref_lookup
        )

        # Step 4: Check if changes were made
        if change_count == 0:
            print("\n✅ No updates needed - all tokens are current")
            return True

        print(f"\n📈 Updated {change_count} channel(s)")

        # Show detailed changes
        if DEBUG:
            print("\n📝 Detailed changes:")
            changes_shown = 0
            for key, channel in updated_channels.items():
                if isinstance(channel, dict) and 'extinf' in channel:
                    channel_id = channel.get('channel_id')
                    if channel_id in ref_lookup:
                        # Check if URL changed
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

                                if changes_shown >= 5:  # Limit output
                                    print(f"\n    ... and {change_count - changes_shown} more changes")
                                    break

        # Step 5: Reconstruct M3U
        if DEBUG: print(f"\n🔧 Reconstructing M3U playlist...")
        new_m3u_content = self.reconstruct_m3u_from_channels(updated_channels)

        # Verify reconstruction - count lines
        old_lines = [l for l in gist_content.strip().split('\n') if l.strip()]
        new_lines = [l for l in new_m3u_content.strip().split('\n') if l.strip()]

        if DEBUG:
            print(f"✅ Reconstruction successful")
            print(f"   Original non-empty lines: {len(old_lines)}")
            print(f"   New non-empty lines: {len(new_lines)}")

        # Step 6: Update gist
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
    DEBUG = False  # Default debug mode off

    # Check for debug flag
    if '--debug' in sys.argv:
        DEBUG = True
        print("🔧 Debug mode enabled")

    print(f"\n🎯 TV.Team Account Manager & Gist Updater")
    print(f"⚙️ Configuration: Erotica enabled by default")
    print(f"{'=' * 60}")

    # Configuration
    ENABLE_EROTICA = True
    TIVIMATE_ID = 41
    GITHUB_TOKEN = "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"  # Your GitHub token
    GIST_FILES = ["file4", "file5"]  # Gist files to update

    playlist_url = None

    # ============================================
    # FIRST: Check saved account WITHOUT proxy
    # ============================================
    print(f"\n📋 Checking saved account (no proxy)...")

    # Create account manager WITHOUT proxy
    check_manager = TVTeamAccount(proxy=None, enable_erotica=ENABLE_EROTICA, playlist_app_id=TIVIMATE_ID)

    # Check if saved account exists and has active trial
    has_active_trial, saved_account = check_manager.check_saved_account_trial()

    if has_active_trial:
        print(f"\n{'=' * 60}")
        print(f"✅ USING EXISTING ACCOUNT WITH ACTIVE TRIAL")
        print(f"{'=' * 60}")
        print(f"  👤 Username: {saved_account['username']}")
        print(f"  📧 Email: {saved_account['email']}")
        print(f"  🎯 Trial: ACTIVE")
        print(f"  💾 Loaded from: {AccountManager.SAVE_FILE}")
        return
    else:
        # ============================================
        # SECOND: Create new account with proxies
        # ============================================
        print(f"\n🔄 Creating new account with proxies...")

        # Load proxies
        fetcher = ProxyFetcher()
        proxies = fetcher.fetch_proxy_list()

        if not proxies:
            proxies = [None]
            print("⚠️ No proxies found, using direct connection")

        print(f"\n📋 Loaded {len(proxies)} proxies")

        account = None

        for current_proxy in proxies:
            try:
                print(f"\n{'=' * 50}")
                print(f"🔄 Attempting account creation with proxy: {current_proxy if current_proxy else 'Direct'}")
                print(f"{'=' * 50}")

                if current_proxy:
                    if not fetcher.test_proxy_simple(current_proxy):
                        if DEBUG: print("❌ Proxy not working, skipping...")
                        continue

                # Create account manager WITH proxy
                account_manager = TVTeamAccount(proxy=current_proxy, enable_erotica=ENABLE_EROTICA,
                                                playlist_app_id=TIVIMATE_ID)

                # Create new account
                account = account_manager.create_and_save_account()

                if account and account.get("trial_activated"):
                    print(f"\n🎉🎉🎉 SUCCESS: New account created WITH TRIAL ACTIVATED! 🎉🎉🎉")
                    playlist_url = account.get("playlist_url")
                    break
                elif account:
                    if DEBUG: print(f"\n⚠️ Account created but trial NOT activated")
                    # Continue to next proxy
                else:
                    if DEBUG: print(f"\n❌ Account creation failed")
                    # Continue to next proxy

            except Exception as e:
                if DEBUG:
                    print(f"\n💥 Unexpected error: {e}")
                    import traceback
                    traceback.print_exc()
                continue

        # Final summary
        print(f"\n\n{'=' * 60}")
        print(f"📈 FINAL RESULTS")
        print(f"{'=' * 60}")

        if account:
            print(f"\n✅ ACCOUNT STATUS:")
            print(f"   Username: {account.get('username')}")
            print(f"   Email: {account.get('email')}")
            print(f"   Trial: {'✅ ACTIVE' if account.get('trial_activated', False) else '❌ Not active'}")
            if playlist_url:
                print(f"   Playlist URL: {playlist_url}")
        else:
            print(f"\n❌ No valid account available")
            return

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
        print(f"✅ ALL OPERATIONS COMPLETED")
        print(f"{'=' * 60}")
    else:
        print(f"\n❌ No playlist URL available to update gists")


if __name__ == "__main__":
    # Check for required packages
    try:
        import requests

        print("✅ All required packages are installed")
    except ImportError:
        print("❌ Please install required packages:")
        print("pip install requests")
        exit(1)

    # Disable SSL warnings
    from urllib3.exceptions import InsecureRequestWarning

    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    # Run main
    main()