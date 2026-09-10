# 架构概览

## 模块依赖关系

```
__main__.py (CLI)
    │
    ├─── api.py (HTTP客户端)
    │       │
    │       ├─── miutils.py (RC4加密)
    │       ├─── errors.py (异常类)
    │       └─── logger.py (日志)
    │
    └─── device.py (设备封装)
            │
            ├─── api.py (调用API)
            ├─── errors.py (异常类)
            └─── logger.py (日志)
```

## 数据流

```
用户输入 (CLI/Python代码)
    │
    ▼
__main__.py / Python API
    │
    ├─── 认证检查 (api.available)
    │       │
    │       └─── _refresh_token() → _get_location()
    │
    ├─── 设备发现
    │       │
    │       └─── api.get_devices_list()
    │               │
    │               └─── _request() → 加密POST → 小米服务器
    │
    ├─── 设备规格获取
    │       │
    │       └─── get_device_info(model)
    │               │
    │               └─── HTTP GET home.miot-spec.com → 解析HTML
    │
    └─── 设备控制
            │
            ├─── MiotDevice.get()/set() → api.get_devices_prop() / set_devices_prop()
            ├─── MiotDevice.run_action() → api.run_action()
            └─── PCDevice.power_on() → 动作/属性 → MiotDevice
```

## 类继承关系

```
Exception
  ├── LoginError
  ├── APIError
  ├── DeviceNotFoundError
  ├── MultipleDevicesFoundError
  ├── DeviceGetError
  ├── DeviceSetError
  ├── DeviceActionError
  └── GetDeviceInfoError

miiotpcAPI              ← 核心HTTP客户端（认证、加密、API调用）
    │
MiotDevice              ← 通用设备封装（属性读写、动作执行）
    │
PCDevice                ← PC高层封装（语义化控制）
```

## 文件职责图

```
┌─────────────────────────────────────────────────────────────┐
│                        miiotpcApi                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ __main__.py  │  │   api.py     │  │  device.py   │      │
│  │              │  │              │  │              │      │
│  │ CLI参数解析   │  │ HTTP客户端    │  │ MiotDevice   │      │
│  │ 子命令分发    │  │ 认证管理     │  │ PCDevice     │      │
│  │ 输出格式化    │  │ 加密请求     │  │ MIoT Spec    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  errors.py   │  │  logger.py   │  │  miutils.py  │      │
│  │              │  │              │  │              │      │
│  │ 异常类定义    │  │ 彩色日志      │  │ RC4加密      │      │
│  │ 错误码映射    │  │ 日志级别控制  │  │ Nonce生成    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 认证数据流

```
首次登录:
  用户扫码 → _complete_qr_login() → 提取token → 保存auth.json

后续使用:
  加载auth.json → _init_session() → 设置Cookie/Headers

Token过期:
  _refresh_token() → _get_location() → 获取新token → 保存auth.json

API请求:
  _request() → 检查token → 生成nonce → RC4加密 → 签名 → POST
```

## PCDevice 能力检测流

```
PCDevice.__init__()
    │
    ▼
MiotDevice(api) → get_device_info(model)
    │
    ▼
解析 MIoT Spec
    │
    ├─── 属性列表 (prop_list)
    │       │
    │       └─── 遍历匹配:
    │             on/power/switch → _capabilities["power"] = True
    │             brightness/screen-brightness → _capabilities["brightness"] = True
    │             volume/speaker-volume → _capabilities["volume"] = True
    │             lock/screen-lock → _capabilities["lock"] = True
    │
    └─── 动作列表 (action_list)
            │
            └─── 遍历匹配:
                  power-on/turn-on/boot → _capabilities["power_on"] = True
                  power-off/turn-off/shutdown → _capabilities["power_off"] = True
                  sleep/suspend/hibernate → _capabilities["sleep"] = True
                  wake/wake-up/resume → _capabilities["wake"] = True
```

## 请求加密流程

```
原始数据: {"did":"123","siid":2,"piid":1}
    │
    ▼
JSON序列化: "data={\"did\":\"123\",\"siid\":2,\"piid\":1}"
    │
    ▼
生成nonce: Base64(8字节随机 + 4字节时间戳)
    │
    ▼
生成signed_nonce: Base64(SHA256(ssecurity + nonce))
    │
    ▼
生成签名: Base64(HMAC-SHA1("POST", uri, params, signed_nonce))
    │
    ▼
RC4加密每个参数值（跳过前1024字节）
    │
    ▼
附加: signature, ssecurity, _nonce
    │
    ▼
POST到 api.mijia.tech/app + uri
```

## 错误处理链

```
小米服务器返回错误
    │
    ▼
_request() 检查 code != 0
    │
    ▼
抛出 APIError(code, message)
    │
    ├─── 设备层捕获
    │       │
    │       └─── 转为 DeviceGetError/DeviceSetError/DeviceActionError
    │
    └─── 用户层捕获
            │
            └─── 错误提示/重试/退出
```
