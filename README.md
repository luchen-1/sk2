# 护肤品价格监控助手

这是一个本地运行的护肤品价格监控工具。当前主链路是：

```text
一键启动价格助手.bat -> dashboard.py 本地网页控制台 -> 手动录入淘宝/抖音真实到手价 -> SQLite -> 报告 -> 邮件提醒
```

当前只支持淘宝、天猫、天猫国际和抖音商品，不恢复京东、拼多多或其他平台逻辑。

## 客户电脑首次安装

第一次在客户电脑上使用时，按下面步骤准备环境：

1. 解压项目压缩包到任意本地目录，路径可以包含中文。
2. 双击：

```text
安装环境.bat
```

3. 等待脚本检查 Python、创建 `.venv`、安装依赖并完成基础检查。
4. 如果提示未检测到 Python，请安装 Python 3.10 或以上版本，并勾选 `Add Python to PATH`。
5. 安装完成后打开 `.env`，填写邮箱配置。
6. QQ 邮箱需要填写 SMTP 授权码，不是 QQ 登录密码。
7. 双击：

```text
启动价格助手.bat
```

8. 页面打开后点击“系统自检”。
9. 点击页面里的“测试邮件”，或在命令行运行：

```powershell
.\.venv\Scripts\python main.py --test-email
```

10. 测试邮箱通过后，就可以开始录入淘宝/抖音真实到手价。

## 客户使用版说明

### 1. 如何启动

双击项目目录里的：

```text
启动价格助手.bat
```

浏览器会自动打开本地控制台：

```text
http://127.0.0.1:8765
```

如果端口 8765 已被占用，命令窗口会提示关闭占用程序后再试。

### 2. 如何录入淘宝价格

1. 用 Edge 或 Chrome 正常打开淘宝、天猫或天猫国际商品页。
2. 自己确认页面里的真实到手价或券后价。
3. 回到本地控制台，选择对应商品。
4. 输入当前真实到手价，点击“保存并判断”。

### 3. 如何录入抖音价格

1. 用手机抖音 App 查看真实到手价。
2. 回到本地控制台，选择对应抖音商品。
3. 输入 App 里看到的真实到手价，点击“保存并判断”。

抖音 Web 页面如果显示 `¥???` 或提示前往抖音 App 查看完整价格，这是平台隐藏价格的正常情况，建议直接用本地控制台手动录入 App 看到的价格。

### 4. 如何生成报告

在本地控制台点击：

```text
生成报告
```

报告会保存到：

```text
reports/price_check_report_YYYYMMDD_HHMMSS.md
```

报告标题为“护肤品价格监控报告”，会按中文展示已达到心理价、未达到心理价、未采集商品、最近采集记录和邮件处理结果。

### 5. 如何发送提醒邮件

在本地控制台点击：

```text
发送提醒邮件
```

只有符合规则的商品才会发送正式提醒：

- 已达到或等于心理价。
- 数据没有过期。
- 价格可信度为手动确认价、高可信或中可信。
- 当商品要求明确券后价时，普通页面价不会发送正式提醒。
- 同一天已经提醒过的同商品同价格同级别提醒会跳过，避免重复发送。

### 6. 如何测试邮箱

在本地控制台点击：

```text
测试邮件
```

也可以在命令行运行：

```powershell
.\.venv\Scripts\python main.py --test-email
```

测试邮件只验证 SMTP 是否可用，不依赖商品价格。程序不会显示 SMTP 密码、授权码或 `.env` 真实内容。

### 7. 如何查看最新报告

点击：

```text
查看最新报告
```

页面会直接显示最新 Markdown 报告内容。

### 8. 如何做系统自检

点击：

```text
系统自检
```

自检会检查：

- products.xlsx 是否存在并能加载。
- 商品数量是否为 22 条，淘宝 11 条，抖音 11 条。
- .env 邮件配置必要字段是否存在。
- price_history.db 是否可连接。
- reports/ 目录是否存在且可写。
- 是否能生成报告。

自检只检查邮件配置字段是否存在，不显示 SMTP 密码、授权码或 `.env` 真实内容。

### 9. 如何备份数据库

点击：

```text
备份数据库
```

数据库会复制到：

```text
backups/price_history_backup_YYYYMMDD_HHMMSS.db
```

建议清理测试数据前先备份数据库。

### 10. 如何清理测试数据

点击：

```text
清空测试数据
```

页面会二次确认。当前只会清理备注或原始价格文本中明确包含 `测试`、`test` 或 `dashboard_validation` 的手动录入记录，并同步清理关联的已提醒记录。

