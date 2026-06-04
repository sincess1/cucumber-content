import urllib.request, urllib.parse, json, os, mimetypes

BOT_TOKEN = "8092050995:AAETRNAP1FcNNPAPS7D_HzrrY-LTj0cNmLo"
CHAT_ID = "@sdsfasdfdsfas"
PHOTO_PATH = "/home/user/cucumber-content/banner.jpg"
CAPTION = (
    "Маленькая штука, но за бесплатно грех не забрать — <b>Winexy</b> это аркада, "
    "где катаешь шарики из разных материалов через лабиринты и пазлы. "
    "Деревянный горит, металлический — нет, такие нюансы. "
    "Отзывы смешанные, но до завтра уже не успеть.\n\n"
    "#халява #steam #инди #бесплатно #Winexy #аркада #головоломка"
)
REPLY_MARKUP = json.dumps({
    "inline_keyboard": [[{
        "text": "🎱 Забрать Winexy",
        "url": "https://store.steampowered.com/app/577740/Winexy/"
    }]]
})

BOUNDARY = "----CucumberFormBoundary7MA4YWxkTrZu0gW"

def encode_multipart(fields, files):
    body = b""
    for key, val in fields.items():
        body += f"--{BOUNDARY}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += val.encode("utf-8") + b"\r\n"
    for key, (filename, data, ctype) in files.items():
        body += f"--{BOUNDARY}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        body += data + b"\r\n"
    body += f"--{BOUNDARY}--\r\n".encode()
    return body

with open(PHOTO_PATH, "rb") as f:
    photo_data = f.read()

fields = {
    "chat_id": CHAT_ID,
    "parse_mode": "HTML",
    "caption": CAPTION,
    "reply_markup": REPLY_MARKUP,
}
files = {
    "photo": ("banner.jpg", photo_data, "image/jpeg"),
}

body = encode_multipart(fields, files)
url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
req = urllib.request.Request(
    url,
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read().decode())
    print(json.dumps(result, ensure_ascii=False, indent=2))
