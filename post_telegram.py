import urllib.request, urllib.parse, json, os

TOKEN = "8092050995:AAETRNAP1FcNNPAPS7D_HzrrY-LTj0cNmLo"
CHAT   = "@sdsfasdfdsfas"
URL    = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"

caption = (
    "🎁 В Steam отдают <b>Winexy</b> — маленькая инди про 3D-шарик с физикой, "
    "лабиринтами и пазлами. Не ААА, но честная игрулька, которая сейчас стоит "
    "ровно ноль рублей.\n\n"
    "До 5 июня, потом снова за деньги.\n\n"
    "#халява #steam #инди #бесплатно #Winexy #игры #freegames"
)

reply_markup = json.dumps({
    "inline_keyboard": [[
        {"text": "🎱 Забрать Winexy",
         "url": "https://store.steampowered.com/app/577740/Winexy"}
    ]]
})

boundary = "----FormBoundary7MA4YWxkTrZu0gW"

def field(name, value):
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode()

with open("banner.jpg", "rb") as f:
    photo_data = f.read()

body = (
    field("chat_id", CHAT) +
    field("parse_mode", "HTML") +
    field("caption", caption) +
    field("reply_markup", reply_markup) +
    (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="banner.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() +
    photo_data +
    f"\r\n--{boundary}--\r\n".encode()
)

req = urllib.request.Request(
    URL,
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
        print(json.dumps(resp, ensure_ascii=False, indent=2))
except Exception as e:
    print("ERROR:", e)
