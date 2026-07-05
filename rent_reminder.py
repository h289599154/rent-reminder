#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收租提醒 V6 - 多公寓分路推送 (V2 API 修复版)
"""
import os, sys, json, logging, re, base64
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

BEIJING_OFFSET = timedelta(hours=8)
def beijing_now():
    return datetime.utcnow() + BEIJING_OFFSET

CLIENT_ID = os.environ.get('TENCENT_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('TENCENT_ACCESS_TOKEN', '')
OPEN_ID = os.environ.get('TENCENT_OPEN_ID', '')
PUSHPLUS_API = 'http://www.pushplus.plus/send'

PUSH_OWNER = os.environ.get('PUSHPLUS_TOKEN', '')
PUSH_FRIEND_B = os.environ.get('FRIEND_B_TOKEN', '')
PUSH_FRIEND_C = os.environ.get('FRIEND_C_TOKEN', '')

TOKEN_EXPIRE_WARN_DAYS = 7

DOCUMENTS = {
    'yueju': {'book_id': '300000000$NGUIfHYzcqNf','sheet_id':'aopwxm','name':'悦居','range':'A1:H80','skip_rows':[11,22,33,44,55,66],'push_to':['owner','friend_b']},
    'caihong': {'book_id': '300000000$NowDLTtMyFxt','sheet_id':'aopwxm','name':'彩虹','range':'A1:H50','skip_rows':[15,25,35],'push_to':['owner']},
    'shida': {'book_id': '300000000$NVGckzvbFein','sheet_id':'BB08J2','name':'狮大','range':'A1:H150','skip_rows':[],'push_to':['friend_c']},
    'lele': {'book_id': '300000000$NEkgavzHZlWi','sheet_id':'aopwxm','name':'乐乐','range':'A1:H200','skip_rows':[],'push_to':['friend_c']},
    'luojia2': {'book_id': '300000000$NaIOsoNOmmry','sheet_id':'BB08J2','name':'骆家相寓2栋','range':'A1:H200','skip_rows':[],'push_to':['friend_c']},
}

TOKEN_MAP = {'owner': PUSH_OWNER, 'friend_b': PUSH_FRIEND_B, 'friend_c': PUSH_FRIEND_C}
TOKEN_NAMES = {'owner': '房东', 'friend_b': '朋友B', 'friend_c': '朋友C'}

# ========== V2 API 数据读取 ==========
def get_sheet_data(book_id, sheet_id, range_str):
    url = f'https://docs.qq.com/openapi/v2/spreadsheets/{book_id}/values/{sheet_id}'
    h = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Client-Id': CLIENT_ID, 'Open-Id': OPEN_ID}
    try:
        resp = requests.get(url, headers=h, params={'range': range_str}, timeout=30)
        data = resp.json()
        return data.get('values', [])
    except Exception as e:
        logger.error(f"V2 API 失败: {e}")
        return []

def parse_rooms(rows, skip_rows):
    rooms = []
    for i, row in enumerate(rows):
        rn = i + 1
        if rn in skip_rows: continue
        if not row or len(row) < 7: continue
        room_name = str(row[0]).strip() if row[0] else ''
        if not room_name: continue
        r = {
            'room': room_name,
            'due_month': str(row[1]).strip() if len(row) > 1 else '',
            'rent_start': str(row[2]).strip() if len(row) > 2 else '',
            'rent_end': str(row[3]).strip() if len(row) > 3 else '',
            'payment': str(row[4]).strip() if len(row) > 4 else '',
            'rent_day': str(row[5]).strip() if len(row) > 5 else '',
            'paid_mark': str(row[6]).strip() if len(row) > 6 else '',
            'rent': str(row[7]).strip() if len(row) > 7 else ''
        }
        rooms.append(r)
    return rooms

# ========== 筛选逻辑 ==========
def should_skip(room, row_num, skip_rows):
    if row_num in skip_rows: return True
    if not room['room'] or not room['room'].strip(): return True
    pm = room['paid_mark'].strip()
    if pm in ['付', '无']: return True
    return False

def check_rent_status(room):
    today = beijing_now()
    today_day = today.day
    rent_end = room.get('rent_end', '').strip()
    paid_mark = room.get('paid_mark', '').strip()

    if paid_mark == '欠':
        return {'status': 'overdue', 'days': 0}

    if not rent_end or rent_end in ['', '1899-12-30']: return None
    try:
        if '-' in rent_end: d = int(rent_end.split('-')[2])
        elif '/' in rent_end: d = int(rent_end.split('/')[2])
        else: return None
        if today_day > d: return {'status': 'overdue', 'days': today_day - d}
        elif today_day == d: return {'status': 'today', 'days': 0}
        return None
    except: return None

def filter_rooms(rooms, skip_rows):
    result = {'overdue': [], 'today': []}
    for i, room in enumerate(rooms):
        if should_skip(room, i+1, skip_rows): continue
        st = check_rent_status(room)
        if st:
            room['status'] = st
            result['overdue' if st['status'] == 'overdue' else 'today'].append(room)
    return result

# ========== 推送生成与发送 ==========
def gen_room_html(room, is_overdue):
    rent = room['rent'].strip() or '?'
    pay = room['payment'].strip() or '月付'
    if is_overdue:
        d = room['status']['days']
        return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room["room"]}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{d}天</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'
    return f'<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room["room"]}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{pay}</span></div>'

def gen_doc_html(name, data):
    c = {'bg':'#FFF7F0','border':'#E8853D','title':'#C5601A','dash':'#F5D5C0'}
    overdue_h = ''.join(gen_room_html(r, True) for r in data['overdue'])
    today_h = ''.join(gen_room_html(r, False) for r in data['today'])
    if not overdue_h and not today_h: return ''
    content = overdue_h
    if overdue_h and today_h: content += f'<div style="border-top:1px dashed {c["dash"]};margin:8px 0"></div>'
    content += today_h
    return f'<h3 style="margin:0 0 6px;padding-left:6px;border-left:3px solid {c["border"]};color:{c["title"]}">{name}</h3><div style="background:{c["bg"]};border-radius:8px;padding:10px 13px">{content}</div>'

def gen_combined_html(doc_keys, all_data):
    parts = []
    for key in doc_keys:
        h = gen_doc_html(DOCUMENTS[key]['name'], all_data.get(key, {'overdue':[], 'today':[]}))
        if h: parts.append(h + '<br>')
    if not parts: return '今日无待处理房间 ✅'
    today_str = beijing_now().strftime('%Y-%m-%d')
    return f'<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>{"".join(parts)}'

def gen_title(doc_keys, all_data):
    overdue = sum(len(all_data.get(k, {}).get('overdue', [])) for k in doc_keys)
    today = sum(len(all_data.get(k, {}).get('today', [])) for k in doc_keys)
    if overdue + today == 0: return '🏠 收租提醒 | 一切正常 · ' + beijing_now().strftime('%H:%M')
    p = []
    if overdue: p.append(f'逾期{overdue}间')
    if today: p.append(f'今日交租{today}间')
    return f'🏠 收租提醒 | {"·".join(p)} | {overdue+today}间待处理 · ' + beijing_now().strftime('%H:%M')

def send_pushplus(token, title, content):
    if not token: return False
    try:
        resp = requests.post(PUSHPLUS_API, headers={'Content-Type':'application/json'}, json={'token':token,'title':title,'content':content,'template':'html'}, timeout=30)
        r = resp.json()
        if r.get('code') == 200: logger.info(f"推送成功: {title[:40]}"); return True
        logger.error(f"PushPlus失败: {r}"); return False
    except Exception as e: logger.error(f"PushPlus异常: {e}"); return False

# ========== 主函数 ==========
def main():
    logger.info("=" * 50)
    logger.info("收租提醒 V6 (V2 API) 开始")
    logger.info("=" * 50)

    if not ACCESS_TOKEN: logger.error("缺少 TENCENT_ACCESS_TOKEN"); sys.exit(1)

    try:
        payload = ACCESS_TOKEN.split('.')[1] + '=='
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        days_left = (datetime.fromtimestamp(decoded['exp']) - beijing_now()).days
        logger.info(f"Token剩余: {days_left}天")
    except: days_left = 30

    all_data = {}
    for key, doc in DOCUMENTS.items():
        logger.info(f"--- {doc['name']} ---")
        rows = get_sheet_data(doc['book_id'], doc['sheet_id'], doc['range'])
        rooms = parse_rooms(rows, doc['skip_rows'])
        filtered = filter_rooms(rooms, doc['skip_rows'])
        logger.info(f"  逾期{len(filtered['overdue'])}间 今日{len(filtered['today'])}间")
        for r in filtered['overdue']: logger.info(f"  ⚠️ {r['room']} 逾期{r['status']['days']}天")
        for r in filtered['today']: logger.info(f"  📅 {r['room']} 今日交租")
        all_data[key] = filtered

    push_groups = {'owner': ['yueju', 'caihong'], 'friend_b': ['yueju'], 'friend_c': ['lele', 'luojia2', 'shida']}

    for target, doc_keys in push_groups.items():
        token = TOKEN_MAP.get(target)
        if not token: logger.warning(f"未配置{target}的token"); continue
        active = [k for k in doc_keys if len(all_data.get(k, {}).get('overdue', [])) + len(all_data.get(k, {}).get('today', [])) > 0]
        logger.info(f">>> {TOKEN_NAMES[target]} ({len(active)}个公寓有数据)")
        if not active: logger.info(f"  无待处理房间，跳过"); continue
        html = gen_combined_html(active, all_data)
        title = gen_title(active, all_data)
        send_pushplus(token, title, html)

    if days_left <= TOKEN_EXPIRE_WARN_DAYS and PUSH_OWNER:
        send_pushplus(PUSH_OWNER, '⚠️ Token即将过期', f'<p>剩余{days_left}天，请去腾讯文档开放平台续期</p>')

    logger.info("=" * 50)
    logger.info("收租提醒完成")
    logger.info("=" * 50)

if __name__ == '__main__':
    main()
