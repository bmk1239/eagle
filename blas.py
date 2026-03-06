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

        # Generate timezone - EXACTLY from fetch
        timezones = ["Asia/Jerusalem"]

        # Generate language - EXACTLY from fetch
        languages = ["he-IL"]

        # Generate user agent - EXACTLY from fetch
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
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

        # Setup headers - EXACTLY from fetch
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
        """Setup headers - EXACTLY matching fetch request"""
        headers = {
            "User-Agent": self.fingerprint_data["user_agent"],
            "Accept": "*/*",
            "Accept-Language": "he-IL,he;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/register?parentId=310175&email={quote('test@test.com')}",
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

                # Make request
                resp = self.session.request(method, url, timeout=30, **kwargs)

                if debug and DEBUG:
                    print(f"  🔍 Request: {method} {url}")
                    print(f"  Response Status: {resp.status_code}")

                # Handle rate limits
                if resp.status_code == 429:
                    if DEBUG: print(f"  ⚠️ Rate limited, waiting 60 seconds...")
                    time.sleep(60)
                    continue

                return resp

            except Exception as e:
                if DEBUG: print(f"  ⚠️ Request error: {str(e)[:100]}, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(2)
                continue

        return None

    def get_captcha(self) -> Optional[Dict]:
        """Get captcha"""
        if DEBUG: print("  🔍 Getting captcha...")
        
        # Clear any previous cache headers
        self.session.headers.update({
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        })
        
        resp = self.safe_request("GET", f"{self.base_url}/v3/auth/captcha/generate", debug=False)

        if not resp:
            if DEBUG: print(f"  ❌ Failed to get captcha: No response")
            return None

        if DEBUG: print(f"  Captcha response status: {resp.status_code}")

        if resp.status_code != 200:
            if DEBUG: print(f"  ❌ Failed to get captcha: {resp.status_code}")
            return None

        try:
            data = resp.json()
            if DEBUG: print(f"  Captcha response data: {data}")
            
            if "data" in data:
                return data["data"]
            return None

        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing captcha: {str(e)[:100]}")
            return None

    def solve_captcha(self, captcha_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Solve captcha - EXACTLY matching fetch request"""
        captcha_id = captcha_data.get("captchaId")
        challenge = captcha_data.get("challenge", {})

        if not captcha_id:
            if DEBUG: print("  ❌ No captcha ID provided")
            return None, None

        if DEBUG:
            print(f"  Captcha ID: {captcha_id}")
            print(f"  Challenge data: {challenge}")

        # Get slotX from challenge - this is the target position
        slot_x = challenge.get("slotX", 110)
        
        if DEBUG: print(f"  🎯 Target slot X: {slot_x}")

        # Use EXACT trail from fetch request
        trail = [
            {"x": 0, "t": 0},
            {"x": 5, "t": 98},
            {"x": 53, "t": 134},
            {"x": 94, "t": 170},
            {"x": 105, "t": 204},
            {"x": 147, "t": 240},
            {"x": 161, "t": 278},
            {"x": 167, "t": 321},
            {"x": 168, "t": 364},
            {"x": 173, "t": 406},
            {"x": 180, "t": 441},
            {"x": 184, "t": 490},
            {"x": 185, "t": 612},
            {"x": 185, "t": 1338}
        ]

        # Verify captcha - EXACT payload from fetch
        payload = {
            "captchaId": captcha_id,
            "offsetX": slot_x,  # Use the exact slot_x from challenge
            "trail": trail
        }
        
        if DEBUG: print(f"  Payload: {payload}")

        resp = self.safe_request(
            "POST",
            f"{self.base_url}/v3/auth/captcha/verify",
            json=payload,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache"
            },
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
            if DEBUG: print(f"  Verification response: {result}")

            # Check response - from fetch it returns data with proof
            if "data" in result:
                proof_token = result["data"].get("proof")
                if proof_token:
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
        """Start quick registration - EXACTLY matching fetch"""
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

        # Start quick registration - EXACT form data from fetch
        form_data = f"email={quote(email)}&captchaId={quote(captcha_id)}&captchaSolution={quote(proof_token)}&lang=US"

        if DEBUG: print(f"  Registration form data: {form_data}")

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
            
            # Check for success
            if result.get("data", {}).get("ok") or result.get("success"):
                if DEBUG: print(f"  ✓ Registration started successfully")
                return True
            else:
                if DEBUG: print(f"  ❌ Registration not successful")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing registration response: {str(e)[:100]}")
            return False

    def quick_register_verify(self, email: str) -> bool:
        """Verify email with code - EXACTLY matching fetch"""
        # Get verification code
        code = self.temp_mail.get_verification_code(timeout=180)
        if not code:
            if DEBUG: print("  ❌ No verification code received")
            return False

        # Complete registration - EXACT form data from fetch
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

        # Prepare login data
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
                if DEBUG: print(f"  ❌ Login failed")
                return False
        except Exception as e:
            if DEBUG: print(f"  ❌ Error parsing login response: {e}")
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
            if DEBUG: print(f"  ❌ Trial check failed")
            return None

        try:
            data = resp.json()
            trial_data = data.get("data", {})
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
            except:
                pass
        return False

    def toggle_erotica(self, enable: bool = True) -> bool:
        """Toggle erotica content on/off"""
        if not self.is_authenticated:
            return False

        print(f"  {'🔞' if enable else '🚫'} Setting erotica content to {'ON' if enable else 'OFF'}...")

        if not self.get_csrf_token():
            return False

        erotica_data = {
            "showPorno": "1" if enable else "0"
        }

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

        return resp and resp.status_code == 200

    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self.is_authenticated:
            return None

        resp = self.safe_request("GET", f"{self.base_url}/v3/profile", debug=False)

        if not resp or resp.status_code != 200:
            return None

        try:
            data = resp.json()
            return data.get("data", {})
        except:
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

        # Toggle erotica
        erotica_set = False
        if self.enable_erotica:
            print(f"\n  🔄 Step 7/7: Setting erotica preference...")
            erotica_set = self.toggle_erotica(enable=True)

        # Get playlist URL
        print(f"\n  🔄 Getting playlist URL...")
        playlist_url = self.generate_playlist_url(use_https=False)

        account_data = {
            "username": email.split('@')[0],
            "password": "QuickRegisterPassword",
            "email": email,
            "trial_activated": trial_activated,
            "playlist_url": playlist_url,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return account_data

    def check_saved_account_trial(self) -> Tuple[bool, Optional[Dict]]:
        """Check if saved account has active trial"""
        saved_account = AccountManager.load_account()

        if not saved_account:
            return False, None

        print(f"\n  🔍 Checking trial status for saved account: {saved_account['username']}")

        if not self.login(saved_account['username'], saved_account['password']):
            print(f"  ❌ Failed to login with saved credentials")
            try:
                os.remove(AccountManager.SAVE_FILE)
            except:
                pass
            return False, None

        trial_status = self.check_trial_status()

        if trial_status and trial_status.get('hasActiveTrial'):
            print(f"  ✅ Trial is ACTIVE")
            return True, saved_account

        return False, saved_account

    def create_and_save_account(self) -> Optional[Dict]:
        """Create new account and save credentials if trial activated"""
        account = self.complete_account_creation()

        if account and account.get("trial_activated"):
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

        resp = self.safe_request("GET", f"{self.base_url}/v3/playlists?slot=0", debug=False)

        if not resp or resp.status_code != 200:
            return None

        try:
            data = resp.json().get("data", {})
            
            # Try uniqId first
            uniq_id = data.get("uniqId")
            if uniq_id:
                return uniq_id

            # Try items
            items = data.get("items", [])
            for item in items:
                link = item.get("link", "")
                if "/pl/" in link:
                    parts = link.split("/")
                    if len(parts) >= 5:
                        return parts[4]

            return None

        except:
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
        except:
            pass

        # Source 2: SSLProxies
        try:
            resp = self.session.get("https://www.sslproxies.org/", timeout=10)
            if resp.status_code == 200:
                pattern = r'(\d+\.\d+\.\d+\.\d+):(\d+)'
                matches = re.findall(pattern, resp.text)
                for ip, port in matches[:50]:
                    proxies.append(f"http://{ip}:{port}")
                if DEBUG: print(f"✓ Got {len(matches)} proxies from SSLProxies")
        except:
            pass

        # Remove duplicates
        unique_proxies = list(set(proxies))
        if DEBUG: print(f"\n📊 Total unique proxies found: {len(unique_proxies)}")

        return unique_proxies

    def test_proxy_simple(self, proxy: str) -> bool:
        """Simple proxy test"""
        try:
            response = requests.get(
                "http://httpbin.org/ip",
                proxies={"http": proxy, "https": proxy},
                timeout=5,
                verify=False
            )
            return response.status_code == 200
        except:
            return False


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
                return None

            return data
        except:
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
                return None, None

            gists = response.json()

            for gist in gists:
                files = gist.get('files', {})
                if filename in files:
                    gist_id = gist['id']
                    # Get content
                    gist_response = requests.get(
                        f"https://api.github.com/gists/{gist_id}",
                        headers=self.headers
                    )
                    if gist_response.status_code == 200:
                        gist_data = gist_response.json()
                        file_info = gist_data['files'][filename]
                        content = file_info.get('content', '')
                        return gist_id, content

            return None, None

        except:
            return None, None

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

            return response.status_code == 200, f"https://gist.githubusercontent.com/anon/{gist_id}/raw/{filename}"
        except:
            return False, None

    def download_playlist(self, playlist_url):
        """Download playlist from URL"""
        try:
            response = requests.get(playlist_url, timeout=10)
            if response.status_code == 200:
                return response.text
        except:
            pass
        return None

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

        print(f"\n🌐 Downloading reference playlist...")
        playlist_content = self.download_playlist(playlist_url)

        if not playlist_content:
            print("❌ Failed to download reference playlist")
            return False

        # Simple check if content changed
        if gist_content == playlist_content:
            print("\n✅ No updates needed - content is identical")
            return True

        print(f"\n📈 Content differs - updating...")

        print(f"\n💾 Uploading updated playlist to gist...")
        success, raw_url = self.update_gist(gist_id, gist_filename, playlist_content)

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

        for current_proxy in proxies[:5]:  # Try first 5 proxies
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

            except Exception as e:
                if DEBUG:
                    print(f"\n💥 Error: {e}")
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
