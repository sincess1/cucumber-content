import urllib.request, urllib.parse, json, os, mimetypes

TOKEN = "8092050995:AAETRNAP1FcNNPAPS7D_HzrrY-LTj0cNmLo"
CHAT  = "@sdsfasdfdsfas"
PHOTO = "banner.jpg"
CAPTION = """<b>Suicide Squad: Kill the Justice League</b> — $70 игра за три доллара, это уже не скидка, это насмешка над ценниками 💀 Rocksteady, живые злодеи, кооп — за такие деньги смешно отказываться.

Скидка без дедлайна, но вечно такое не лежит.

#SuicideSquad #Steam #скидки #TopDeals #экшен #кооп #шутер"""

REPLY_MARKUP = json.dumps({"inline_keyboard": [[
    {"text": "💀 Купить Suicide Squad", "url": "https://itad.link/018d9386-d629-7249-ad1f-1c15d86215a1/"}
]]})

boundary = "----PythonBoundary7x92"
CRLF = b"\r\n"

def field(name, value):
    return (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f'{value}\r\n'
    ).encode()

with open(PHOTO, "rb") as f:
    photo_data = f.read()

body = (
    field("chat_id", CHAT) +
    field("parse_mode", "HTML") +
    field("caption", CAPTION) +
    field("reply_markup", REPLY_MARKUP) +
    f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="banner.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() +
    photo_data + CRLF +
    f'--{boundary}--\r\n'.encode()
)

url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
req = urllib.request.Request(url, data=body,
      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read())
print(json.dumps(result, ensure_ascii=False, indent=2))
