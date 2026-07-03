# 房租到期提醒系统

每天北京时间 13:00 自动检查腾讯文档中的房租数据，推送逾期和今日交租提醒到微信。

## 部署步骤

### 1. 创建 GitHub 仓库

1. 登录 GitHub，点击右上角 `+` → `New repository`
2. 仓库名填写 `rent-reminder`（或任意名称）
3. 选择 **Private**（私有仓库，因为包含敏感配置）
4. 不要勾选 "Add a README file"
5. 点击 `Create repository`

### 2. 上传项目文件

将以下文件上传到仓库根目录：
- `rent_reminder.py`
- `requirements.txt`
- `.github/workflows/rent_reminder.yml`

上传方式：在仓库页面点击 `Add file` → `Upload files`，拖入文件后 `Commit changes`

### 3. 配置 GitHub Secrets

进入仓库 → `Settings` → 左侧 `Secrets and variables` → `Actions` → 点击 `New repository secret`

逐个添加以下 5 个 Secret：

| Secret 名称 | 值 |
|---|---|
| `TENCENT_CLIENT_ID` | `23dd7aae48ce4db1a9308670bc22eb84` |
| `TENCENT_ACCESS_TOKEN` | 你的腾讯文档 access_token |
| `TENCENT_OPEN_ID` | `b34b505259484a0eba38cc44d3f44a38` |
| `TENCENT_CLIENT_SECRET` | `aff9f7d2ea3b465e9853aa4e1bfca9a9` |
| `PUSHPLUS_TOKEN` | `a956213e2a25450381f56d3bfa55c3ea` |

> **重要**：access_token 约 30 天过期，到期后需重新获取并更新此 Secret

### 4. 测试运行

1. 进入仓库 → `Actions` 标签页
2. 左侧选择 `Rent Reminder Daily`
3. 点击 `Run workflow` → `Run workflow` 按钮
4. 等待执行完成，检查日志和微信是否收到推送

### 5. 自动运行

配置完成后，GitHub Actions 会在每天北京时间 13:00 自动执行。
你也可以随时通过 `Run workflow` 手动触发。

## Token 续期

当 Token 过期时（脚本会提前 5 天提醒）：
1. 重新获取 access_token
2. 更新 GitHub Secret `TENCENT_ACCESS_TOKEN`
3. 手动触发一次 workflow 验证
