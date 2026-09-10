# 底层协议参考

> 了解 miiotpcApi 与小米服务器通信的底层协议细节

## 一、认证流程

### 1.1 二维码登录时序

```
用户设备              小米服务器               米家APP
  │                    │                    │
  │  _get_location()   │                    │
  │───────────────────>│                    │
  │   返回 location    │                    │
  │<───────────────────│                    │
  │                    │                    │
  │  location 有效?    │                    │
  │   ├─ 是: 刷新成功   │                    │
  │   └─ 否: 获取二维码  │                    │
  │                    │                    │
  │  login_url 请求    │                    │
  │───────────────────>│                    │
  │  返回 loginUrl/qr  │                    │
  │<───────────────────│                    │
  │                    │                    │
  │  终端显示二维码 ─────────────────────>│
  │                    │         用户扫码    │
  │                    │<─────────────────  │
  │                    │                    │
  │  长轮询 (120秒)     │                    │
  │───────────────────>│                    │
  │  返回 auth 数据     │                    │
  │<───────────────────│                    │
  │                    │                    │
  │  获取 cookies       │                    │
  │───────────────────>│                    │
  │<───────────────────│                    │
```

### 1.2 认证数据结构 (auth.json)

```json
{
  "ua": "Android-15-11.0.701-Xiaomi-...",
  "pass_o": "a1b2c3d4e5f67890",
  "deviceId": "AbCdEfGhIjKlMnOp",
  "psecurity": "...",
  "nonce": "...",
  "ssecurity": "...",
  "passToken": "...",
  "userId": "1234567890",
  "cUserId": "...",
  "serviceToken": "...",
  "expireTime": 1700000000000,
  "saveTime": 1699900000000
}
```

### 1.3 Token 刷新机制

```python
def _refresh_token(self) -> dict:
    """Token 刷新逻辑

    1. 检查 available 属性（60秒缓存）
    2. 调用 _get_location() 获取新 token
    3. 成功则保存认证数据并重建 session
    4. 失败则抛出 LoginError
    """
    if self.available:
        return self.auth_data  # 缓存未过期

    location_data = self._get_location()
    if location_data.get("code") == 0:
        self._save_auth_data()
        self._init_session()
        return self.auth_data
    else:
        raise LoginError(-1, "刷新Token失败")
```

---

## 二、加密请求流程

### 2.1 请求签名与加密

每个 API 请求都经过以下处理：

```
原始请求数据
    │
    ▼
JSON 序列化 {"data": "{\"did\":\"123\",\"siid\":2,\"piid\":1}"}
    │
    ▼
生成 nonce（随机数 + 时间戳的 Base64）
    │
    ▼
生成 signed_nonce = SHA256(ssecurity + nonce) 的 Base64
    │
    ▼
生成 RC4 签名 = HMAC-SHA1(方法, URI, 参数, signed_nonce)
    │
    ▼
RC4 加密每个参数值（跳过前1024字节）
    │
    ▼
附加 signature, ssecurity, _nonce 到参数
    │
    ▼
POST 请求到 api.mijia.tech
```

### 2.2 nonce 生成

```python
def gen_nonce():
    """生成 Base64 编码的 nonce

    结构: [8字节随机数] + [4字节时间戳（毫秒/60000）]
    """
    millis = int(round(time.time() * 1000))
    b = (random.getrandbits(64) - 2**63).to_bytes(8, "big", signed=True)
    part2 = int(millis / 60000)
    b += part2.to_bytes(((part2.bit_length()+7)//8), "big")
    return base64.b64encode(b).decode("utf-8")
```

### 2.3 RC4 加密

```python
def encrypt_rc4(password, payload):
    """RC4 加密

    特殊处理: 跳过前 1024 字节（小米协议要求）
    """
    r = ARC4.new(base64.b64decode(password))
    r.encrypt(bytes(1024))  # 跳过前1024字节
    return base64.b64encode(r.encrypt(payload.encode())).decode()
```

---

## 三、MIoT Spec 协议

### 3.1 Spec 获取

从 `https://home.miot-spec.com/spec/{model}` 获取设备规格。

响应为 HTML 页面，嵌入 JSON 数据在 `<script data-page="app">` 标签中。

### 3.2 属性读写

