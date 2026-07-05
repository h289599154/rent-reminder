#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收租提醒脚本 V6 - 多公寓分路推送
- 房东: 悦居 + 彩虹
- 朋友B: 悦居
- 朋友C: 乐乐 + 骆家相寓2栋 + 狮大
"""

import os, sys, json, logging, re, base64
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# ========== 时区 ==========
BEIJING_OFFSET = timedelta(hours=8)
def beijing_now():
    return datetime.utcnow() + BEIJING_OFFSET

# ========== API配置 ==========
CLIENT_ID = os.environ.get('TENCENT_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('TENCENT_ACCESS_TOKEN', '')
OPEN_ID = os.environ.get('TENCENT_OPEN_ID', '')
PUSHPLUS_API = 'http://www.pushplus.plus/send'

# ========== Push 配置 ==========
PUSH_OWNER = os.environ.get('PUSHPLUS_TOKEN', '')
PUSH_FRIEND_B = os.environ.get('FRIEND_B_TOKEN', '')
PUSH_FRIEND_C = os.environ.get('FRIEND_C_TOKEN', '')

TOKEN_EXPIRE_WARN_DAYS = 7

# ========== 文档配置 ==========
DOCUMENTS = {
    'yueju': {
        'book_id': '300000000$NGUIfHYzcqNf', 'sheet_id': 'aopwxm',
        'name': '悦居', 'range': 'A1:H80',
        'skip_rows': [11, 22, 33, 44, 55, 66],
        'push_to': ['owner', 'friend_b'],
        'colors': {'bg': '#FFF7F0', 'border': '#E8853D', 'title': '#C5601A', 'dash': '#F5D5C0'}
    },
    'caihong': {
        'book_id': '300000000$NowDLTtMyFxt', 'sheet_id': 'aopwxm',
        'name': '彩虹', 'range': 'A1:H50',
        'skip_rows': [15, 25, 35],
        'push_to': ['owner'],
        'colors': {'bg': '#F0F5FF', 'border': '#3D8BE8', 'title': '#1A5FC5', 'dash': '#C5D5F5'}
    },
    'shida': {
        'book_id': '300000000$NVGckzvbFein', 'sheet_id': 'BB08J2',
        'name': '狮大', 'range': 'A1:H150',
        'skip_rows': [],
        'push_to': ['friend_c'],
        'colors': {'bg': '#FFF5F0', 'border': '#E8963D', 'title': '#C5801A', 'dash': '#F5E0C0'}
    },
    'lele': {
        'book_id': '300000000$NEkgavzHZlWi', 'sheet_id': 'aopwxm',
        'name': '乐乐', 'range': 'A1:H200',
        'skip_rows': [],
        'push_to': ['friend_c'],
        'colors': {'bg': '#F5FFF0', 'border': '#6DE83D', 'title': '#3AC51A', 'dash': '#D5F5C0'}
    },
    'luojia2': {
        'book_id': '300000000$NaIOsoNOmmry', 'sheet_id': 'BB08J2',
        'name': '骆家相寓2栋', 'range': 'A1:H200',
        'skip_rows': [],
        'push_to': ['friend_c'],
        'colors': {'bg': '#FFF0F5', 'border': '#E83D8B', 'title': '#C51A6D', 'dash': '#F5C0D5'}
    },
}

# 推送token映射
TOKEN_MAP = {
    'owner': PUSH_OWNER,
    'friend_b': PUSH_FRIEND_B,
    'friend_c': PUSH_FRIEND_C,
}
TOKEN_NAMES = {'owner': '房东', 'friend_b': '朋友B', 'friend_c': '朋友C'}

# ========== 数据读取 ==========

def get_sheet_data(book_id, sheet_id, range_str):
    url = f'https://docs.qq.com/openapi/spreadsheet/v3/files/{book_id}/{sheet_id}/{range_str}'
    h = {'Access-Token': ACCESS_TOKEN, 'Client-Id': CLIENT_ID, 'Open-Id': OPEN_ID}
    try:
        resp = requests.get(url, headers=h, timeout=30)
        result = resp.json()
        grid = result.get('gridData', {})
        return grid.get('rows', [])
    except Exception as e:
        logger.error(f"✗ API失败: {e}")
        return []

def extract_cell(cell_data):
    if not cell_data: return ''
    cv = cell_data.get('cellValue', {})
    if not cv: return ''
    dt = cell_data.get('dataType', '')
    if dt == 'TIME':
        t = cv.get('time', {})
        y, m, d = t.get('year',''), t.get('month',''), t.get('day','')
        return f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}" if y and m and d else ''
    if dt == 'SELECT':
        s = cv.get('select', {})
        return ','.join(o.get('text','') for o in s.get('options',[]) if o.get('id') in s.get('value',[]))
    return str(cv.get('text', '') or cv.get('number', ''))

def parse_rooms(rows, skip_rows):
    rooms = []
    for i, row in enumerate(rows):
        if (i+1) in skip_rows: continue
        vals = row.get('values', [])
        if not vals or len(vals) < 8: continue
        cells = [extract_cell(vals[j]) for j in range(8)]
        r = {'room': cells[0], 'due_month': cells[1], 'rent_start': cells[2],
             'rent_end': cells[3], 'payment': cells[4], 'rent_day': cells[5],
             'paid_mark': cells[6], 'rent': cells[7]}
        if r['room'] and r['room'].strip(): rooms.append(r)
    return rooms

# ========== 筛选 ==========

def should_skip(room, row_num, skip_rows):
    if row_num in skip_rows: return True
    if not room['room'] or not room['room'].strip(): return True
    if room['room'].strip() in ['空房', '烧酒', '房号', '悦居账目表', '彩虹公寓2栋 水角村4栋8号']: return True
    pm = room['paid_mark'].strip()
    if pm in ['付', '无']: return True
    re_str = room.get('rent_end', '').strip()
    if not re_str or re_str in ['', '1899-12-30']:
        if pm != '欠': return True
    return False

def check_rent_status(room):
    today = beijing_now()
    today_day = today.day
    rent_end = room.get('rent_end', '')
    paid_mark = room.get('paid_mark', '').strip()

    if paid_mark == '欠':
        m = re.match(r'(\d{1,2})\.(\d{1,2})', room.get('rent_day', '').strip())
        if m:
            try:
                due = datetime(today.year, int(m.group(1)), int(m.group(2)))
                return {'status': 'overdue', 'days': max(0, (today - due).days)}
            except: pass
        return {'status': 'overdue', 'days': 0}

    if not rent_end or rent_end in ['', '1899-12-30']: return None
    try:
        end = datetime.strptime(rent_end.strip(), '%Y-%m-%d')
        if today_day > end.day:
            lm = 12 if today.month == 1 else today.month - 1
            ly = today.year - 1 if today.month == 1 else today.year
            try: return {'status': 'overdue', 'days': (today - datetime(ly, lm, end.day)).days}
            except: return {'status': 'overdue', 'days': today_day - end.day}
        elif today_day == end.day: return {'status': 'today', 'days': 0}
        return None
    except: return None

def check_lease_expiry(rent_end_str):
    if not rent_end_str or not rent_end_str.strip(): return None
    try:
        end = datetime.strptime(rent_end_str.strip(), '%Y-%m-%d')
        diff = (end - beijing_now()).days
        if diff < 0: return {'status': 'expired', 'days': abs(diff)}
        elif diff <= 7: return {'status': 'expiring', 'days': diff}
    except: pass
    return None

def filter_rooms(rooms, skip_rows):
    result = {'overdue': [], 'today': []}
    for i, room in enumerate(rooms):
        if should_skip(room, i+1, skip_rows): continue
        ls = check_lease_expiry(room['rent_end'])
        if ls: room['lease_status'] = ls
        st = check_rent_status(room)
        if st:
            room['status'] = st
            result['overdue' if st['status'] == 'overdue' else 'today'].append(room)
    return result

# ========== HTML生成 ==========

def gen_room_html(room, is_overdue):
    rent = room['rent'].strip() or '?'
    pay = room['payment'].strip() or '月付'
    rs = room['rent_start'] or ''; re_s = room['rent_end'] or ''
    lease = f"{rs}~{re_s}" if rs else '未知租期'
    if room.get('lease_status'):
        ls = room['lease_status']
        if ls['status'] == 'expired':
            lease += f' · <span style="color:#D4380D;font-weight:bold">租约已到期{ls["days"]}天</span>'
        elif ls['status'] == 'expiring':
            lease += f' · <span style="color:#E8853D;font-weight:bold">租约{ls["days"]}天后到期</span>'
    if is_overdue:
        d = room['status']['days']
        return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room["room"]}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{d}天</span><br><span style="font-size:11px;color:#999">{lease} · {pay}</span></div>'
    return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room["room"]}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{lease} · {pay}</span></div>'

def gen_building_html(doc, data):
    c = doc['colors']
    overdue_h = ''.join(gen_room_html(r, True) for r in data['overdue'])
    today_h = ''.join(gen_room_html(r, False) for r in data['today'])
    if not overdue_h and not today_h:
        content = '<div style="margin:0;color:#999">一切正常</div>'
    else:
        content = overdue_h
        if overdue_h and today_h:
            content += f'<div style="border-top:1px dashed {c["dash"]};margin:8px 0 6px 0"></div>'
        content += today_h
    return f'<h3 style="font-size:16px;margin:0 0 8px;padding-left:6px;border-left:3px solid {c["border"]};color:{c["title"]}">{doc["name"]}</h3><div style="background:{c["bg"]};border-radius:8px;padding:10px 13px">{content}</div>'

def gen_combined_html(doc_list, all_data):
    """生成合并HTML"""
    today_str = beijing_now().strftime('%Y-%m-%d')
    parts = []
    total = 0
    for key in doc_list:
        data = all_data.get(key, {'overdue':[], 'today':[]})
        parts.append(gen_building_html(DOCUMENTS[key], data))
        parts.append('<br>')
        total += len(data['overdue']) + len(data['today'])
    return f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>{"".join(parts)}<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">共 {total}间待处理</div>'

def gen_title(doc_list, all_data):
    """生成动态标题"""
    overdue = sum(len(all_data.get(k, {}).get('overdue', [])) for k in doc_list)
    today = sum(len(all_data.get(k, {}).get('today', [])) for k in doc_list)
    if overdue + today == 0:
        return '🏠 收租提醒 | 一切正常 · ' + beijing_now().strftime('%H:%M')
    p = []
    if overdue: p.append(f'逾期{overdue}间')
    if today: p.append(f'今日交租{today}间')
    return f'🏠 收租提醒 | {"·".join(p)} | {overdue+today}间待处理 · ' + beijing_now().strftime('%H:%M')

# ========== 推送 ==========

def send_pushplus(token, title, content):
    if not token: return False
    try:
        resp = requests.post(PUSHPLUS_API, headers={'Content-Type': 'application/json; charset=utf-8'},
                           json={'token': token, 'title': title, 'content': content, 'template': 'html'}, timeout=30)
        r = resp.json()
        if r.get('code') == 200:
            logger.info(f"✓ {title[:50]}...")
            return True
        logger.error(f"✗ PushPlus失败: {r}")
        return False
    except Exception as e:
        logger.error(f"✗ PushPlus异常: {e}")
        return False

# ========== 主函数 ==========

def main():
    logger.info("=" * 50)
    logger.info("收租提醒 V6 开始")
    logger.info("=" * 50)

    if not ACCESS_TOKEN: logger.error("缺少 TENCENT_ACCESS_TOKEN"); sys.exit(1)

    # Token过期检查
    try:
        payload = ACCESS_TOKEN.split('.')[1] + '=='
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        days_left = (datetime.fromtimestamp(decoded['exp']) - beijing_now()).days
        logger.info(f"Token剩余: {days_left}天")
    except: days_left = 30

    # 读取所有文档
    all_data = {}
    for key, doc in DOCUMENTS.items():
        logger.info(f"--- {doc['name']} ---")
        rows = get_sheet_data(doc['book_id'], doc['sheet_id'], doc['range'])
        rooms = parse_rooms(rows, doc['skip_rows'])
        filtered = filter_rooms(rooms, doc['skip_rows'])
        logger.info(f"  逾期{len(filtered['overdue'])}间 今日{len(filtered['today'])}间")
        for r in filtered['overdue']:
            logger.info(f"  ⚠️ {r['room']} 逾期{r['status']['days']}天")
        for r in filtered['today']:
            logger.info(f"  📅 {r['room']} 今日交租")
        all_data[key] = filtered

    # 按接收人分组推送
    # 房东: 悦居+彩虹
    # 朋友B: 悦居
    # 朋友C: 乐乐+骆家2栋+狮大
    push_groups = {
        'owner': ['yueju', 'caihong'],
        'friend_b': ['yueju'],
        'friend_c': ['lele', 'luojia2', 'shida'],
    }

    for target, doc_keys in push_groups.items():
        token = TOKEN_MAP.get(target)
        if not token:
            logger.warning(f"⚠️ 未配置{target}的token")
            continue

        # 筛选有数据的文档
        active_docs = [k for k in doc_keys if len(all_data.get(k, {}).get('overdue', [])) + len(all_data.get(k, {}).get('today', [])) > 0]

        logger.info(f">>> 推送 {TOKEN_NAMES[target]} ({len(active_docs)}个公寓)")

        if not active_docs:
            logger.info(f"  {TOKEN_NAMES[target]} 无待处理房间，跳过")
            continue

        html = gen_combined_html(active_docs, all_data)
        title = gen_title(active_docs, all_data)
        send_pushplus(token, title, html)

    # Token到期提醒
    if days_left <= TOKEN_EXPIRE_WARN_DAYS and PUSH_OWNER:
        t = f'⚠️ Token将在{days_left}天后过期'
        c = f'<div style="color:#D4380D;font-size:15px;font-weight:bold">请及时续期Token</div><p>剩余{days_left}天</p><p>打开 https://docs.qq.com/open/developers/ 点"重置"获取新token</p>'
        send_pushplus(PUSH_OWNER, t, c)

    logger.info("=" * 50)
    logger.info("收租提醒 V6 完成")
    logger.info("=" * 50)

if __name__ == '__main__':
    main()
