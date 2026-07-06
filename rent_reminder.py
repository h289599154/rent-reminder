#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests, traceback
from datetime import datetime, timezone, timedelta

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

    # 文档配置，每个文档都有完整的 name、color 等字段
    DOCUMENTS = {
        "悦居": {
            "name": "悦居",
            "book_id": "300000000$NGUIfHYzcqNf",
            "sheet_id": "aopwxm",
            "range": "A1:H80",
            "skip_rows": [11, 22, 33, 44, 55, 66],
            "push_to": ["owner", "friend_b"],
            "bg": "#FFF7F0",
            "border": "#E8853D",
            "title_color": "#C5601A"
        },
        "彩虹": {
            "name": "彩虹",
            "book_id": "300000000$NowDLTtMyFxt",
            "sheet_id": "aopwxm",
            "range": "A1:H50",
            "skip_rows": [15, 25, 35],
            "push_to": ["owner"],
            "bg": "#F0F5FF",
            "border": "#3D8BE8",
            "title_color": "#1A5FC5"
        },
        "乐乐": {
            "name": "乐乐",
            "book_id": "300000000$NEkgavzHZlWi",
            "sheet_id": "aopwxm",
            "range": "A1:H200",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "bg": "#F5FFF0",
            "border": "#6DE83D",
            "title_color": "#3AC51A"
        },
        "狮大": {
            "name": "狮大",
            "book_id": "300000000$NVGckzvbFein",
            "sheet_id": "BB08J2",
            "range": "A1:H150",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "bg": "#FFF5F0",
            "border": "#E8963D",
            "title_color": "#C5801A"
        },
        "骆家": {
            "name": "骆家",
            "book_id": "300000000$NaIOsoNOmmry",
            "sheet_id": "BB08J2",
            "range": "A1:H200",
            "skip_rows": [],
            "push_to": ["friend_c"],
            "bg": "#FFF0F5",
            "border": "#E83D8B",
            "title_color": "#C51A6D"
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

    def check_sheet(cfg):
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

    # 生成单个房间的 HTML
    def room_html(r, is_overdue):
        name = r['room']
        rent = r.get('rent', '') or '?'
        pay = r.get('payment', '') or '月付'
        if is_overdue:
            days = r.get('days', 0)
            return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#D4380D">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{days}天</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'
        else:
            return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px;color:#333">{name}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'

    # 生成某个文档的卡片 HTML
    def doc_card(doc_key, doc_cfg, overdue, today):
        if not overdue and not today:
            return ""
        parts = []
        for r in overdue:
            parts.append(room_html(r, True))
        if overdue and today:
            parts.append(f'<div style="border-top:1px dashed {doc_cfg["border"]};margin:8px 0"></div>')
        for r in today:
            parts.append(room_html(r, False))
        return f'''
        <div style="margin-bottom:12px">
            <h3 style="font-size:16px;margin:0 0 8px;padding-left:6px;border-left:3px solid {doc_cfg['border']};color:{doc_cfg['title_color']}">{doc_cfg['name']}</h3>
            <div style="background:{doc_cfg['bg']};border-radius:8px;padding:10px 13px">{"".join(parts)}</div>
        </div>
        '''

    def push(title, content, token):
        requests.post("http://www.pushplus.plus/send", json={
            "token": token, "title": title, "content": content, "template": "html"
        }, timeout=10)

    force_log("开始读取文档...")
    all_data = {}
    for key, cfg in DOCUMENTS.items():
        o, t = check_sheet(cfg)
        all_data[key] = (o, t)
        force_log(f"{cfg['name']}: 逾期{len(o)} 今日{len(t)}")

    # 推送分组
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

    for target, doc_keys in push_groups.items():
        token = token_map.get(target)
        if not token:
            continue
        # 收集本组有数据的文档
        blocks = []
        total_overdue = 0
        total_today = 0
        for key in doc_keys:
            if key not in DOCUMENTS:
                force_log(f"警告：未知文档键 {key}")
                continue
            cfg = DOCUMENTS[key]
            overdue, today = all_data.get(key, ([], []))
            if overdue or today:
                card = doc_card(key, cfg, overdue, today)
                if card:
                    blocks.append(card)
                    total_overdue += len(overdue)
                    total_today += len(today)
        if not blocks:
            force_log(f"{target} 无待处理房间，跳过")
            continue

        now = datetime.now(TZ).strftime('%H:%M')
        title = f"🏠 收租提醒 | "
        if total_overdue:
            title += f"逾期{total_overdue}间"
        if total_overdue and total_today:
            title += "·"
        if total_today:
            title += f"今日交租{total_today}间"
        title += f" | {total_overdue+total_today}间待处理 · {now}"

        today_str = datetime.now(TZ).strftime('%Y-%m-%d')
        html = f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>'
        html += ''.join(blocks)
        html += f'<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total_overdue+total_today} 间待处理</div>'

        push(title, html, token)
        force_log(f"推送 {target}: {title}")

    if check_token():
        push("⚠️ Token即将过期", '<div style="color:#D4380D;font-size:15px;font-weight:bold">请及时续期Token</div><p>打开 https://docs.qq.com/open/developers/ 点"重置"获取新token</p >', PUSHPLUS_TOKEN)

    force_log("脚本正常结束")
    sys.exit(0)

except Exception as e:
    err_info = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    force_log(err_info)
    try:
        requests.post("http://www.pushplus.plus/send", json={
            "token": PUSHPLUS_TOKEN,
            "title": "收租提醒异常",
            "content": f"❌ {err_info}",
            "template": "txt"
        }, timeout=10)
    except: pass
    sys.exit(1)
