# -*- coding: utf-8 -*-
import re
def a(appid, name):
    return f'<a href="https://store.steampowered.com/app/{appid}/"><b>{name}</b></a>'

# trimmed to top 12 headliners so body+tail fit 1024
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
    ("\U0001F534", 2183900, "Warhammer 40K: Space Marine 2", 70),
    ("\U0001F534", 1681430, "RoboCop: Rogue City", 90),
]
lines = []
lines.append("\U0001F3C1 <b>Летняя распродажа Steam — последний день</b>")
lines.append("")
lines.append("Завтра вечером всё, ценники отрастают обратно — кто тянул, самое время.")
lines.append("")
inner = [f"{m} {a(appid,name)} <b>−{pct}%</b>" for m, appid, name, pct in games]
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

tail = "\n\n— — —\n\U0001F4CB тир-3 · финал Летней распродажи Steam (последний день, до 09.07)\nальтернативы: халява — дубли, новинок каталога 0, ААА-новостей/событий нет\nкаталог: почти вся подборка у нас · VK: 📱 на карточке · блог: нет · постов: 1"

cap = "\n".join(lines) + tail
open("approve_caption.txt","w",encoding="utf-8").write(cap)
vis=re.sub(r"<[^>]+>","",cap)
print("approve UTF-16 units:", len(vis.encode('utf-16-le'))//2)
