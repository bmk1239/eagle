import requests

url = "https://play.embyil.tv/emby/LiveTv/Programs"

params = {
    "UserId": "f77d2537830c404a8a0e616694be0964",
    "MinEndDate": "2025-06-20T20:50:14Z",
    "MaxStartDate": "2025-06-21T20:50:14Z",
    "ImageTypeLimit": 1,
    "SortBy": "StartDate",
    "EnableTotalRecordCount": "false",
    "EnableUserData": "false",
    "EnableImages": "false"
}

headers = {
    "X-Emby-Token": "e70e9dd9d9254859aa208efaadb6dfcf"
}

response = requests.get(url, params=params, headers=headers)

print("Status Code:", response.status_code)
print("Response Body:", response.text[:1000])