如果无法区分测试数据和真实数据，程序不会默认清空全部历史，会提示先备份数据库。

### 11. 如何修改商品清单

打开：

```text
products.xlsx
```

常用字段：

```text
id, name, platform, url, target_price, enabled,
promo_name, promo_start, promo_end, require_final_price, note
```

注意：

- `platform` 只填写淘宝或抖音。
- `target_price` 必须是数字。
- `enabled=FALSE` 的商品不会参与监控。
- 修改后回到控制台点击刷新页面或重新打开助手。

### 12. 如何配置邮箱

修改项目目录下的：

```text
.env
```

需要的字段：

```env
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=
EMAIL_TO=
```

不要把 `.env` 发给别人，不要提交到代码仓库，不要截图展示邮箱授权码。

## 常见问题

### 双击安装环境.bat 后提示找不到 Python 怎么办？

安装 Python 3.10 或以上版本，安装时勾选 `Add Python to PATH`。安装完成后重新双击 `安装环境.bat`。

### 邮件发不出去怎么办？

检查 `.env` 中的 `SMTP_HOST`、`SMTP_PORT`、邮箱账号、SMTP 授权码、DNS 和网络连接。QQ 邮箱要使用 SMTP 授权码，不是登录密码。

### 为什么没有发邮件？

常见原因：

- 当前价格没有达到心理价。
- 价格数据已经过期。
- 价格可信度较低。
- 商品设置了 `require_final_price=TRUE`，但价格来源只是普通页面价。
- 今天已经对同商品同价格同级别提醒过。
- `.env` 邮件配置不完整。

可以查看报告里的“邮件提醒处理结果”，也可以在控制台看“邮件处理原因”。

### 为什么显示今日已提醒？

为了避免一天内重复发同样的提醒，系统会记录已发送提醒。同一天同商品、同价格、同提醒级别已经发送过时，会显示“今日已提醒，避免重复发送”。

### 为什么抖音不能自动读取？

抖音 Web 端经常隐藏完整价格，显示 `¥???` 或要求打开抖音 App。本项目不抓包抖音 App、不逆向接口、不读取 Cookie，所以推荐在手机 App 看价格后手动录入。

### 为什么淘宝不是自动抓？

本工具不绕过平台限制，不保存淘宝账号密码，也不读取 Cookie。淘宝价格建议用户正常打开页面确认后，在本地控制台手动录入。

### 如何重新安装依赖？

重新运行 `安装环境.bat`。如果 `.venv` 已存在，脚本会跳过创建虚拟环境，并重新检查和安装 `requirements.txt` 中的依赖。

### 如何清理测试数据？

测试时请在备注里写“测试”或 `test`。之后点击“清空测试数据”即可清理这些明确标记的测试记录。没有明确标记时，系统不会默认删除真实历史数据。

### 如何备份数据库？

点击“备份数据库”。备份文件会保存在 `backups/` 目录。

## Chrome/Edge 插件

`chrome_extension/` 继续保留，但不再强依赖。

插件适合在淘宝/抖音 Web 页面里快速采集当前页面可见文本和价格候选。普通客户最推荐使用：

```text
启动价格助手.bat + 本地网页控制台
```

## 命令行仍可用

生成报告，不发邮件：

```powershell
.\.venv\Scripts\python main.py --once --no-email
```

生成报告并发送符合规则的提醒邮件：

```powershell
.\.venv\Scripts\python main.py --once
```

启动循环：

```powershell
.\.venv\Scripts\python main.py
```

每 30 分钟运行一次：

```powershell
.\.venv\Scripts\python main.py --interval-minutes 30
```

测试邮箱：

```powershell
.\.venv\Scripts\python main.py --test-email
```

备用手动录入命令：

```powershell
.\.venv\Scripts\python manual_collect.py
```

## 本地网页接口

- `GET /health`
- `GET /api/products`
- `GET /api/status`
- `GET /api/recent`
- `GET /api/self-check`
- `GET /api/latest-report`
- `POST /api/manual-collect`
- `POST /api/collect`
- `POST /api/generate-report`
- `POST /api/send-alerts`
- `POST /api/test-email`
- `POST /api/backup-db`
- `POST /api/clear-test-data`

## 安全说明

- 不保存淘宝/抖音账号密码。
- 不读取 Cookie。
- 不抓包抖音 App。
- 不接第三方 API。
- 不绕过验证码、滑块或安全验证。
- 不自动下单。
- 不打印 `.env`、SMTP 密码、授权码、Cookie、账号或密码。
- `.env`、`price_history.db`、`reports/`、`screenshots/`、`backups/` 不要提交。
