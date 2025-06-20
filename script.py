import subprocess
import json

cmd = [
    "curl", "-s", "-X", "GET",
    "https://play.embyil.tv/emby/LiveTv/Programs?UserId=f77d2537830c404a8a0e616694be0964&MinEndDate=2025-06-20T20%3A50%3A14Z&MaxStartDate=2025-06-21T20%3A50%3A14Z&ImageTypeLimit=1&SortBy=StartDate&EnableTotalRecordCount=false&EnableUserData=false&EnableImages=false",
    "-H", "X-Emby-Token: e70e9dd9d9254859aa208efaadb6dfcf"
]

result = subprocess.run(cmd, capture_output=True, text=True)

print("Output:", result.stdout[:1000])
