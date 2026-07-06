#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests, traceback
from datetime import datetime, timezone, timedelta

# 强制输出错误信息，防止静默退出
def force_log(msg):
    print(msg, flush=True)

try:
    force_log("脚本开始运行...")

    CLIENT_ID = os.environ["TENCENT_CLIENT_ID"]
    ACCESS_TOKEN = os.environ["TENCENT_ACCESS_TOKEN"]
    OPEN_ID = os.environ["TENCENT_OPEN_ID"]
    PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
    FRIEND_B_TOKEN = os.environ["FRIEND_B_TOKEN"]
    FRIEND_C_TOKEN = os.environ["FRIEND_C_TOKEN"]

    force_log("环境变量读取成功")

    DOCUMENTS = {
        "悦居": {
            "book_id": "300000000$NGUIfHYzcqNf",
            "sheet_id": "aopwxm",
            "range": "A1:H80",
            "skip_rows": [11, 22, 33, 44, 55, 66],
            "push_to": ["owner", "friend_b"],
            "color": {"bg": "#FFF7F0", "border": "#E8853D", "title": "#C5601A"}
        },
        "彩虹": {
            "book_id": "300000000$NowDLTtMyFxt",
            "sheet_id": "aopwxm",
            "range": "A1:H50",
            "skip_rows": [15, 25, 35],
            "push_to": ["owner"],
            "color": {"bg": "#F0F5FF", "border": "#3D8BE8", "title": "#1A5FC5"}
        },
        "乐乐": {
            "book_id": "300000000$NEkgavzHZlWi",
            "sheet_id": "aopwxm",
            "range": "A1:H200",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "color": {"bg": "#F5FFF0", "border": "#6DE83D", "title": "#3AC51A"}
        },
        "狮大": {
            "book_id": "300000000$NVGckzvbFein",
            "sheet_id": "BB08J2",
            "range": "A1:H150",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "color": {"bg": "#FFF5F0", "border": "#E8963D", "title": "#C5801A"}
        },
        "骆家": {
            "book_id": "300000000$NaIOsoNOmmry",
            "sheet_id": "BB08J2",
            "range": "A1:H200",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "color": {"bg": "#FFF0F5", "border": "#E83D8B", "title": "#C51A6D"}
        },
    }

    TZ = timezone(timedelta(hours=8))

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
        h = {"Access-Token": ACCESS_TOKEN, "Client-Id": CLIENT_ID, "Open-Id": OPEN_ID}
        resp = requests.get(url, headers=h, timeout=30)
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
                    y, m, d = t.get("year",""), t.get("month",""), t.get("day","")
                    cells.append(f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}" if y and m and d else "")
                else:
                    cells.append(str(cv.get("text", "") or cv.get("number", "")))
            result.append(cells)
        return result

    def check_sheet(name, cfg):
        rows = get_sheet_data(cfg["book_id"], cfg["sheet_id"], cfg["range"])
        today = get_today_day()
        overdue, due = [], []
        skip = set(cfg["skip_rows"])
        for i, row in enumerate(rows):
            rn = i + 1
            if rn in skip: continue
            if len(row) < 7: continue
            room = str(row[0]).strip() if row[0] else ""
            if not room: continue
            status = str(row[6]).strip() if len(row) > 6 else ""
            move = str(row[3]).strip() if len(row) > 3 else ""
            if status == "欠":
                overdue.append({"room": room, "rent": str(row[7]).strip() if len(row) > 7 else "", "payment": str(row[4]).strip() if len(row) > 4 else "", "days": 0})
                continue
            if status in ("付", "无"): continue
            d = parse_day(move)
            if d is not None:
                if d < today:
                    overdue.append({"room": room, "rent": str(row[7]).strip() if len(row) > 7 else "", "payment": str(row[4]).strip() if len(row) > 4 else "", "days": today - d})
                elif d == today:
                    due.append({"room": room, "rent": str(row[7]).strip() if len(row) > 7 else "", "payment": str(row[4]).strip() if len(row) > 4 else ""})
        return overdue, due

    def check_token():
        try:
            p = ACCESS_TOKEN.split(".")[1]
            p += "=" * (4 - len(p) % 4)
            d = json.loads(base64.urlsafe_b64decode(p))
            exp = d.get("exp", 0)
            return (exp - datetime.now(TZ).timestamp()) / 86400 <= 7
        except: return False

    def gen_room_html(room, is_overdue, days=0):
        rent = room.get('rent', '') or '?'
        payment = room.get('payment', '') or '月付'
        name = room['room']
        if is_overdue:
            return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#D4380D">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{days}天</span><br><span style="font-size:11px;color:#999">{payment}</span></div>'
        else:
            return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#333">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{payment}</span></div>'

    def gen_doc_html(doc_name, color, overdue_list, today_list):
        if not overdue_list and not today_list:
            return ""
        c = color
        parts = []
        for r in overdue_list:
            parts.append(gen_room_html(r, True, r.get('days', 0)))
        if overdue_list and today_list:
            parts.append(f'<div style="border-top:1px dashed {c["border"]};margin:8px 0"></div>')
        for r in today_list:
            parts.append(gen_room_html(r, False))
        return f'<div style="margin-bottom:12px"><h3 style="font-size:16px;margin:0 0 8px;padding-left:6px;border-left:3px solid {c["border"]};color:{c["title"]}">{doc_name}</h3><div style="background:{c["bg"]};border-radius:8px;padding:10px 13px">{"".join(parts)}</div></div>'

    def gen_combined_html(doc_keys, all_data):
        today_str = datetime.now(TZ).strftime('%Y-%m-%d')
        blocks = []
        total = 0
        for key in doc_keys:
            doc_info = DOCUMENTS.get(key)
            if not doc_info: continue
            overdue, today = all_data.get(key, ([], []))
            if overdue or today:
                html = gen_doc_html(doc_info["name"], doc_info["color"], overdue, today)
                if html:
                    blocks.append(html)
                    total += len(overdue) + len(today)
        if not blocks:
            return "今日无待处理房间 ✅"
        header = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>'
        footer = f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total} 间待处理</div>'
        return header + ''.join(blocks) + footer

    def gen_title(doc_keys, all_data):
        overdue = sum(len(all_data.get(k, ([], []))[0]) for k in doc_keys)
        today = sum(len(all_data.get(k, ([], []))[1]) for k in doc_keys)
        if overdue + today == 0:
            return '🏠 收租提醒 | 一切正常 · ' + datetime.now(TZ).strftime('%H:%M')
        p = []
        if overdue: p.append(f'逾期{overdue}间')
        if today: p.append(f'今日交租{today}间')
        return f'🏠 收租提醒 | {"·".join(p)} | {overdue+today}间待处理 · ' + datetime.now(TZ).strftime('%H:%M')

    def push(title, content, token):
        requests.post("http://www.pushplus.plus/send", json={
            "token": token, "title": title, "content": content, "template": "html"
        }, timeout=10)

    force_log("开始读取文档...")

    all_data = {}
    for key, doc in DOCUMENTS.items():
        o, t = check_sheet(key, doc)
        all_data[key] = (o, t)
        force_log(f"{key}: 逾期{len(o)} 今日{len(t)}")

    push_groups = {
        "owner": ["悦居", "彩虹"],
        "friend_b": ["悦居"],
        "friend_c": ["乐乐", "狮大", "骆家"],
    }
    token_map = {
        "owner": PUSHPLUS_TOKEN,
        "friend_b": FRIEND_B_TOKEN,
        "friend_c": FRIEND_C_TOKEN,
    }

    for target, keys in push_groups.items():
        token = token_map.get(target)
        if not token: continue
        active = [k for k in keys if all_data.get(k, ([], []))[0] or all_data.get(k, ([], []))[1]]
        if not active: continue
        title = gen_title(active, all_data)
        html = gen_combined_html(active, all_data)
        push(title, html, token)
        force_log(f"推送 {target}: {title}")

    if check_token():
        push("⚠️ Token即将过期", '<div style="color:#D4380D;font-size:15px;font-weight:bold">请及时续期Token</div><p>打开 https://docs.qq.com/open/developers/ 点"重置"获取新token</p >', PUSHPLUS_TOKEN)

    force_log("脚本正常结束")
    sys.exit(0)

except Exception as e:
    err_info = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    force_log(err_info)
    # 推送错误信息
    try:
        requests.post("http://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": "收租提醒异常",
            "content": f"❌ {err_info}",
            "template": "txt"
        }, timeout=10)
    except: pass
    sys.exit(1)
