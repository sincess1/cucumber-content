# -*- coding: utf-8 -*-
def a(appid, name):
    return f'<a href="https://store.steampowered.com/app/{appid}/"><b>{name}</b></a>'

# (marker, appid, name, pct)
games = [
    ("\U0001F6AB", 1091500, "Cyberpunk 2077", 70),
    ("\U0001F6AB", 1174180, "Red Dead Redemption 2", 75),
    ("\U0001F6AB", 3240220, "GTA V Enhanced", 50),
    ("\U0001F6AB", 990080,  "Hogwarts Legacy", 85),
    ("\U0001F6AB", 2322010, "God of War Ragnarök", 33),
    ("\U0001F6AB", 1771300, "Kingdom Come: Deliverance II", 60),
    ("\U0001F6AB", 2246340, "Monster Hunter Wilds", 58),
    ("\U0001F534", 2622380, "Elden Ring Nightreign", 25),
    ("\U0001F6AB", 2050650, "Resident Evil 4", 75),
    ("\U0001F6AB", 3017860, "DOOM: The Dark Ages", 67),
    ("\U0001F6AB", 3159330, "Assassin's Creed Shadows", 55),
    ("\U0001F534", 2183900, "Warhammer 40K: Space Marine 2", 70),
    ("\U0001F534", 1903340, "Clair Obscur: Expedition 33", 20),
    ("\U0001F6AB", 1888930, "The Last of Us Part I", 50),
    ("\U0001F6AB", 2215430, "Ghost of Tsushima", 40),
    ("\U0001F6AB", 668580,  "Atomic Heart", 75),
    ("\U0001F6AB", 489830,  "Skyrim Special Edition", 75),
    ("\U0001F534", 275850,  "No Man's Sky", 60),
    ("\U0001F534", 1681430, "RoboCop: Rogue City", 90),
]

lines = []
lines.append("\U0001F3C1 <b>Летняя распродажа Steam — последний день</b>")
lines.append("")
lines.append("Завтра вечером всё, ценники отрастают обратно — кто тянул, самое время.")
lines.append("")
inner = []
for m, appid, name, pct in games:
    inner.append(f"{m} {a(appid,name)} <b>−{pct}%</b>")
lines.append("<blockquote expandable>" + "\n".join(inner) + "</blockquote>")
lines.append("")
lines.append("\U0001F3AE и ещё <b>сотни</b> хитов — <a href=\"https://store.steampowered.com/specials/\">смотреть все</a>")
lines.append("")
lines.append("⏳ До 9 июля, 20:00 МСК")
lines.append("")
lines.append("\U0001F534 обычная скидка")
lines.append("\U0001F6AB обычная скидка, нет в РФ")
lines.append("")
lines.append("\U0001F3AE Cyberpunk, RDR2 и ещё десятки отсюда есть у нас в каталоге — по подписке, первая бесплатно: <a href=\"https://steamgate.online/ru/catalog\">наш каталог</a>")
lines.append("")
lines.append("<blockquote>\U0001F525 — успел запрыгнуть в последний вагон\n\U0001F4A9 — вечно узнаю в последний день</blockquote>")
lines.append("")
lines.append("#steam #распродажа #скидки #летняяраспродажа #cyberpunk #rdr2")

cap = "\n".join(lines)
open("caption.txt","w",encoding="utf-8").write(cap)
# visible length approx (strip tags)
import re
vis = re.sub(r"<[^>]+>","",cap)
print("VISIBLE LEN:", len(vis))
print("----")
print(cap)
