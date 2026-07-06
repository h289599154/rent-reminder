#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, base64, requests
from datetime import datetime, timezone, timedelta

CLIENT_ID = os.environ["TENCENT_CLIENT_ID"]
ACCESS_TOKEN = os.environ["TENCENT_ACCESS_TOKEN"]
OPEN_ID = os.environ["TENCENT_OPEN_ID"]
PUSHPLUS_TOKEN = os.environ["PUSHPLUS_TOKEN"]
FRIEND_B_TOKEN = os.environ["FRIEND_B_TOKEN"]
FRIEND_C_TOKEN = os.environ["FRIEND_C_TOKEN"]

SHEETS = {
    "悦居": {"book_id":"300000000$NGUIfHYzcqNf","sheet_id":"aopwxm","range":"A1:H80","skip_rows":[11,22,33,44,55,66]},
    "彩虹": {"book_id":"300000000$NowDLTtMyFxt","sheet_id":"aopwxm","range":"A1:H50","skip_rows":[15,25,35]},
    # 修正后的 book_id（直接使用链接中的编码）
    "乐乐": {"book_id":"DTkVrZ2F2ekhabFdp","sheet_id":"aopwxm","range":"A1:H200","skip_rows":[]},
    "狮大": {"book_id":"DTlZHY2t6dmJGZWlu","sheet_id":"aopwxm","range":"A1:H150","skip_rows":[]},
    "骆家": {"book_id":"DTmFJT3NvTk9tbXJ5","sheet_id":"aopwxm","range":"A1:H200","skip_rows":[]},
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

def get_data(book, sheet, rng):
    url = f"https://docs.qq.com/openapi/v2/spreadsheets/{book}/values/{sheet}"
    h = {"Authorization":f"Bearer {ACCESS_TOKEN}","Client-Id":CLIENT_ID,"Open-Id":OPEN_ID}
    r = requests.get(url, headers=h, params={"range":rng}, timeout=15)
    if r.status_code!=200: raise Exception(f"API {r.status_code}: {r.text}")
    return r.json().get("values",[])

def check_sheet(name,cfg):
    rows = get_data(cfg["book_id"],cfg["sheet_id"],cfg["range"])
    today = get_today_day()
    overdue, due = [], []
    skip = set(cfg["skip_rows"])
    for i,row in enumerate(rows):
        rn = i+1
        if rn in skip: continue
        if len(row)<7: continue
        room = str(row[0]).strip() if row[0] else ""
        if not room: continue
        status = str(row[6]).strip() if len(row)>6 else ""
        move = str(row[3]).strip() if len(row)>3 else ""
        if status=="欠":
            overdue.append(room); continue
        if status in ("付","无"): continue
        d = parse_day(move)
        if d is not None:
            if d<today: overdue.append(room)
            elif d==today: due.append(room)
    return overdue,due

def check_token():
    try:
        p = ACCESS_TOKEN.split(".")[1]
        p += "="*(4-len(p)%4)
        d = json.loads(base64.urlsafe_b64decode(p))
        exp = d.get("exp",0)
        return (exp-datetime.now(TZ).timestamp())/86400 <= 7
    except: return False

def push(title, content, token):
    requests.post("http://www.pushplus.plus/send", json={
        "token":token,"title":title,"content":content,"template":"html"
    }, timeout=10)

def main():
    try:
        # 自己（悦居+彩虹）
        all_over, all_today = [], []
        for name in ["悦居","彩虹"]:
            o,t = check_sheet(name, SHEETS[name])
            all_over.extend(o); all_today.extend(t)
        # 朋友B（悦居）
        y_over, y_today = check_sheet("悦居", SHEETS["悦居"])
        # 朋友C（乐乐+狮大+骆家）
        new_over, new_today = [], []
        for name in ["乐乐","狮大","骆家"]:
            o,t = check_sheet(name, SHEETS[name])
            new_over.extend(o); new_today.extend(t)

        now = datetime.now(TZ).strftime("%H:%M")

        # 推自己
        total = len(all_over)+len(all_today)
        title = f"🏠 收租提醒 | 逾期{len(all_over)}间·今日交租{len(all_today)}间 | {total}间待处理 · {now}"
        lines=[]
        if all_over: lines.append(f"❗ 逾期({len(all_over)}间): {'、'.join(all_over)}")
        if all_today: lines.append(f"🔔 今日交租({len(all_today)}间): {'、'.join(all_today)}")
        if check_token(): lines.append("\n⚠️ access_token 即将过期，请续期！")
        content = "\n\n".join(lines) if lines else "今日无待处理房间 ✅"
        push(title, content, PUSHPLUS_TOKEN)

        # 推朋友B
        if y_over or y_today:
            ft = f"🏠 悦居收租提醒 | 逾期{len(y_over)}间·今日交租{len(y_today)}间 · {now}"
            fl=[]
            if y_over: fl.append(f"❗ 逾期({len(y_over)}间): {'、'.join(y_over)}")
            if y_today: fl.append(f"🔔 今日交租({len(y_today)}间): {'、'.join(y_today)}")
            push(ft, "\n\n".join(fl), FRIEND_B_TOKEN)

        # 推朋友C
        if new_over or new_today:
            nt = f"🏠 收租提醒 | 逾期{len(new_over)}间·今日交租{len(new_today)}间 · {now}"
            nl=[]
            if new_over: nl.append(f"❗ 逾期({len(new_over)}间): {'、'.join(new_over)}")
            if new_today: nl.append(f"🔔 今日交租({len(new_today)}间): {'、'.join(new_today)}")
            push(nt, "\n\n".join(nl), FRIEND_C_TOKEN)

        sys.exit(0)
    except Exception as e:
        push("收租提醒异常", f"❌ {e}", PUSHPLUS_TOKEN)
        sys.exit(1)

if __name__=="__main__":
    main()
