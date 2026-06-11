import urllib.request, json

TOKEN_BLOG = "a698d9c9c4472d9fc00f3a5c70c9293c347199bc8432cb61b617c0d65ac94a70"
file_id = "AgACAgUAAyEGAATe-OcgAAIBdmop_P0ObVnYhlVD_CnlezVS1sEoAAL-Dmsb0OxQVctpTZeb7l2YAQADAgADeQADOwQ"
caption = open("caption.txt", encoding="utf-8").read()

payload = {
    "file_id": file_id,
    "caption": caption,
    "buttons": [[{"text": "📰 Подробнее", "url": "https://www.gematsu.com/2026/05/unrailed-2-back-on-track-launches-june-11"}]]
}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    "https://steamgate.online/api/integrations/recent-post",
    data=data,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN_BLOG}"}
)
try:
    resp = urllib.request.urlopen(req, timeout=15)
    print(resp.read().decode())
except Exception as e:
    print("recent-post error (non-critical):", e)
