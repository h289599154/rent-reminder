#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
房租到期提醒脚本 V3 - GitHub Actions 版
每天自动检查，推送逾期和今日交租的房间信息到微信

所有敏感配置通过环境变量读取，适配 GitHub Actions Secrets

数据解析说明：
- 日期类型(TIME)：cellValue.time  → {year, month, day}
- 数字类型(NUMBER)：cellValue.number
- 文本类型(TEXT)：cellValue.text
- 下拉选择(SELECT)：cellValue.select.value[0] → 对照options找到text
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timedelta
import requests
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== 腾讯文档API配置（从环境变量读取） ==========
CLIENT_ID = os.environ.get('TENCENT_CLIENT_ID', '')
ACCESS_TOKEN = os.environ.get('TENCENT_ACCESS_TOKEN', '')
OPEN_ID = os.environ.get('TENCENT_OPEN_ID', '')
CLIENT_SECRET = os.environ.get('TENCENT_CLIENT_SECRET', '')

# ========== 文档配置 ==========
DOCUMENTS = {
    'yueju': {
        'book_id': '300000000$NGUIfHYzcqNf',
        'sheet_id': 'aopwxm',
        'name': '悦居',
        'range': 'A1:H80',
        'skip_rows': [11, 22, 33, 44, 55, 66],
        'colors': {
            'bg': '#FFF7F0', 'border': '#E8853D', 'title': '#C5601A', 'dash': '#F5D5C0'
        }
    },
    'caihong': {
        'book_id': '300000000$NowDLTtMyFxt',
        'sheet_id': 'aopwxm',
        'name': '彩虹',
        'range': 'A1:H50',
        'skip_rows': [15, 25, 35],
        'colors': {
            'bg': '#F0F5FF', 'border': '#3D8BE8', 'title': '#1A5FC5', 'dash': '#C5D5F5'
        }
    }
}

# ========== PushPlus配置（从环境变量读取） ==========
PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN', '')
PUSHPLUS_API = 'http://www.pushplus.plus/send'


# ========== Token管理 ==========

def check_token_expiry():
    """检查token是否即将过期（通过JWT解析）"""
    try:
        import base64
        payload = ACCESS_TOKEN.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        exp_time = datetime.fromtimestamp(decoded['exp'])
        days_left = (exp_time - datetime.now()).days
        if days_left <= 5:
            logger.warning(f"⚠️ Token将在{days_left}天后过期，请尽快续期！")
            # 尝试自动续期
            if CLIENT_SECRET:
                try_refresh_token(days_left)
        else:
            logger.info(f"Token剩余有效期: {days_left}天")
        return days_left
    except Exception as e:
        logger.warning(f"解析Token过期时间失败: {e}")
        return 30


def try_refresh_token(days_left):
    """尝试使用client_secret刷新token（需要refresh_token）"""
    # GitHub Actions 环境无法持久化token，这里仅做检测和提醒
    # 实际续期需要用户手动获取refresh_token后配置
    logger.info(f"Token剩余{days_left}天，尝试续期...")
    logger.warning("⚠️ GitHub Actions环境无法自动续期Token，请手动更新Secrets中的TENCENT_ACCESS_TOKEN")


# ========== 数据读取与解析 ==========

def get_sheet_data(book_id, sheet_id, range_str):
    """通过腾讯文档API读取表格数据"""
    url = f'https://docs.qq.com/openapi/spreadsheet/v3/files/{book_id}/{sheet_id}/{range_str}'
    headers = {
        'Access-Token': ACCESS_TOKEN,
        'Client-Id': CLIENT_ID,
        'Open-Id': OPEN_ID
    }
    
    try:
        logger.info(f"调用API: {book_id[:20]}.../{sheet_id}/{range_str}")
        resp = requests.get(url, headers=headers, timeout=30)
        result = resp.json()
        
        grid_data = result.get('gridData') or result.get('data', {}).get('gridData', {})
        rows = grid_data.get('rows', [])
        
        logger.info(f"✓ 获取到 {len(rows)} 行数据")
        return rows
    except Exception as e:
        logger.error(f"✗ API调用失败: {e}")
        return []


