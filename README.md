# eagle

fetch("https://www.hot.net.il/HotCmsApiFront/api/ProgramsSchedual/GetProgramsSchedual", {
  "headers": {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
  },
  "referrer": "https://www.hot.net.il/heb/tv/tvguide/",
  "referrerPolicy": "strict-origin-when-cross-origin",
  "body": "{\"ProgramsStartDateTime\":\"2025/06/30 00:00:00\",\"ProgramsEndDateTime\":\"2025/07/05 23:59:59\"}",
  "method": "POST",
  "mode": "cors",
  "credentials": "include"
});
