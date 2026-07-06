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
    rows = get_sheet_data(doc["book_id"], doc["sheet_id"], doc["range"])
    today = get_today_day()
    overdue, due = [], []
    skip = set(doc["skip_rows"])
    for i, row in enumerate(rows):
        rn = i + 1
        if rn in skip: continue
        if len(row) < 7: continue
        room = str(row[0]).strip() if row[0] else ""
        if not room: continue
        raw_status = str(row[6]).strip() if len(row) > 6 else ""
        move = str(row[3]).strip() if len(row) > 3 else ""
        info = {
            "room": room,
            "rent": str(row[7]).strip() if len(row) > 7 else "",
            "payment": str(row[4]).strip() if len(row) > 4 else ""
        }

        # ---------- 多选控件处理 ----------
        # 按逗号拆分，分别判断每个选项
        has_owe = False
        has_paid = False
        if raw_status:
            for opt in raw_status.split(","):
                opt = opt.strip()
                if "欠" in opt:
                    has_owe = True
                if "付" in opt or "无" in opt:
                    has_paid = True

        # 只要包含“欠”且没有“付/无”，就强制逾期
        if has_owe and not has_paid:
            overdue.append(info)
            continue

        # 包含“付”或“无”就跳过
        if has_paid:
            continue
        # ---------------------------------

        # 退租日逻辑（与昨晚版本一致）
        d = parse_day(move)
        if d is not None:
            if d < today:
                info["days"] = today - d
                overdue.append(info)
            elif d == today:
                due.append(info)
    return overdue, due

def check_token_expiry():
    try:
        p = ACCESS_TOKEN.split(".")[1]
        p += "=" * (4 - len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        exp = d.get("exp", 0)
        return (exp - datetime.now(TZ).timestamp()) / 86400 <= 7
    except: return False

def room_html(room, is_overdue, days=0):
    rent = room.get("rent", "") or "?"
    pay = room.get("payment", "") or "月付"
    name = room["room"]
    if is_overdue:
        return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#D4380D">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{days}天</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'
    else:
        return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#333">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'

def doc_card(doc, overdue, today):
    if not overdue and not today: return ""
    parts = []
    for r in overdue:
        parts.append(room_html(r, True, r.get("days", 0)))
    if overdue and today:
        parts.append(f'<div style="border-top:1px dashed {doc["color"]["border"]};margin:8px 0"></div>')
    for r in today:
        parts.append(room_html(r, False))
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
            overdue, today = check_sheet(doc)
            all_data[doc["name"]] = (overdue, today)
            print(f"{doc['name']}: 逾期{len(overdue)} 今日{len(today)}")

        for target, token in TOKEN_MAP.items():
            if not token: continue
            cards = []
            total_overdue = 0
            total_today = 0
            for doc in DOCS:
                if target not in doc["push_to"]: continue
                overdue, today = all_data.get(doc["name"], ([], []))
                if overdue or today:
                    card = doc_card(doc, overdue, today)
                    if card:
                        cards.append(card)
                        total_overdue += len(overdue)
                        total_today += len(today)
            if not cards:
                print(f"{target} 无待处理房间，跳过")
                continue

            now = datetime.now(TZ).strftime("%H:%M")
            title = f"🏠 收租提醒 | 逾期{total_overdue}间·今日交租{total_today}间 | {total_overdue+total_today}间待处理 · {now}"

            today_str = datetime.now(TZ).strftime("%Y-%m-%d")
            html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>'
            html += "".join(cards)
            html += f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total_overdue+total_today} 间待处理</div>'
            # 添加随机数避免重复拦截
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