**读取属性：**
```
POST https://api.mijia.tech/app/miotspec/prop/get

请求体:
{
    "params": [
        {"did": "123456", "siid": 2, "piid": 1}
    ],
    "datasource": 1
}

响应:
{
    "result": [
        {"did": "123456", "siid": 2, "piid": 1, "value": true, "code": 0, "updateTime": 1234567890}
    ]
}
```

**设置属性：**
```
POST https://api.mijia.tech/app/miotspec/prop/set

请求体:
{
    "params": [
        {"did": "123456", "siid": 2, "piid": 1, "value": true}
    ]
}

响应:
{
    "result": [
        {"did": "123456", "siid": 2, "piid": 1, "code": 0, "message": "成功"}
    ]
}
```

### 3.3 动作执行

```
POST https://api.mijia.tech/app/miotspec/action

请求体:
{
    "params": {
        "did": "123456",
        "siid": 2,
        "aiid": 1,
        "value": [2]  // 可选参数列表
    }
}

响应:
{
    "result": {
        "did": "123456",
        "siid": 2,
        "aiid": 1,
        "code": 0,
        "message": "成功"
    }
}
```

### 3.4 请求头要求

```python
headers = {
    "User-Agent": "Android-15-11.0.701-Xiaomi-...",  # 模拟小米设备
    "Content-Type": "application/x-www-form-urlencoded",
    "miot-accept-encoding": "GZIP",
    "miot-encrypt-algorithm": "ENCRYPT-RC4",
    "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
}
```

---

## 四、API 端点汇总

| 端点 | 方法 | 说明 | miiotpcApi 中使用 |
|------|------|------|-------------------|
| `/app/miotspec/prop/get` | POST | 读取属性 | ✅ get_devices_prop() |
| `/app/miotspec/prop/set` | POST | 设置属性 | ✅ set_devices_prop() |
| `/app/miotspec/action` | POST | 执行动作 | ✅ run_action() |
| `/v2/home/device_list_page` | POST | 设备列表 | ✅ get_devices_list() |
| `/v2/message/v2/check_new_msg` | POST | Token检测 | ✅ check_new_msg() |
| `/v2/homeroom/gethome_merged` | POST | 家庭列表 | ❌ 已移除 |
| `/home/home_device_list` | POST | 家庭设备 | ❌ 已移除 |
| `/appgateway/.../GetSimpleSceneList` | POST | 场景列表 | ❌ 已移除 |
| `/appgateway/.../NewRunScene` | POST | 执行场景 | ❌ 已移除 |
| `/v2/home/standard_consumable_items` | POST | 耗材列表 | ❌ 已移除 |
| `/v2/user/statistics` | POST | 统计数据 | ❌ 已移除 |

---

## 五、设备发现流程

```
miiotpcAPI.get_devices_list()
    │
    ▼
POST /v2/home/device_list_page
    │
    ▼
返回所有设备列表
    │
    ├─ 每个设备包含:
    │   ├─ did: 设备ID (唯一标识)
    │   ├─ name: 设备名称 (用户设定)
    │   ├─ model: 设备型号 (如 yeelink.light.lamp4)
    │   ├─ isOnline: 在线状态
    │   └─ ...
    │
    ▼
find_pc_devices(keyword) 筛选
    │
    ├─ 匹配 name 或 model 中的关键词
    │   (pc, 电脑, 笔记本, laptop, desktop, notebook)
    │
    ▼
返回 PC 设备列表
```

---

## 六、PCDevice 能力检测流程

```
PCDevice.__init__()
    │
    ▼
MiotDevice 初始化 → 获取 MIoT Spec
    │
    ▼
_detect_capabilities()
    │
    ├─ 遍历 prop_list，匹配属性名:
    │   ├─ on, power, switch → power 能力
    │   ├─ brightness, screen-brightness → brightness 能力
    │   ├─ volume, speaker-volume → volume 能力
    │   └─ lock, screen-lock → lock 能力
    │
    ├─ 遍历 action_list，匹配动作名:
    │   ├─ power-on, turn-on, boot → power_on 能力
    │   ├─ power-off, turn-off, shutdown → power_off 能力
    │   ├─ sleep, suspend, hibernate → sleep 能力
    │   ├─ wake, wake-up, resume → wake 能力
    │   └─ lock, lock-screen → lock 能力
    │
    ▼
self._capabilities = {
    "power": True/False,
    "sleep": True/False,
    "wake": True/False,
    "lock": True/False,
    "brightness": True/False,
    "volume": True/False,
    ...
}
```
