#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests, traceback, random, unicodedata, re
from datetime import datetime, timezone, timedelta

CLIENT_ID = os.environ["TENCENT_CLIENT_ID"]
ACCESS_TOKEN = os.environ["TENCENT_ACCESS_TOKEN"]
OPEN_ID = os.environ["TENCENT_OPEN_ID"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
FRIEND_B_TOKEN = os.environ["FRIEND_B_TOKEN"]
FRIEND_C_TOKEN = os.environ["FRIEND_C_TOKEN"]

TZ = timezone(timedelta(hours=8))

COL_ROOM = 0
COL_REMAIN = 1
COL_START = 2
COL_END = 3
COL_PAYMENT = 4
COL_DUE_DAY = 5    # F列：交租日（朋友C专用）
COL_STATUS = 6
COL_RENT = 7
COL_WATER = 9
COL_NET = 11

DOCS = [
    {
        "name": "悦居",
        "book_id": "300000000$NGUIfHYzcqNf",
        "sheet_id": "aopwxm",
        "range": "A1:L71",
        "title_rows": [11, 22, 33, 44, 55, 66],
        "push_to": ["owner", "friend_b"],
        "color": {"bg": "#FFF7F0", "border": "#E8853D", "title": "#C5601A"}
    },
    {
        "name": "彩虹",
        "book_id": "300000000$NowDLTtMyFxt",
        "sheet_id": "aopwxm",
        "range": "A1:L41",
        "title_rows": [15, 25, 35],
        "push_to": ["owner"],
        "color": {"bg": "#F0F5FF", "border": "#3D8BE8", "title": "#1A5FC5"}
    },
    {
        "name": "乐乐",
        "book_id": "300000000$NEkgavzHZlWi",
        "sheet_id": "aopwxm",
        "range": "A1:L54",
        "title_rows": [16, 27, 38, 49],
        "push_to": ["friend_c"],
        "color": {"bg": "#F5FFF0", "border": "#6DE83D", "title": "#3AC51A"},
        "use_f_column": True
    },
    {
        "name": "狮大",
        "book_id": "300000000$NVGckzvbFein",
        "sheet_id": "BB08J2",
        "range": "A1:L42",
        "title_rows": [11, 18, 25, 32, 39],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF5F0", "border": "#E8963D", "title": "#C5801A"},
        "use_f_column": True
    },
    {
        "name": "骆家2栋",
        "book_id": "300000000$NaIOsoNOmmry",
        "sheet_id": "BB08J2",
        "range": "A1:L32",
        "title_rows": [12, 19, 26],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF0F5", "border": "#E83D8B", "title": "#C51A6D"},
        "use_f_column": True
    }
]

TOKEN_MAP = {
    "owner": PUSHPLUS_TOKEN,
    "friend_b": FRIEND_B_TOKEN,
    "friend_c": FRIEND_C_TOKEN
}

def get_today():
    return datetime.now(TZ)

def get_today_day():
    return get_today().day

def get_today_month():
    return get_today().month

def is_first_day_of_month():
    return get_today().day == 1

def parse_day(cell):
    if not cell: return None
    cell = str(cell).strip()
    if "-" in cell: return int(cell.split("-")[-1])
    if "/" in cell: return int(cell.split("/")[-1])
    return None

def get_sheet_data(book_id, sheet_id, range_str):
    url = f"https://docs.qq.com/openapi/spreadsheet/v3/files/{book_id}/{sheet_id}/{range_str}"
    headers = {"Access-Token": ACCESS_TOKEN, "Client-Id": CLIENT_ID, "Open-Id": OPEN_ID}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"API {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    rows_raw = data.get("gridData", {}).get("rows", [])
    result = []
    for row in rows_raw:
        vals = row.get("values", [])
        if not vals: continue
        cells = []
        for v in vals:
            cv = v.get("cellValue", {})
            if not cv:
                cells.append("")
            elif v.get("dataType") == "TIME":
                t = cv.get("time", {})
                y, m, d = t.get("year", ""), t.get("month", ""), t.get("day", "")
                cells.append(f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}" if y and m and d else "")
            elif v.get("dataType") == "SELECT":
                sel = cv.get("select", {})
                options = sel.get("options", [])
                selected_values = sel.get("value", [])
                selected_texts = []
                for opt in options:
                    if opt.get("id") in selected_values:
                        selected_texts.append(opt.get("text", ""))
                cells.append(",".join(selected_texts))
            else:
                cells.append(str(cv.get("text", "") or cv.get("number", "")))
        result.append(cells)
    return result

def clean_text(s):
    if not s: return ""
    s = str(s).strip()
    s = unicodedata.normalize('NFKC', s)
    for ch in ['\u200b', '\u200c', '\u200d', '\ufeff', '\n', '\r', '\t', ' ']:
        s = s.replace(ch, '')
    return s

def safe_float(s):
    try:
        return float(str(s).strip())
    except:
        return 0.0

def check_sheet_owner(doc):
    rows = get_sheet_data(doc["book_id"], doc["sheet_id"], doc["range"])
    today = get_today()
    today_day = today.day
    first_day = is_first_day_of_month()
    title_rows = set(doc["title_rows"])
    today_due = []

    for i, row in enumerate(rows):
        rn = i + 1
        if rn in title_rows: continue
        if len(row) < 12: continue
        room = str(row[COL_ROOM]).strip() if len(row) > COL_ROOM else ""
        if not room: continue
        if not any(c.isdigit() for c in room): continue

        raw_status = str(row[COL_STATUS]) if len(row) > COL_STATUS else ""
        status = clean_text(raw_status)
        move = str(row[COL_END]).strip() if len(row) > COL_END else ""
        d = parse_day(move)

        if first_day and status in ("付", "无"):
            status = ""

        rent_str = str(row[COL_RENT]).strip() if len(row) > COL_RENT else "0"
        water_str = str(row[COL_WATER]).strip() if len(row) > COL_WATER else "0"
        net_str = str(row[COL_NET]).strip() if len(row) > COL_NET else "0"
        payment_str = str(row[COL_PAYMENT]).strip() if len(row) > COL_PAYMENT else "月付"
        start_str = str(row[COL_START]).strip() if len(row) > COL_START else ""
        remain_str = str(row[COL_REMAIN]).strip() if len(row) > COL_REMAIN else ""

        rent_val = safe_float(rent_str)
        water_val = safe_float(water_str)
        net_val = safe_float(net_str)
        total_payment = rent_val + water_val + net_val

        info = {
            "room": room,
            "rent": rent_str,
            "water": water_str,
            "net": net_str,
            "total": f"{total_payment:.0f}" if total_payment == int(total_payment) else f"{total_payment:.2f}",
            "payment": payment_str or "月付",
            "rent_start": start_str,
            "rent_end": move,
            "lease_remain": remain_str,
            "status": status,
            "f_due_day": str(row[COL_DUE_DAY]).strip() if len(row) > COL_DUE_DAY else ""
        }

        if status == "付":
            continue
        if status == "欠":
            today_due.append(info)
            continue
        if status == "退":
            if d is not None and d <= today_day:
                today_due.append(info)
            continue
        if d is not None and d <= today_day:
            today_due.append(info)

    return today_due

def check_sheet_friend_c(doc):
    rows = get_sheet_data(doc["book_id"], doc["sheet_id"], doc["range"])
    today = get_today()
    today_month = today.month
    today_day = today.day
    title_rows = set(doc["title_rows"])
    today_due = []

    for i, row in enumerate(rows):
        rn = i + 1
        if rn in title_rows: continue
        if len(row) < 12: continue
        room = str(row[COL_ROOM]).strip() if len(row) > COL_ROOM else ""
        if not room: continue
        if not any(c.isdigit() for c in room): continue

        f_val = str(row[COL_DUE_DAY]).strip() if len(row) > COL_DUE_DAY else ""

        if not f_val:
            continue

        if "✔" in f_val:
            continue

        nums = re.findall(r'\d+', f_val)
        if not nums:
            continue

        if len(nums) >= 2:
            due_month = int(nums[0])
            due_day = int(nums[-1])
        else:
            due_month = today_month
            due_day = int(nums[0])

        if due_month != today_month or due_day != today_day:
            continue

        rent_str = str(row[COL_RENT]).strip() if len(row) > COL_RENT else "0"
        water_str = str(row[COL_WATER]).strip() if len(row) > COL_WATER else "0"
        net_str = str(row[COL_NET]).strip() if len(row) > COL_NET else "0"
        payment_str = str(row[COL_PAYMENT]).strip() if len(row) > COL_PAYMENT else "月付"
        start_str = str(row[COL_START]).strip() if len(row) > COL_START else ""
        end_str = str(row[COL_END]).strip() if len(row) > COL_END else ""
        remain_str = str(row[COL_REMAIN]).strip() if len(row) > COL_REMAIN else ""

        rent_val = safe_float(rent_str)
        water_val = safe_float(water_str)
        net_val = safe_float(net_str)
        total_payment = rent_val + water_val + net_val

        info = {
            "room": room,
            "rent": rent_str,
            "water": water_str,
            "net": net_str,
            "total": f"{total_payment:.0f}" if total_payment == int(total_payment) else f"{total_payment:.2f}",
            "payment": payment_str or "月付",
            "rent_start": start_str,
            "rent_end": end_str,
            "lease_remain": remain_str,
            "status": "",
            "f_due_day": f_val
        }
        today_due.append(info)

    return today_due

def check_sheet(doc):
    if doc.get("use_f_column"):
        return check_sheet_friend_c(doc)
    else:
        return check_sheet_owner(doc)

def check_token_expiry():
    try:
        p = ACCESS_TOKEN.split(".")[1]
        p += "=" * (4 - len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        exp = d.get("exp", 0)
        return (exp - datetime.now(TZ).timestamp()) / 86400 <= 7
    except: return False

def room_html(room):
    name = room["room"]
    rent = room.get("rent", "0")
    water = room.get("water", "0")
    net = room.get("net", "0")
    total = room.get("total", "0")
    pay = room.get("payment", "月付")
    start = room.get("rent_start", "")
    end = room.get("rent_end", "")
    lease_remain = room.get("lease_remain", "")
    st = room.get("status", "")

    if st == "欠":
        tag = '<span style="color:#D4380D;font-weight:bold">【欠租】</span>'
    elif st == "退":
        tag = '<span style="color:#E8963D;font-weight:bold">【退租】</span>'
    else:
        tag = ""

    lease = f"{start} ~ {end}" if start and end else "未知租期"
    net_display = net if (net and net != "0") else "&nbsp;"
    water_display = water if (water and water != "0") else "&nbsp;"
    pay_info = pay

    months_text = ""
    if lease_remain:
        nums = re.findall(r'\d+', lease_remain)
        if nums:
            months_text = f" · 剩余{nums[0]}个月"

    line1 = (
        f'<b style="font-size:14px;color:#333">{name}</b> {tag}'
        f'<span style="font-size:13px;color:#333"> ¥{rent}/月</span> '
        f'<span style="font-size:13px;color:#D4380D;font-weight:bold">需支付：¥{total}</span> '
        f'<span style="font-size:11px;color:#666">（水费{water_display} 网杂费{net_display}）</span>'
    )
    line2 = f'<span style="font-size:11px;color:#999">{lease} · {pay_info}{months_text}</span>'

    return f'<div style="margin:0;line-height:1.5">{line1}<br>{line2}</div>'

def doc_card(doc, today_list):
    if not today_list: return ""
    parts = [room_html(r) for r in today_list]
    c = doc["color"]
    return f'''<div style="margin-bottom:12px">
        <h3 style="font-size:16px;margin:0 0 8px;padding-left:6px;border-left:3px solid {c['border']};color:{c['title']}">{doc['name']}</h3>
        <div style="background:{c['bg']};border-radius:8px;padding:10px 13px">{"".join(parts)}</div>
    </div>'''

def send_pushplus(token, title, content):
    resp = requests.post("http://www.pushplus.plus/send", json={
        "token": token, "title": title, "content": content, "template": "html"
    }, timeout=10)
    print(f"PushPlus 返回: {resp.json()}")

def main():
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        target = None
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if event_path:
            try:
                with open(event_path, "r") as f:
                    event = json.load(f)
                target = event.get("inputs", {}).get("target", None)
            except:
                pass

        if event_name == "schedule":
            targets = ["owner", "friend_b", "friend_c"]
            print("定时任务：推送给 owner, friend_b, friend_c")
        elif target == "all":
            targets = ["owner"]
            for doc in DOCS:
                if "owner" not in doc["push_to"]:
                    doc["push_to"].append("owner")
            print("手动触发（全部公寓）：推送给 owner")
        elif target:
            targets = [target]
            print(f"手动触发：推送给 {target}")
        else:
            targets = ["owner"]
            print("无参数，默认推送给 owner")

        all_data = {}
        for doc in DOCS:
            due_list = check_sheet(doc)
            all_data[doc["name"]] = due_list
            print(f"{doc['name']}: 需处理{len(due_list)}间")

        for t in targets:
            token = TOKEN_MAP.get(t)
            if not token:
                print(f"未找到 {t} 的 token")
                continue

            cards = []
            total_due = 0
            for doc in DOCS:
                if t not in doc["push_to"]:
                    continue
                due = all_data.get(doc["name"], [])
                if due:
                    card = doc_card(doc, due)
                    if card:
                        cards.append(card)
                        total_due += len(due)

            now = datetime.now(TZ).strftime("%H:%M")
            today_str = datetime.now(TZ).strftime("%Y-%m-%d")
            rand = random.randint(10000, 99999)
            if cards:
                title = f"🏠 收租提醒 | 交租{total_due}间 | {total_due}间待处理 · {now}"
                html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租/退租提醒 · {today_str}</h2>'
                html += "".join(cards)
                html += f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total_due} 间待处理</div>'
                html += f"<!-- {rand} -->"
                send_pushplus(token, title, html)
                print(f"已推送 {t}: {title}")
            else:
                title = f"🏠 收租提醒 | 今日无待处理 · {now}"
                html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 今日无待处理 · {today_str}</h2><p>所有房间已付清或无到期。</p><!-- {rand} -->'
                send_pushplus(token, title, html)
                print(f"已推送 {t}: 今日无待处理")

        if target == "all":
            for doc in DOCS:
                if "owner" in doc["push_to"] and doc["name"] not in ["悦居", "彩虹"]:
                    doc["push_to"].remove("owner")

        if check_token_expiry():
            send_pushplus(PUSHPLUS_TOKEN, "⚠️ Token即将过期",
                          '<div style="color:#D4380D;font-size:15px;font-weight:bold">请及时续期Token</div><p>打开 https://docs.qq.com/open/developers/ 点"重置"获取新token</p>')
        print("脚本正常结束")
    except Exception as e:
        err_info = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(err_info)
        try:
            send_pushplus(PUSHPLUS_TOKEN, "收租提醒异常", f"❌ {err_info}")
        except: pass
        sys.exit(1)

if __name__ == "__main__":
    main()
