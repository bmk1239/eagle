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
from datetime import datetime, date

warnings.filterwarnings('ignore')


class TempMailService:
    """Service to get temporary emails using freecustom.email"""

    def __init__(self):
        self.email = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        self.session.verify = False

    def generate_email(self) -> Optional[str]:
        """Generate a random temporary email using freecustom.email"""
        try:
            # Generate random email
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            domain = "freecustom.email"
            email = f"{username}@{domain}"
            self.email = email
            print(f"  ✓ Created temporary email: {email}")
            return email

        except Exception as e:
            if DEBUG: print(f"  Error generating email: {str(e)[:100]}")
            return None

    def check_emails(self) -> List[Dict]:
        """Check for new emails using freecustom.email"""
        if not self.email:
            return []

        try:
            # Extract username from email
            username = self.email.split('@')[0]
            
            response = self.session.get(
                f"https://www.freecustom.email/{username}",
                timeout=10
            )

            if response.status_code == 200:
                messages = []
                # Parse the HTML response to find emails
                html = response.text
                
                # Look for email entries
                email_pattern = r'<div class="email-item[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<p[^>]*>(.*?)</p>'
                matches = re.findall(email_pattern, html, re.DOTALL)
                
                for match in matches:
                    messages.append({
                        'id': str(len(messages)),
                        'subject': match[0] if match else '',
                        'from': 'support@tv.team',
                        'intro': match[1] if len(match) > 1 else '',
                        'text': match[1] if len(match) > 1 else ''
                    })
                
                return messages
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

                        # Check if it's from TV.Team or contains verification
                        if 'verification' in subject.lower() or 'code' in subject.lower():
                            email_found = True
                            if DEBUG: print(f"\n  📨 Found email with subject: {subject[:50]}...")

                            # Combine all text fields for searching
                            search_text = f"{subject} {intro} {text}"

                            # Search for 6-digit code
                            code_patterns = [
                                r'<strong[^>]*>(\d{6})</strong>',
                                r'<div[^>]*class="code-box"[^>]*>.*?(\d{6})',
                                r'is:?\s*(\d{6})',
                                r'code:?\s*(\d{6})',
                                r'(\d{6})\s*will expire',
                                r'Your verification code is:\s*(\d{6})',
                                r'\b\d{6}\b',
                            ]

                            for pattern in code_patterns:
                                match = re.search(pattern, search_text, re.IGNORECASE | re.DOTALL)
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

            if remaining > 0 and not DEBUG:
                status = "Found email, scanning..." if email_found else "Still waiting for email..."
                print(f"\r  ⏱️ Elapsed: {elapsed}s | Remaining: {remaining}s | {status}", end="", flush=True)

            time.sleep(1)

        print(f"\n  ❌ Timeout waiting for verification code")
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

        # Generate timezone - updated to match fetch request
        timezones = ["Asia/Jerusalem", "Europe/Moscow", "Europe/Kiev", "Europe/Minsk"]

        # Generate language - updated to match fetch request
        languages = ["he-IL", "en-US", "ru-RU", "uk-UA"]

        # Generate user agent - updated to match fetch request
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
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
        """Setup headers with fingerprint - updated to match fetch request"""
        headers = {
            "User-Agent": self.fingerprint_data["user_agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": f"{self.fingerprint_data['language']},en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Device-Fingerprint": json.dumps(self.fingerprint_data),
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/register",
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

                # Make request with longer timeout
                resp = self.session.request(method, url, timeout=45, **kwargs)

                if debug and DEBUG:
                    print(f"  🔍 Request: {method} {url}")
                    print(f"  Response Status: {resp.status_code}")

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

            except requests.exceptions.ConnectTimeout:
                if DEBUG: print(f"  ⚠️ Connection timeout, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(5)
                continue
            except requests.exceptions.ReadTimeout:
                if DEBUG: print(f"  ⚠️ Read timeout, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(5)
                continue
            except requests.exceptions.SSLError:
                if DEBUG: print(f"  ⚠️ SSL Error, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(5)
                continue
            except Exception as e:
                if DEBUG: print(f"  ⚠️ Request error: {str(e)[:100]}, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(5)
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

    def generate_mouse_trail(self, target_x: int) -> List[Dict[str, int]]:
        """Generate realistic mouse trail for captcha - based on fetch request"""
        trail = []
        
        # Starting point
        current_x = 0
        current_time = 0
        
        # Generate movement steps - exactly like in the fetch request
        movements = [
            (5, 98),    # x=5, t=98
            (53, 134),  # x=53, t=134
            (94, 170),  # x=94, t=170
            (105, 204), # x=105, t=204
            (147, 240), # x=147, t=240
            (161, 278), # x=161, t=278
            (167, 321), # x=167, t=321
            (168, 364), # x=168, t=364
            (173, 406), # x=173, t=406
            (180, 441), # x=180, t=441
            (184, 490), # x=184, t=490
            (185, 612), # x=185, t=612
            (185, 1338) # x=185, t=1338
        ]
        
        # Scale movements to match target_x
        scale_factor = target_x / 185 if target_x != 185 else 1
        
        for x, t in movements:
            scaled_x = min(int(x * scale_factor), target_x)
            scaled_t = int(t * (target_x / 185) * random.uniform(0.9, 1.1))
            trail.append({"x": scaled_x, "t": scaled_t})
        
        return trail

    def solve_captcha(self, captcha_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Solve captcha and get proof token - WITH TRAIL from fetch request"""
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

        # Generate mouse trail - FIX FOR FIRST ERROR
        trail = self.generate_mouse_trail(offset_x)

        # Verify captcha with trail
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
            headers={"Content-Type": "application/json; charset=UTF-8"},
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

            # Check response structure - from fetch request it returns data.proof
            if "data" in result:
                if "proof" in result["data"]:
                    proof_token = result["data"]["proof"]
                    if DEBUG: print(f"  ✓ Got proof token: {proof_token[:30]}...")
                    return captcha_id, proof_token
                else:
                    if DEBUG: print(f"  ❌ No proof token in response data")
                    if DEBUG: print(f"  Response data: {result['data']}")
            else:
                if DEBUG: print(f"  ❌ No 'data' field in response")
                if DEBUG: print(f"  Response: {result}")
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing verification: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")

        return None, None

    def quick_register_start(self, email: str) -> bool:
        """Start quick registration with email"""
        print(f"  📝 Registering {email}...")

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

        # Start quick registration - matching fetch request exactly
        form_data = f"email={quote(email)}&captchaId={quote(captcha_id)}&captchaSolution={quote(proof_token)}&lang=US"

        if DEBUG: print(f"  Registration form data: {form_data[:200]}...")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/quick-register/start",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            },
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
            result = resp.json()
            if DEBUG: print(f"  Registration response: {result}")
            
            # Check for success in response
            if result.get("data", {}).get("ok") or result.get("success"):
                if DEBUG: print(f"  ✓ Registration started successfully")
                return True
            else:
                if DEBUG: print(f"  ❌ Registration not successful")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing registration response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def quick_register_verify(self, email: str) -> bool:
        """Verify email with code"""
        # Get verification code
        code = self.temp_mail.get_verification_code(timeout=180)
        if not code:
            if DEBUG: print("  ❌ No verification code received")
            return False

        # Complete registration
        print(f"  ✅ Verifying with code {code}...")
        form_data = f"email={quote(email)}&code={code}&lang=US"

        if DEBUG: print(f"  Verification form data: {form_data}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/quick-register/verify",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            },
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
            result = resp.json()
            if DEBUG: print(f"  Verification response: {result}")
            
            if result.get("data", {}).get("ok") or result.get("success"):
                print(f"  🎉 Account verified successfully!")
                self.account_created = True
                return True
            else:
                if DEBUG: print(f"  ❌ Verification not successful")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing verification response: {str(e)[:100]}")
            if DEBUG: print(f"  Raw response: {resp.text[:200]}...")
            return False

    def login(self, username: str, password: str) -> bool:
        """Login to the account"""
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

        # Prepare login data - matching fetch request
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

            # Check for success
            if (login_result.get("success") or
                    login_result.get("authorized") == 1 or
                    login_result.get("data", {}).get("authorized") == 1):
                print(f"  ✅ Login successful!")
                self.is_authenticated = True
                return True
            else:
                error_msg = login_result.get("message") or login_result.get("data", {}).get("message", "Unknown error")
                if DEBUG: print(f"  ❌ Login failed: {error_msg}")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing login response: {e}")
            if DEBUG: print(f"  Raw response: {login_resp.text[:200]}")
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
            "fingerprint": json.dumps(self.fingerprint_data),
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
        """Complete account creation flow using quick register"""
        print(f"\n{'=' * 60}")
        print(f"🚀 Creating New Account with Trial Activation")
        print(f"{'=' * 60}")

        # Get email
        print(f"\n  📧 Getting temporary email...")
        email = self.temp_mail.generate_email()
        if not email:
            print("  ❌ Cannot proceed without email - stopping")
            return None

        print(f"  📨 Email: {email}")

        # Start quick registration
        print(f"\n  🔄 Step 1/5: Starting registration...")
        if not self.quick_register_start(email):
            print("  ❌ Registration failed")
            return None

        # Verify email
        print(f"\n  🔄 Step 2/5: Verifying email...")
        if not self.quick_register_verify(email):
            print("  ❌ Email verification failed")
            return None

        # Login to account
        print(f"\n  🔄 Step 3/5: Logging in...")
        if not self.login(email, "QuickRegisterPassword"):
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
            "username": email.split('@')[0],
            "password": "QuickRegisterPassword",
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
            date_str = trial_status.get('activeTrialExpires', 'N/A')
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                today = date.today()
                if target_date > today:
                    print(f"  ✅ Trial is ACTIVE on website till {trial_status.get('activeTrialExpires', 'NA')}")
                    return True, saved_account
            except:
                pass
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
        """Get playlist session ID"""
        if not self.is_authenticated:
            return None

        if DEBUG: print("  🔍 Getting playlist session ID...")

        resp = self.safe_request("GET", f"{self.base_url}/v3/playlists?slot=0", debug=False)

        if not resp or resp.status_code != 200:
            return None

        try:
            data = resp.json().get("data", {})

            # Check for uniqId
            uniq_id = data.get("uniqId")
            if uniq_id:
                if DEBUG: print(f"  ✅ Found uniqId: {uniq_id}")
                return uniq_id

            # Alternative: try to extract from items
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
                print(f"  ❌ Could not find playlist session ID")
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
                    data = response.json()
                    origin = data.get('origin', '')
                except:
                    origin = "unknown"
                return True, speed, origin

        except:
            pass

        return False, 0, ""

    def test_proxy_simple(self, proxy: str) -> bool:
        working, speed, origin = self.test_proxy(proxy, timeout=8)
        return working


class AccountManager:
    """Manages saved account information"""

    SAVE_FILE = "/home/bmk1239/tvteam_account.json"

    @staticmethod
    def save_account(username: str, password: str, email: str) -> None:
        """Save account info to file"""
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
        """Find a gist containing the specific filename"""
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
        """Get file content"""
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
                return True, f"https://gist.githubusercontent.com/anon/{gist_id}/raw/{filename}"
            else:
                if DEBUG: print(f"Error updating gist: {response.status_code}")
                return False, None
        except Exception as e:
            if DEBUG: print(f"Error: {e}")
            return False, None

    def parse_m3u_playlist(self, content):
        """Parse M3U playlist into structured data"""
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

                channel_data = {
                    'index': channel_index,
                    'extinf': extinf_line,
                    'group': group_line,
                    'url': url_line,
                    'raw_lines': [extinf_line, group_line, url_line] if group_line else [extinf_line, url_line]
                }

                # Extract channel ID from URL
                channel_id = None
                if url_line:
                    match = re.search(r'/ch(\d+)/', url_line)
                    if match:
                        channel_id = match.group(1)

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

    def extract_token_from_url(self, url):
        """Extract token from URL"""
        if not url:
            return None

        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'token' in query_params:
            return query_params['token'][0]
        return None

    def download_playlist(self, playlist_url):
        """Download playlist from URL"""
        try:
            response = requests.get(playlist_url, timeout=10)
            if response.status_code == 200:
                return response.text
        except:
            pass
        return None

    def update_channels_from_reference(self, gist_channels, reference_channels):
        """Update gist channels with tokens from reference channels"""
        change_count = 0
        updated_channels = OrderedDict()

        for key, value in gist_channels.items():
            if key == 'header' or (isinstance(value, dict) and value.get('type') == 'metadata'):
                updated_channels[key] = value
            elif isinstance(value, dict) and 'extinf' in value:
                channel_data = value.copy()
                channel_id = None
                if key.startswith('ch'):
                    channel_id = key[2:]

                if channel_id and channel_id in reference_channels:
                    ref_channel = reference_channels[channel_id]
                    if channel_data.get('url') != ref_channel.get('url'):
                        channel_data['url'] = ref_channel.get('url', '')
                        # Update raw_lines
                        for j, line in enumerate(channel_data['raw_lines']):
                            if line.startswith('http'):
                                channel_data['raw_lines'][j] = ref_channel.get('url', '')
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

        gist_channels = self.parse_m3u_playlist(gist_content)

        print(f"\n🌐 Downloading reference playlist...")
        playlist_content = self.download_playlist(playlist_url)

        if not playlist_content:
            print("❌ Failed to download reference playlist")
            return False

        reference_channels = self.parse_m3u_playlist(playlist_content)

        # Create lookup dict
        ref_lookup = {}
        for key, value in reference_channels.items():
            if isinstance(value, dict) and 'extinf' in value:
                if key.startswith('ch'):
                    channel_id = key[2:]
                    ref_lookup[channel_id] = value

        updated_channels, change_count = self.update_channels_from_reference(
            gist_channels, ref_lookup
        )

        if change_count == 0:
            print("\n✅ No updates needed - all tokens are current")
            return True

        print(f"\n📈 Updated {change_count} channel(s)")

        new_m3u_content = self.reconstruct_m3u_from_channels(updated_channels)

        print(f"\n💾 Uploading updated playlist to gist...")
        success, raw_url = self.update_gist(gist_id, gist_filename, new_m3u_content)

        if success:
            print(f"✅ Gist updated successfully!")
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
    print(f"⚙️ Configuration: Erotica enabled by default, using freecustom.email")
    print(f"{'=' * 60}")

    # Configuration
    ENABLE_EROTICA = True
    TIVIMATE_ID = 41
    GITHUB_TOKEN = ""
    GIST_FILES = ["file4", "file5"]

    playlist_url = None

    # Check saved account
    print(f"\n📋 Checking saved account (no proxy)...")
    check_manager = TVTeamAccount(proxy=None, enable_erotica=ENABLE_EROTICA, playlist_app_id=TIVIMATE_ID)
    has_active_trial, saved_account = check_manager.check_saved_account_trial()

    if has_active_trial and '--force' not in sys.argv:
        print(f"\n{'=' * 60}")
        print(f"✅ USING EXISTING ACCOUNT WITH ACTIVE TRIAL")
        print(f"{'=' * 60}")
        print(f"  👤 Username: {saved_account['username']}")
        print(f"  📧 Email: {saved_account['email']}")
        print(f"  🎯 Trial: ACTIVE")
        print(f"  💾 Loaded from: {AccountManager.SAVE_FILE}")
        playlist_url = check_manager.generate_playlist_url(use_https=False)
    else:
        # Create new account with proxies
        print(f"\n🔄 Creating new account with proxies...")

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

                account_manager = TVTeamAccount(proxy=current_proxy, enable_erotica=ENABLE_EROTICA,
                                                playlist_app_id=TIVIMATE_ID)

                account = account_manager.create_and_save_account()

                if account and account.get("trial_activated"):
                    print(f"\n🎉🎉🎉 SUCCESS: New account created WITH TRIAL ACTIVATED! 🎉🎉🎉")
                    playlist_url = account.get("playlist_url")
                    break
                elif account:
                    if DEBUG: print(f"\n⚠️ Account created but trial NOT activated")
                else:
                    if DEBUG: print(f"\n❌ Account creation failed")

            except Exception as e:
                if DEBUG:
                    print(f"\n💥 Unexpected error: {e}")
                    import traceback
                    traceback.print_exc()
                continue

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

    # Update gists
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
        print("✅ All required packages are installed")
    except ImportError:
        print("❌ Please install required packages:")
        print("pip install requests")
        exit(1)

    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    main()