def extract_cell_text(cell_data):
    """
    从API返回的单元格数据中提取文本值
    支持多种数据类型：TIME(日期), NUMBER(数字), TEXT(文本), SELECT(下拉选择)
    """
    if not cell_data:
        return ''
    
    cell_value = cell_data.get('cellValue')
    if not cell_value:
        return ''
    
    data_type = cell_data.get('dataType', '')
    
    # 1. 日期类型 (TIME)
    if data_type == 'TIME':
        time_obj = cell_value.get('time', {})
        year = time_obj.get('year', '')
        month = time_obj.get('month', '')
        day = time_obj.get('day', '')
        if year and month and day:
            return f"{year}-{month:02d}-{day:02d}" if isinstance(month, int) else f"{year}-{month}-{day}"
        return ''
    
    # 2. 下拉选择类型 (SELECT)
    if data_type == 'SELECT':
        select_obj = cell_value.get('select', {})
        selected_ids = select_obj.get('value', [])
        options = select_obj.get('options', [])
        texts = []
        for opt_id in selected_ids:
            for opt in options:
                if opt.get('id') == opt_id:
                    texts.append(opt.get('text', ''))
                    break
        return ','.join(texts) if texts else ''
    
    # 3. 文本类型
    text = cell_value.get('text', '')
    if text:
        return text
    
    # 4. 数字类型
    number = cell_value.get('number')
    if number is not None:
        if isinstance(number, float) and number == int(number):
            return str(int(number))
        return str(number)
    
    # 5. 日期时间类型（备选）
    date_time = cell_value.get('dateTime', '')
    if date_time:
        return str(date_time)
    
    return ''


def parse_rows_to_rooms(rows):
    """将API返回的行数据解析为房间列表"""
    rooms = []
    
    for row_data in rows:
        values = row_data.get('values', [])
        if not values or len(values) < 8:
            continue
        
        cells = [extract_cell_text(values[i]) for i in range(8)]
        
        room = {
            'room': cells[0],       # A房号
            'due_month': cells[1],  # B到期
            'rent_start': cells[2], # C起租
            'rent_end': cells[3],   # D退租
            'payment': cells[4],    # E支付方式/备注
            'rent_day': cells[5],   # F交租日
            'paid_mark': cells[6],  # G付标记
            'rent': cells[7],       # H租金
        }
        rooms.append(room)
    
    return rooms


# ========== 筛选逻辑 ==========

def should_skip(room, row_num, skip_rows):
    """判断是否应该跳过该房间"""
    if row_num in skip_rows:
        return True
    
    if not room['room'] or room['room'].strip() == '':
        return True
    
    if room['room'].strip() in ['空房', '烧酒', '房号', '悦居账目表', '彩虹公寓2栋 水角村4栋8号']:
        return True
    
    paid_mark = room['paid_mark'].strip()
    if paid_mark in ['付', '无']:
        return True
    
    rent_end = room.get('rent_end', '').strip()
    if not rent_end or rent_end in ['', '1899-12-30']:
        if paid_mark != '欠':
            return True
    
    return False


def check_rent_status(room):
    """
    按原始交租逻辑判断：
    条件1: G列 = "欠" → 强制提醒
    条件2: 退租日(D列)非空 AND 今天日数 >= 退租日日数 → 提醒
    
    逾期判断：退租日日数 < 今天日数（不看月份，只看日）
    今日交租：退租日日数 == 今天日数
    
    返回: None / {'status': 'overdue', 'days': N} / {'status': 'today', 'days': 0}
    """
    today = datetime.now()
    today_day = today.day
    
    rent_end = room.get('rent_end', '')
    paid_mark = room.get('paid_mark', '').strip()
    
    # 条件1: G列 = "欠" → 强制提醒（按逾期处理）
    if paid_mark == '欠':
        rent_day_str = room.get('rent_day', '').strip()
        match = re.match(r'(\d{1,2})\.(\d{1,2})', rent_day_str)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            try:
                due_date = datetime(today.year, month, day)
                overdue_days = max(0, (today - due_date).days)
            except ValueError:
                overdue_days = 0
        else:
            overdue_days = 0
        return {'status': 'overdue', 'days': overdue_days}
    
    # 条件2: 退租日非空 AND 今天日数 >= 退租日日数
    if not rent_end or rent_end in ['', '1899-12-30']:
        return None
    
    try:
        end_date = datetime.strptime(rent_end.strip(), '%Y-%m-%d')
        end_day = end_date.day
        
        if today_day > end_day:
            if today.month == 1:
                last_month = 12
                last_year = today.year - 1
            else:
                last_month = today.month - 1
                last_year = today.year
            try:
                last_due = datetime(last_year, last_month, end_day)
                overdue_days = (today - last_due).days
            except ValueError:
                overdue_days = (today_day - end_day)
            return {'status': 'overdue', 'days': overdue_days}
        elif today_day == end_day:
            return {'status': 'today', 'days': 0}
        else:
            return None
    except (ValueError, TypeError):
        return None


