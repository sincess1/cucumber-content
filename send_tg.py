import urllib.request, urllib.parse, json, sys

TOKEN = "8092050995:AAETRNAP1FcNNPAPS7D_HzrrY-LTj0cNmLo"
CHAT = "@sdsfasdfdsfas"

caption = open("caption.txt", encoding="utf-8").read()
reply_markup = json.dumps({"inline_keyboard": [[{"text": "📰 Подробнее", "url": "https://www.gematsu.com/2026/05/unrailed-2-back-on-track-launches-june-11"}]]})

import mimetypes, uuid

boundary = uuid.uuid4().hex
body_parts = []

def add_field(name, value):
    body_parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
    )

def add_file(name, filename, data, mime):
    body_parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
        + data + b'\r\n'
    )

add_field("chat_id", CHAT)
add_field("parse_mode", "HTML")
add_field("caption", caption)
add_field("reply_markup", reply_markup)

with open("banner.jpg", "rb") as f:
    add_file("photo", "banner.jpg", f.read(), "image/jpeg")

body_parts.append(f'--{boundary}--\r\n'.encode("utf-8"))
body = b"".join(body_parts)

req = urllib.request.Request(
    f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read())
print(json.dumps(result, ensure_ascii=False, indent=2))
