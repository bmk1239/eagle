import subprocess
import json
from datetime import datetime, timedelta, timezone

# Step 1: Set values
token = "e70e9dd9d9254859aa208efaadb6dfcf"
user_id = "f77d2537830c404a8a0e616694be0964"

now = datetime.now(timezone.utc)
later = now + timedelta(hours=24)

min_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
max_start = later.strftime("%Y-%m-%dT%H:%M:%SZ")

url = (
    f"https://play.embyil.tv/emby/LiveTv/Programs?"
    f"UserId={user_id}"
    f"&MinEndDate={min_end}"
    f"&MaxStartDate={max_start}"
    f"&ImageTypeLimit=1"
    f"&SortBy=StartDate"
    f"&EnableTotalRecordCount=false"
    f"&EnableUserData=false"
    f"&EnableImages=false"
)

# Step 2: Run curl command via subprocess
cmd = [
    "curl", "-s", "-X", "GET", url,
    "-H", f"X-Emby-Token: {token}"
]

result = subprocess.run(cmd, capture_output=True, text=True)

# Step 3: Parse and print result
try:
    data = json.loads(result.stdout)
    print("✅ Success, items:", len(data.get("Items", [])))
except Exception as e:
    print("❌ Failed to parse:", e)
    print("Output was:", result.stdout[:1000])
