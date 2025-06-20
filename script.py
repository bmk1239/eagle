import requests
from datetime import datetime, timedelta, timezone

token = "e70e9dd9d9254859aa208efaadb6dfcf"
user_id = "f77d2537830c404a8a0e616694be0964"

now = datetime.now(timezone.utc)
later = now + timedelta(hours=24)

params = {
    "UserId": user_id,
    "MinEndDate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "MaxStartDate": later.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "channelIds": "2436645,2299409",
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false"
}

headers = {
    "X-Emby-Token": token
}

r = requests.get("https://play.embyil.tv/emby/LiveTv/Programs", params=params, headers=headers)

print("Status:", r.status_code)
print("Response:", r.text[:300])