def check_lease_expiry(rent_end_str):
    """
    检查合同（退租日）是否到期或即将到期
    返回: None / {'status': 'expired', 'days': N} / {'status': 'expiring', 'days': N}
    """
    if not rent_end_str or rent_end_str.strip() == '':
        return None
    
    try:
        rent_end = datetime.strptime(rent_end_str.strip(), '%Y-%m-%d')
        today = datetime.now()
        days_diff = (rent_end - today).days
        
        if days_diff < 0:
            return {'status': 'expired', 'days': abs(days_diff)}
        elif days_diff <= 7:
            return {'status': 'expiring', 'days': days_diff}
        else:
            return None
    except (ValueError, TypeError):
        return None


def filter_rooms(rooms, skip_rows):
    """筛选需要提醒的房间"""
    result = {'overdue': [], 'today': []}
    
    for i, room in enumerate(rooms):
        row_num = i + 1
        
        if should_skip(room, row_num, skip_rows):
            continue
        
        lease_status = check_lease_expiry(room['rent_end'])
        if lease_status:
            room['lease_status'] = lease_status
        
        status = check_rent_status(room)
        if status:
            room['status'] = status
            if status['status'] == 'overdue':
                result['overdue'].append(room)
            else:
                result['today'].append(room)
    
    return result


# ========== HTML生成 ==========

def format_rent(rent_str):
    if not rent_str or rent_str.strip() == '':
        return '?'
    return rent_str.strip()


def format_payment(payment_str):
    if not payment_str or payment_str.strip() == '':
        return '月付'
    return payment_str.strip()


def format_lease_info(room):
    rent_start = room['rent_start'] or ''
    rent_end = room['rent_end'] or ''
    lease_status = room.get('lease_status')
    
    if rent_start and rent_end:
        base_info = f"{rent_start}~{rent_end}"
    elif rent_start:
        base_info = f"{rent_start}~"
    else:
        base_info = '未知租期'
    
    if lease_status:
        if lease_status['status'] == 'expired':
            base_info += f' · <span style="color:#D4380D;font-weight:bold">租约已到期{lease_status["days"]}天</span>'
        elif lease_status['status'] == 'expiring':
            base_info += f' · <span style="color:#E8853D;font-weight:bold">租约{lease_status["days"]}天后到期</span>'
    
    return base_info


def generate_room_html(room, is_overdue):
    rent = format_rent(room['rent'])
    payment = format_payment(room['payment'])
    lease = format_lease_info(room)
    
    if is_overdue:
        days = room['status']['days']
        return f'''<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room['room']}</b><span style="font-size:13px;color:#333"> ¥{rent}/月 · </span><span style="font-size:13px;color:#D4380D">逾期{days}天</span><br><span style="font-size:11px;color:#999">{lease} · {payment}</span></div>'''
    else:
        return f'''<div style="margin:0;line-height:1.3"><b style="font-size:14px">{room['room']}</b><span style="font-size:13px;color:#333"> ¥{rent}/月</span><br><span style="font-size:11px;color:#999">{lease} · {payment}</span></div>'''


def generate_building_html(doc_config, data):
    name = doc_config['name']
    colors = doc_config['colors']
    
    overdue_html = ''
    today_html = ''
    
    for room in data['overdue']:
        overdue_html += generate_room_html(room, True)
    
    for room in data['today']:
        today_html += generate_room_html(room, False)
    
    if not overdue_html and not today_html:
        content = '<div style="margin:0;color:#999">一切正常</div>'
    else:
        content = overdue_html
        if overdue_html and today_html:
            content += f'<div style="border-top:1px dashed {colors["dash"]};margin:8px 0 6px 0"></div>'
        content += today_html
    
    return f'''<h3 style="font-size:16px;margin:0 0 8px;padding-left:6px;border-left:3px solid {colors["border"]};color:{colors["title"]}">{name}</h3>
<div style="background:{colors["bg"]};border-radius:8px;padding:10px 13px">
{content}
</div>'''


def generate_html(yueju_data, caihong_data):
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    yueju_html = generate_building_html(DOCUMENTS['yueju'], yueju_data)
    caihong_html = generate_building_html(DOCUMENTS['caihong'], caihong_data)
    
    yueju_count = len(yueju_data['overdue']) + len(yueju_data['today'])
    caihong_count = len(caihong_data['overdue']) + len(caihong_data['today'])
    total = yueju_count + caihong_count
    
    return f'''<h2 style="font-size:17px;color:#222;margin:0 0 10px">📢 收租提醒 · {today_str}</h2>
{yueju_html}
<br>
{caihong_html}
<div style="background:#FAFAFA;border-radius:4px;padding:6px 12px;text-align:center;font-size:12px;color:#555;margin-top:10px">悦居 {yueju_count}间 · 彩虹 {caihong_count}间 · 共 {total}间</div>'''


# ========== 推送 ==========

