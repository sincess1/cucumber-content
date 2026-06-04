import urllib.request, urllib.parse, json, mimetypes, os

TOKEN = "8092050995:AAETRNAP1FcNNPAPS7D_HzrrY-LTj0cNmLo"
CHAT_ID = "@sdsfasdfdsfas"
BANNER = "/home/user/cucumber-content/banner.jpg"

caption = (
    "Мелкая инди <b>Winexy</b> — это 3D-пазлы с физическими шарами из разных материалов. "
    "Деревянный горит и поджигает вокруг, металлический не боится огня — и всё это надо как-то "
    "использовать на уровнях. Отзывы смешанные, но бесплатно — грех не попробовать, тем более "
    "завтра вечером уже всё.\n\n"
    "#халява #steam #инди #паззл #бесплатно #winexy #steamgate"
)

reply_markup = json.dumps({
    "inline_keyboard": [[{
        "text": "🎱 Забрать Winexy",
        "url": "https://store.steampowered.com/app/577740/Winexy"
    }]]
})

boundary = "----BannerBoundary7"
CRLF = b"\r\n"

def field(name, value):
    return (
        f"--{boundary}".encode() + CRLF +
        f'Content-Disposition: form-data; name="{name}"'.encode() + CRLF +
        CRLF +
        value.encode("utf-8") + CRLF
    )

def file_field(name, filename, data, ctype):
    return (
        f"--{boundary}".encode() + CRLF +
        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode() + CRLF +
        f"Content-Type: {ctype}".encode() + CRLF +
        CRLF +
        data + CRLF
    )

body = (
    field("chat_id", CHAT_ID) +
    field("parse_mode", "HTML") +
    field("caption", caption) +
    field("reply_markup", reply_markup) +
    file_field("photo", "banner.jpg", open(BANNER, "rb").read(), "image/jpeg") +
    f"--{boundary}--".encode() + CRLF
)

url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
req = urllib.request.Request(
    url,
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST"
)
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(json.dumps(result, ensure_ascii=False, indent=2))
