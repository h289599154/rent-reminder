#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests, traceback, random
from datetime import datetime, timezone, timedelta

CLIENT_ID = os.environ["TENCENT_CLIENT_ID"]
ACCESS_TOKEN = os.environ["TENCENT_ACCESS_TOKEN"]
OPEN_ID = os.environ["TENCENT_OPEN_ID"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
FRIEND_B_TOKEN = os.environ["FRIEND_B_TOKEN"]
FRIEND_C_TOKEN = os.environ["FRIEND_C_TOKEN"]

TZ = timezone(timedelta(hours=8))

DOCS = [
    {
        "name": "悦居",
        "book_id": "300000000$NGUIfHYzcqNf",
        "sheet_id": "aopwxm",
        "range": "A1:H80",
        "skip_rows": [11, 22, 33, 44, 55, 66],
        "push_to": ["owner", "friend_b"],
        "color": {"bg": "#FFF7F0", "border": "#E8853D", "title": "#C5601A"}
    },
    {
        "name": "彩虹",
        "book_id": "300000000$NowDLTtMyFxt",
        "sheet_id": "aopwxm",
        "range": "A1:H50",
        "skip_rows": [15, 25, 35],
        "push_to": ["owner"],
        "color": {"bg": "#F0F5FF", "border": "#3D8BE8", "title": "#1A5FC5"}
    },
    {
        "name": "乐乐",
        "book_id": "300000000$NEkgavzHZlWi",
        "sheet_id": "aopwxm",
        "range": "A1:H200",
        "skip_rows": [],
        "push_to": ["friend_c"],
        "color": {"bg": "#F5FFF0", "border": "#6DE83D", "title": "#3AC51A"}
    },
    {
        "name": "狮大",
        "book_id": "300000000$NVGckzvbFein",
        "sheet_id": "BB08J2",
        "range": "A1:H150",
        "skip_rows": [],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF5F0", "border": "#E8963D", "title": "#C5801A"}
    },
    {
        "name": "骆家2栋",
        "book_id": "300000000$NaIOsoNOmmry",
        "sheet_id": "BB08J2",
        "range": "A1:H200",
        "skip_rows": [],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF0F5", "border": "#E83D8B", "title": "#C51A6D"}
    }
]

TOKEN_MAP = {
    "owner": PUSHPLUS_TOKEN,
    "friend_b": FRIEND_B_TOKEN,
    "friend_c": FRIEND_C_TOKEN
}

def get_today_day():
    return datetime.now(TZ).day

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
            else:
                cells.append(str(cv.get("text", "") or cv.get("number", "")))
        result.append(cells)
    return result

def check_sheet(doc):
    """
    严格按 Excel 公式逻辑：
    1. G列包含「付」或「无」→ 跳过
    2. G列包含「欠」→ 强制加入提醒
    3. D列非空且退租日日数 = 今天 → 加入提醒
    """
    rows = get_sheet_data(doc["book_id"], doc["sheet_id"], doc["range"])
    today = get_today_day()
    today_due = []
    skip = set(doc["skip_rows"])
    for i, row in enumerate(rows):
        rn = i + 1
        if rn in skip: continue
        if len(row) < 8: continue
        room = str(row[0]).strip() if row[0] else ""
        if not room: continue

        raw_status = str(row[6]).strip() if len(row) > 6 else ""
        options = [opt.strip() for opt in raw_status.split(",") if opt.strip()]

        # 只要包含「付」或「无」就跳过
        if any("付" in opt or "无" in opt for opt in options):
            continue

        # 构建房间信息
        info = {
            "room": room,
            "rent": str(row[7]).strip() if len(row) > 7 else "",
            "payment": str(row[4]).strip() if len(row) > 4 else "月付",
            "rent_start": str(row[2]).strip() if len(row) > 2 else "",
            "rent_end": str(row[3]).strip() if len(row) > 3 else ""
        }

        # 条件1: G列包含「欠」→ 强制加入
        if any("欠" in opt for opt in options):
            today_due.append(info)
            continue

        # 条件2: 退租日非空且日数 = 今天
        move = info["rent_end"]
        d = parse_day(move)
        if move and d is not None and d == today:
            today_due.append(info)

    return today_due

def check_token_expiry():
    try:
        p = ACCESS_TOKEN.split(".")[1]
        p += "=" * (4 - len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        exp = d.get("exp", 0)
        return (exp - datetime.now(TZ).timestamp()) / 86400 <= 7
    except: return False

def room_html(room):
    rent = room.get("rent", "") or "?"
    pay = room.get("payment", "") or "月付"
    name = room["room"]
    start = room.get("rent_start", "")
    end = room.get("rent_end", "")
    lease = f"{start} ~ {end}" if start and end else "未知租期"
    return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#333">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{lease} · {pay}</span></div>'

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
        all_data = {}
        for doc in DOCS:
            today_due = check_sheet(doc)
            all_data[doc["name"]] = today_due
            print(f"{doc['name']}: 需交租{len(today_due)}间")

        for target, token in TOKEN_MAP.items():
            if not token: continue
            cards = []
            total_due = 0
            for doc in DOCS:
                if target not in doc["push_to"]: continue
                due_list = all_data.get(doc["name"], [])
                if due_list:
                    card = doc_card(doc, due_list)
                    if card:
                        cards.append(card)
                        total_due += len(due_list)
            if not cards:
                print(f"{target} 无交租房间，跳过")
                continue

            now = datetime.now(TZ).strftime("%H:%M")
            title = f"🏠 收租提醒 | {total_due}间需交租 · {now}"

            today_str = datetime.now(TZ).strftime("%Y-%m-%d")
            html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 需交租提醒 · {today_str}</h2>'
            html += "".join(cards)
            html += f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total_due} 间需交租</div>'
            html += f"<!-- {random.randint(10000, 99999)} -->"

            send_pushplus(token, title, html)
            print(f"已推送 {target}: {title}")

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