def send_pushplus(html_content, yueju_data, caihong_data, is_all_clear=False):
    """发送PushPlus推送"""
    yueju_overdue = len(yueju_data['overdue']) if yueju_data else 0
    yueju_today = len(yueju_data['today']) if yueju_data else 0
    caihong_overdue = len(caihong_data['overdue']) if caihong_data else 0
    caihong_today = len(caihong_data['today']) if caihong_data else 0
    
    total = yueju_overdue + yueju_today + caihong_overdue + caihong_today
    
    if total > 0:
        parts = []
        if yueju_overdue + caihong_overdue > 0:
            parts.append(f'逾期{yueju_overdue + caihong_overdue}间')
        if yueju_today + caihong_today > 0:
            parts.append(f'今日交租{yueju_today + caihong_today}间')
        title = f'🏠 收租提醒 | {"·".join(parts)} | {total}间待处理'
    else:
        title = '🏠 收租提醒 | 一切正常'
    
    if is_all_clear:
        data = {
            'token': PUSHPLUS_TOKEN,
            'title': title,
            'content': '今天没有需要交租的房间，一切正常。',
            'template': 'html'
        }
    else:
        data = {
            'token': PUSHPLUS_TOKEN,
            'title': title,
            'content': html_content,
            'template': 'html'
        }
    
    try:
        resp = requests.post(
            PUSHPLUS_API,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            json=data,
            timeout=30
        )
        result = resp.json()
        if result.get('code') == 200:
            logger.info("✓ PushPlus推送成功")
            return True
        else:
            logger.error(f"✗ PushPlus推送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"✗ PushPlus推送异常: {e}")
        return False


def send_all(html_content, yueju_data, caihong_data, is_all_clear=False):
    """推送"""
    return send_pushplus(html_content, yueju_data, caihong_data, is_all_clear)


# ========== 主函数 ==========

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("房租提醒脚本开始执行 (V3-GitHub Actions版)")
    logger.info("=" * 50)
    
    # 检查环境变量
    if not ACCESS_TOKEN:
        logger.error("✗ 缺少环境变量 TENCENT_ACCESS_TOKEN")
        sys.exit(1)
    if not PUSHPLUS_TOKEN:
        logger.error("✗ 缺少环境变量 PUSHPLUS_TOKEN")
        sys.exit(1)
    
    try:
        # 检查Token有效期
        days_left = check_token_expiry()
        
        # 步骤1：通过API读取两份文档
        all_data = {}
        for key, doc in DOCUMENTS.items():
            logger.info(f"--- 处理 {doc['name']} ---")
            rows = get_sheet_data(doc['book_id'], doc['sheet_id'], doc['range'])
            rooms = parse_rows_to_rooms(rows)
            logger.info(f"✓ 解析到 {len(rooms)} 个房间记录")
            
            # 调试：打印前5个有效房间
            for i, room in enumerate(rooms[:10]):
                if room['room'] and not should_skip(room, i+1, doc['skip_rows']):
                    logger.info(f"  示例: {room['room']} | 退租日={room['rent_end']} | 付标记={room['paid_mark']} | 起租={room['rent_start']}")
            
            filtered = filter_rooms(rooms, doc['skip_rows'])
            logger.info(f"✓ 筛选结果: 逾期{len(filtered['overdue'])}间, 今日交租{len(filtered['today'])}间")
            
            for room in filtered['overdue']:
                logger.info(f"  ⚠️ 逾期: {room['room']} | 交租日={room['rent_day']} | 逾期{room['status']['days']}天")
            for room in filtered['today']:
                logger.info(f"  📅 今日: {room['room']} | 交租日={room['rent_day']}")
            
            all_data[key] = filtered
        
        # 步骤2：生成HTML并推送
        yueju = all_data['yueju']
        caihong = all_data['caihong']
        
        total_alerts = (len(yueju['overdue']) + len(yueju['today']) + 
                       len(caihong['overdue']) + len(caihong['today']))
        
        if total_alerts == 0:
            logger.info("今天没有需要交租的房间，一切正常。")
            send_all(None, yueju, caihong, is_all_clear=True)
        else:
            html = generate_html(yueju, caihong)
            send_all(html, yueju, caihong)
        
        # Token过期提醒（写入推送内容中提示用户更新）
        if days_left <= 5:
            logger.warning(f"⚠️ Token将在{days_left}天后过期！请尽快更新GitHub Secrets中的TENCENT_ACCESS_TOKEN")
        
        logger.info("=" * 50)
        logger.info("房租提醒脚本执行完成")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"✗ 执行失败: {e}", exc_info=True)
        # 推送失败通知
        try:
            send_pushplus(
                f'<div style="color:#D4380D;font-weight:bold">⚠️ 收租提醒脚本执行失败</div><div style="color:#999">{str(e)}</div>',
                {'overdue': [], 'today': []}, {'overdue': [], 'today': []},
                is_all_clear=False
            )
        except:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
