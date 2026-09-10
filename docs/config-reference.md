# 配置参考

## 一、文件路径

### 认证文件

| 项目 | 默认值 | 可通过参数覆盖 |
|------|--------|---------------|
| 认证文件 | `~/.config/miiotpc-api/auth.json` | `-p` / `--auth_path` |
| MIoT Spec 缓存 | 认证文件同目录 | `cache_path` 参数 |

**认证文件目录结构：**
```
~/.config/miiotpc-api/
├── auth.json                    # 认证数据
├── <model1>.json                # MIoT Spec 缓存
├── <model2>.json
└── ...
```

### 自定义路径示例

```bash
# CLI 指定路径
miiotpcApi -p /path/to/auth.json login
miiotpcApi -p /path/to/dir/ get --dev_name "..." --prop_name on

# Python 指定路径
api = miiotpcAPI(auth_data_path="/path/to/auth.json")
api = miiotpcAPI(auth_data_path="/path/to/dir/")
```

---

## 二、环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MIIOTPC_LOG_LEVEL` | `INFO` | 日志级别 |

**可选值：** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

```bash
# 设置日志级别
export MIIOTPC_LOG_LEVEL=DEBUG

# Windows PowerShell
$env:MIIOTPC_LOG_LEVEL = "DEBUG"
```

**日志输出示例：**

```
# INFO 级别（默认）
2024-01-01 12:00:00 - miiotpcApi - INFO: 登录成功

# DEBUG 级别
2024-01-01 12:00:00 - miiotpcApi - DEBUG: 请求 URI: /miotspec/prop/get，数据: {...}
2024-01-01 12:00:00 - miiotpcApi - DEBUG: 响应数据: {...}
```

---

## 三、pyproject.toml 完整配置

```toml
[project]
name = "miiotpcApi"
version = "0.1.0"
description = "米家笔记本/PC设备控制 API"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
authors = [
    { name = "Your Name", email = "your@email.com" }
]
keywords = ["mijia", "xiaomi", "miot", "pc", "laptop", "smart-home"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Operating System :: OS Independent",
    "Topic :: Home Automation",
]
dependencies = [
    "pycryptodome>=3.23.0",
    "qrcode>=8.2",
    "requests>=2.32.5",
    "tzlocal>=5.3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.urls]
Homepage = "https://github.com/yourname/miiotpcApi"
Repository = "https://github.com/yourname/miiotpcApi"
Issues = "https://github.com/yourname/miiotpcApi/issues"

[project.scripts]
miiotpcApi = "miiotpcApi.__main__:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/miiotpcApi"]
```

---

## 四、依赖版本说明

| 依赖 | 最低版本 | 用途 | 可选 |
|------|---------|------|------|
| `pycryptodome` | 3.23.0 | RC4 加密 | 否 |
| `qrcode` | 8.2 | 生成登录二维码 | 否 |
| `requests` | 2.32.5 | HTTP 请求 | 否 |
| `tzlocal` | 5.3.1 | 获取本地时区 | 否 |

**不需要的依赖（相比 mijiaAPI）：**
- ~~`fastmcp`~~ — MCP Server（已移除）
- ~~`pillow`~~ — qrcode 可选图片依赖（不需要）

---

## 五、默认配置汇总

| 配置项 | 默认值 | 来源 |
|--------|--------|------|
| API 端点 | `https://api.mijia.tech/app` | `api.py` |
| 登录 URL | `https://account.xiaomi.com/longPolling/loginUrl` | `api.py` |
| 服务登录 URL | `https://account.xiaomi.com/pass/serviceLogin` | `api.py` |
| 设备规格 URL | `https://home.miot-spec.com/spec/` | `device.py` |
| 认证文件路径 | `~/.config/miiotpc-api/auth.json` | `api.py` |
| 日志级别 | `INFO` | `logger.py` |
| 设备操作间隔 | 0.5秒 | `MiotDevice.sleep_time` |
| Token 缓存时间 | 60秒 | `api.py._available_cache_time` |
| 扫码超时 | 120秒 | `api.py._complete_qr_login` |
| 设备列表分页 | 200条/页 | `api.py._get_all_devices` |

---

## 六、网络配置

### 超时设置

```python
# 登录长轮询超时: 120秒
lp_ret = session.get(login_data["lp"], headers=headers, timeout=120)

# API 请求使用 requests.Session 默认超时（无限制）
# 如需自定义，可修改 api.py 中的 _request() 方法
```

### 代理设置

如需通过代理访问小米服务器：

```python
api = miiotpcAPI()
# 修改 session 的代理设置
api.session.proxies = {
    "http": "http://proxy:port",
    "https": "http://proxy:port",
}
```

### User-Agent

默认模拟 Android 15 小米设备：

```
Android-15-11.0.701-Xiaomi-23046RP50C-OS2.0.212.0.VMYCNXM-<随机ID>-CN-<随机ID>-<随机ID>-SmartHome-MI_APP_STORE-<ID>|<ID>|<pass_o>-64
```

---

## 七、PCDevice 能力检测关键词

### 属性匹配关键词

