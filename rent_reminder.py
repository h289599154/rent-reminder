import requests
import base64
import json
import time

TOKEN = "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"
REPO = "h289599154/rent-reminder"
FILE = "rent_reminder.py"
BRANCH = "main"

# 1. 获取文件 SHA
resp = requests.get(
    f"https://api.github.com/repos/{REPO}/contents/{FILE}?ref={BRANCH}",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
sha = resp.json()["sha"]
print("SHA:", sha)

# 2. 准备测试代码
content = """#!/usr/bin/env python3
import os, sys, json, base64, requests
from datetime import datetime, timezone, timedelta

print("=== 脚本启动 ===")

CLIENT_ID = os.environ.get("TENCENT_CLIENT_ID", "")
ACCESS_TOKEN = os.environ.get("TENCENT_ACCESS_TOKEN", "")
OPEN_ID = os.environ.get("TENCENT_OPEN_ID", "")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
FRIEND_B_TOKEN = os.environ.get("FRIEND_B_TOKEN", "")
FRIEND_C_TOKEN = os.environ.get("FRIEND_C_TOKEN", "")

print("环境变量读取完成")
print("ACCESS_TOKEN长度:", len(ACCESS_TOKEN))
print("PUSHPLUS_TOKEN长度:", len(PUSHPLUS_TOKEN))

try:
    url = "https://docs.qq.com/openapi/spreadsheet/v3/files/300000000$NGUIfHYzcqNf/aopwxm/A1:H5"
    headers = {"Access-Token": ACCESS_TOKEN, "Client-Id": CLIENT_ID, "Open-Id": OPEN_ID}
    resp = requests.get(url, headers=headers, timeout=30)
    print("API状态码:", resp.status_code)
    if resp.status_code == 200:
        data = resp.json()
        rows = data.get("gridData", {}).get("rows", [])
        print("读取行数:", len(rows))
        if rows:
            print("第一行数据:", rows[0])
    else:
        print("API错误:", resp.text[:200])
except Exception as e:
    print("API请求异常:", str(e))

try:
    push_resp = requests.post("http://www.pushplus.plus/send", json={
        "token": PUSHPLUS_TOKEN,
        "title": "测试推送",
        "content": "如果收到此消息，说明脚本正常运行。",
        "template": "txt"
    }, timeout=10)
    print("PushPlus状态码:", push_resp.status_code)
    print("PushPlus返回:", push_resp.text[:200])
except Exception as e:
    print("PushPlus异常:", str(e))

print("=== 脚本结束 ===")
"""

# Base64 编码
content_bytes = content.encode('utf-8')
content_b64 = base64.b64encode(content_bytes).decode('utf-8')

# 3. 提交文件
data = {
    "message": "Test script - clean version",
    "content": content_b64,
    "sha": sha,
    "branch": BRANCH
}
resp = requests.put(
    f"https://api.github.com/repos/{REPO}/contents/{FILE}",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json=data
)
print("提交状态码:", resp.status_code)
if resp.status_code == 200:
    print("✅ 代码已提交")
else:
    print("提交失败:", resp.text[:200])

# 4. 触发工作流
resp = requests.post(
    f"https://api.github.com/repos/{REPO}/actions/workflows/rent_reminder.yml/dispatches",
    headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"},
    json={"ref": "main"}
)
print("触发状态码:", resp.status_code)
print("等待30秒...")
time.sleep(30)

# 5. 获取最新运行日志
runs_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
runs_data = runs_resp.json()
run_id = runs_data["workflow_runs"][0]["id"]
print("最新 Run ID:", run_id)

jobs_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
jobs_data = jobs_resp.json()
job_id = jobs_data["jobs"][0]["id"]
print("Job ID:", job_id)

logs_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/jobs/{job_id}/logs",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
print("=== 日志 ===")
print(logs_resp.text[-1000:])  # 最后1000字符
