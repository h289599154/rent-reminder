#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests, traceback, random, unicodedata
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
        "range": "A1:L80",
        "skip_rows": [11, 22, 33, 44, 55, 66],
        "push_to": ["owner", "friend_b"],
        "color": {"bg": "#FFF7F0", "border": "#E8853D", "title": "#C5601A"}
    },
    {
        "name": "彩虹",
        "book_id": "300000000$NowDLTtMyFxt",
        "sheet_id": "aopwxm",
        "range": "A1:L50",
        "skip_rows": [15, 25, 35],
        "push_to": ["owner"],
        "color": {"bg": "#F0F5FF", "border": "#3D8BE8", "title": "#1A5FC5"}
    },
    {
        "name": "乐乐",
        "book_id": "300000000$NEkgavzHZlWi",
        "sheet_id": "aopwxm",
        "range": "A1:L200",
        "skip_rows": [16, 27, 38, 49],
        "push_to": ["friend_c"],
        "color": {"bg": "#F5FFF0", "border": "#6DE83D", "title": "#3AC51A"}
    },
    {
        "name": "狮大",
        "book_id": "300000000$NVGckzvbFein",
        "sheet_id": "BB08J2",
        "range": "A1:L150",
        "skip_rows": [11, 18, 25, 32, 39],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF5F0", "border": "#E8963D", "title": "#C5801A"}
    },
    {
        "name": "骆家2栋",
        "book_id": "300000000$NaIOsoNOmmry",
        "sheet_id": "BB08J2",
        "range": "A1:L200",
        "skip_rows": [12, 19, 26],
        "push_to": ["friend_c"],
        "color": {"bg": "#FFF0F5", "border": "#E83D8B", "title": "#C51A6D"}
    }
]

TOKEN_MAP = {
    "owner": PUSHPLUS_TOKEN,
    "friend_b": FRIEND_B_TOKEN,
    "friend_c": FRIEND_C_TOKEN
}

TOKEN_NAMES = {"owner": "房东", "friend_b": "朋友B", "friend_c": "朋友C", "all": "全部公寓"}

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

def check_sheet(doc):
    rows = get_sheet_data(doc["book_id"], doc["sheet_id"], doc["range"])
    today = get_today_day()
    today_due = []
    skip = set(doc["skip_rows"])
    for i, row in enumerate(rows):
        rn = i + 1
        if rn in skip: continue
        if len(row) < 12: continue
        room = str(row[0]).strip() if row[0] else ""
        if not room: continue

        raw_status = str(row[6]) if len(row) > 6 else ""
        status = clean_text(raw_status)
        move = str(row[3]).strip() if len(row) > 3 else ""
        d = parse_day(move)

        rent_str = str(row[7]).strip() if len(row) > 7 else "0"
        water_str = str(row[9]).strip() if len(row) > 9 else "0"
        net_str = str(row[11]).strip() if len(row) > 11 else "0"
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
            "payment": str(row[4]).strip() if len(row) > 4 else "月付",
            "due_day": str(row[5]).strip() if len(row) > 5 else "",
            "rent_start": str(row[2]).strip() if len(row) > 2 else "",
            "rent_end": move,
            "lease_remain": str(row[1]).strip() if len(row) > 1 else "",
            "status": status
        }

        if status == "付":
            continue
        if status == "欠":
            today_due.append(info)
            continue
        if status == "退":
            if d is not None and d <= today:
                today_due.append(info)
            continue
        if d is not None and d <= today:
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
    name = room["room"]
    rent = room.get("rent", "0")
    water = room.get("water", "0")
    net = room.get("net", "0")
    total = room.get("total", "0")
    pay = room.get("payment", "月付")
    start = room.get("rent_start", "")
    end = room.get("rent_end", "")
    due_day = room.get("due_day", "")
    lease_remain = room.get("lease_remain", "")
    st = room.get("status", "")

    if st == "欠":
        tag = '<span style="color:#D4380D;font-weight:bold">【欠租】</span>'
    elif st == "退":
        tag = '<span style="color:#E8963D;font-weight:bold">【退租】</span>'
    else:
        tag = ""

    lease = f"{start} ~ {end}" if start and end else "未知租期"
    pay_info = pay
    if due_day:
        pay_info += f" · 交租日{due_day}"
    remain_info = f" · 租期剩余{lease_remain}天" if lease_remain else ""

    # 第一行：房间号 + 标签 + 租金 + 水费/网杂费 + 共支付（红色加粗）
    line1 = f'<b style="font-size:14px;color:#333">{name}</b> {tag}<span style="font-size:13px;color:#333"> ¥{rent}/月</span> <span style="font-size:11px;color:#666">水费{water} 网杂费{net}</span> <span style="font-size:13px;color:#D4380D;font-weight:bold">共支付：¥{total}</span>'
    # 第二行：租期 · 支付方式 · 交租日 · 租期剩余
    line2 = f'<span style="font-size:11px;color:#999">{lease} · {pay_info}{remain_info}</span>'

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

def get_target():
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if event_path:
        try:
            with open(event_path, "r") as f:
                event = json.load(f)
            return event.get("inputs", {}).get("target", "owner")
        except:
            pass
    return "owner"

def main():
    try:
        target = get_target()
        print(f"目标推送对象: {target} ({TOKEN_NAMES.get(target, '未知')})")

        all_data = {}
        for doc in DOCS:
            due_list = check_sheet(doc)
            all_data[doc["name"]] = due_list
            print(f"{doc['name']}: 需处理{len(due_list)}间")

        if target == "all":
            token = PUSHPLUS_TOKEN
            doc_filter = None
        else:
            token = TOKEN_MAP.get(target)
            doc_filter = target
            if not token:
                print(f"未找到 {target} 的 token")
                sys.exit(1)

        cards = []
        total_due = 0
        for doc in DOCS:
            if doc_filter is not None and doc_filter not in doc["push_to"]:
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
            owe_count = sum(1 for doc in DOCS if (doc_filter is None or doc_filter in doc["push_to"]) for r in all_data.get(doc["name"], []) if r.get("status") == "欠")
            quit_count = sum(1 for doc in DOCS if (doc_filter is None or doc_filter in doc["push_to"]) for r in all_data.get(doc["name"], []) if r.get("status") == "退")
            normal_count = total_due - owe_count - quit_count

            title_parts = []
            if owe_count: title_parts.append(f"欠租{owe_count}间")
            if quit_count: title_parts.append(f"退租{quit_count}间")
            if normal_count: title_parts.append(f"交租{normal_count}间")
            title = f"🏠 收租提醒 | {'·'.join(title_parts)} | {total_due}间待处理 · {now}"

            html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租/退租提醒 · {today_str}</h2>'
            html += "".join(cards)
            html += f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total_due} 间待处理</div>'
            html += f"<!-- {rand} -->"
            send_pushplus(token, title, html)
            print(f"已推送 {target}: {title}")
        else:
            title = f"🏠 收租提醒 | 今日无待处理 · {now}"
            html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 今日无待处理 · {today_str}</h2><p>所有房间已付清或无到期/退租。</p><!-- {rand} -->'
            send_pushplus(token, title, html)
            print(f"已推送 {target}: 今日无待处理")

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