| 能力 | 匹配的属性名关键词 |
|------|-------------------|
| power | `on`, `power`, `switch`, `power-status` |
| brightness | `brightness`, `screen-brightness`, `display-brightness` |
| volume | `volume`, `speaker-volume` |
| lock | `lock`, `screen-lock`, `locked` |

### 动作匹配关键词

| 能力 | 匹配的动作名关键词 |
|------|-------------------|
| power_on | `power-on`, `turn-on`, `on`, `boot` |
| power_off | `power-off`, `turn-off`, `off`, `shutdown` |
| sleep | `sleep`, `suspend`, `hibernate` |
| wake | `wake`, `wake-up`, `resume` |
| lock | `lock`, `lock-screen` |

### 扩展关键词

如需匹配更多关键词，修改 `device.py` 中 PCDevice 类的类属性：

```python
class PCDevice:
    _POWER_PROPS = {"on", "power", "switch", "power-status", "your-custom-keyword"}
    _BRIGHTNESS_PROPS = {"brightness", "screen-brightness", "your-custom-keyword"}
    # ...
```

---

## 八、CLI 参数完整参考

### 全局选项

```
miiotpcApi [选项]

选项:
  -v, --version              显示版本信息
  -p, --auth_path PATH       认证文件路径 (默认: ~/.config/miiotpc-api/auth.json)
  -l, --list_devices         列出所有设备
  --list_pc                  仅列出PC/笔记本设备
  --get_device_info MODEL    获取设备MIoT Spec
```

### login 子命令

```
miiotpcApi login [选项]

选项:
  -p, --auth_path PATH       认证文件路径
```

### get 子命令

```
miiotpcApi get [选项]

选项:
  -p, --auth_path PATH       认证文件路径
  --did DID                  设备ID
  --dev_name NAME            设备名称
  --prop_name NAME           属性名 (必填)
```

### set 子命令

```
miiotpcApi set [选项]

选项:
  -p, --auth_path PATH       认证文件路径
  --did DID                  设备ID
  --dev_name NAME            设备名称
  --prop_name NAME           属性名 (必填)
  --value VALUE              属性值 (必填)
```

### action 子命令

```
miiotpcApi action [选项]

选项:
  -p, --auth_path PATH       认证文件路径
  --did DID                  设备ID (与 --dev_name 互斥)
  --dev_name NAME            设备名称 (与 --did 互斥)
  --action_name NAME         动作名 (必填)
  --params JSON              动作参数 JSON 对象
```

### 顶层 PC 控制选项

```
miiotpcApi [选项]

选项:
  -p, --auth_path PATH       认证文件路径
  --list-pc                  列出PC设备
  --did DID                  设备ID (与 --dev_name 互斥)
  --dev_name NAME            设备名称 (与 --did 互斥)
  --power {on,sleep,off}      on=唤醒/开机，sleep=睡眠，off=关机
  --temperature              获取CPU温度
  --battery                  获取电池电量
  --charging-state           获取充电状态
  --status                   获取状态概览
```

---

## 九、错误码完整列表

| 错误码 | 含义 |
|--------|------|
| `-10000` | 未知错误 |
| `-10001` | 服务不可用 |
| `-10002` | 参数无效 |
| `-10003` | 资源不足 |
| `-10004` | 内部错误 |
| `-10005` | 权限不足 |
| `-10006` | 执行超时 |
| `-10007` | 设备离线或者不存在 |
| `-10020` | 未授权OAuth2 |
| `-10030` | 无效的token（HTTP） |
| `-10040` | 无效的消息格式 |
| `-10050` | 无效的证书 |
| `-704000000` | 未知错误 |
| `-704010000` | 未授权（设备可能被删除） |
| `-704014006` | 没找到设备描述 |
| `-704030013` | Property不可读 |
| `-704030023` | Property不可写 |
| `-704030033` | Property不可订阅 |
| `-704040002` | Service不存在 |
| `-704040003` | Property不存在 |
| `-704040004` | Event不存在 |
| `-704040005` | Action不存在 |
| `-704040999` | 功能未上线 |
| `-704042001` | Device不存在 |
| `-704042011` | 设备离线 |
| `-704053036` | 设备操作超时 |
| `-704053100` | 设备在当前状态下无法执行此操作 |
| `-704083036` | 设备操作超时 |
| `-704090001` | Device不存在 |
| `-704220008` | 无效的ID |
| `-704220025` | Action参数个数不匹配 |
| `-704220035` | Action参数错误 |
| `-704220043` | Property值错误 |
| `-704222034` | Action返回值错误 |
| `-705004000` | 未知错误 |
| `-705004501` | 未知错误 |
| `-705201013` | Property不可读 |
| `-705201015` | Action执行错误 |
| `-705201023` | Property不可写 |
| `-705201033` | Property不可订阅 |
| `-706012000` | 未知错误 |
| `-706012013` | Property不可读 |
| `-706012015` | Action执行错误 |
| `-706012023` | Property不可写 |
| `-706012033` | Property不可订阅 |
| `-706012043` | Property值错误 |
| `-706014006` | 没找到设备描述 |
