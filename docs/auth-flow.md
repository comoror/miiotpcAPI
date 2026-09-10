# 认证流程详解

> 完整的认证数据流和状态转换

## 一、认证状态机

```
                   ┌─────────────────────────────────┐
                   │         无认证数据                │
                   │    (auth_data = {})               │
                   └───────────────┬─────────────────┘
                                   │
                        miiotpcAPI()
                                   │
                                   ▼
                   ┌─────────────────────────────────┐
                   │       未登录状态                  │
                   │    available = False              │
                   └───────────────┬─────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
               api.login()                   api.available
                    │                             │
                    ▼                             ▼
          ┌─────────────────┐        ┌─────────────────────┐
          │  二维码登录流程   │        │   _refresh_token()  │
          │                 │        │                     │
          │ 1. _get_location()       │ 1. _get_location() │
          │    └─ 返回二维码 URL      │    └─ 尝试刷新      │
          │ 2. 终端显示二维码  │        │ 2. 成功?            │
          │    + QR图片链接   │        │    ├─ 是: 保存数据  │
          │ 3. 用户扫码(120s)│        │    └─ 否: 失败     │
          │ 4. 获取 auth 数据 │        └─────────────────────┘
          │ 5. 保存到文件    │
          └────────┬────────┘
                   │
                   ▼
       ┌───────────────────────────────┐
       │      已登录状态                 │
       │   available = True              │
       │   auth_data 有完整数据          │
       └───────────────┬───────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
     每次请求      Token过期     手动登出
          │            │            │
          ▼            ▼            ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ 正常请求  │  │ 自动刷新  │  │ 清除数据  │
  │ _request()│  │          │  │          │
  └──────────┘  └──────────┘  └──────────┘
```

## 二、认证数据生命周期

### 2.1 首次登录

```python
# Step 1: 创建 API 实例（无认证文件）
api = miiotpcAPI()  # auth_data = {}

# Step 2: 调用 login()
api.login()  # 或 api.QRlogin()

# 内部流程:
# 1. _get_location() → 返回 location URL
# 2. location 无效（code != 0）→ 需要登录
# 3. _get_qr_login_data() → 获取 loginUrl 和 lp（长轮询地址）
# 4. _print_qr() → 终端显示二维码
# 5. _complete_qr_login() → 长轮询等待扫码（120秒超时）
# 6. 从响应中提取: psecurity, nonce, ssecurity, passToken, userId, cUserId
# 7. 获取 cookies: serviceToken, cUserId 等
# 8. 保存到 auth.json（添加 saveTime, expireTime）

# Step 3: 认证完成
# auth_data 现在包含所有必要字段
# session 已初始化（_init_session()）
# api.available 返回 True
```

### 2.2 后续使用

```python
# 创建 API 实例（已有认证文件）
api = miiotpcAPI()  # 加载 auth.json

# 检查认证状态
if api.available:
    # Token 有效，直接使用
    devices = api.get_devices_list()
else:
    # Token 过期，尝试刷新
    try:
        api._refresh_token()
        # 刷新成功，继续使用
    except LoginError:
        # 刷新失败，需要重新登录
        api.login()
```

### 2.3 Token 过期处理

```python
# 在 _request() 中自动处理
def _request(self, uri, data, refresh_token=True):
    if refresh_token:
        self._refresh_token()  # 自动检查并刷新
    # ... 发送请求 ...
```

## 三、认证数据字段说明

### 3.1 必要字段

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `ua` | str | 首次登录生成 | User-Agent，模拟小米设备 |
| `ssecurity` | str | 登录响应 | 会话密钥，用于加密 |
| `userId` | str | 登录响应 | 用户ID |
| `cUserId` | str | 登录响应 | 加密用户ID |
| `serviceToken` | str | 登录响应 | 服务令牌 |
| `passToken` | str | 登录响应 | 通行证令牌 |
| `psecurity` | str | 登录响应 | 密码安全令牌 |
| `nonce` | str | 登录响应 | 一次性随机数 |

### 3.2 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `pass_o` | str | 16位随机hex，首次使用时生成 |
| `deviceId` | str | 16位随机标识，首次使用时生成 |
| `expireTime` | int | 过期时间戳（毫秒） |
| `saveTime` | int | 保存时间戳（毫秒） |

### 3.3 available 属性检查逻辑

```python
@property
def available(self) -> bool:
    # 1. 检查是否有认证数据
    if not self.auth_data:
        return False

    # 2. 检查必要字段是否存在
    required_keys = ["ua", "ssecurity", "userId", "cUserId", "serviceToken"]
    if any(key not in self.auth_data for key in required_keys):
        return False

    # 3. 60秒缓存检查（避免频繁请求）
    current_time = int(time.time())
    if current_time - self._available_cache_time < 60:
        return self._available_cache

    # 4. 实际检查：调用 check_new_msg()
    try:
        self.check_new_msg(refresh_token=False)
    except Exception:
        self._available_cache = None
        return False

    self._available_cache = True
    return True
```

## 四、Session 初始化

### 4.1 Cookie 结构

```python
# _init_session() 设置的 Cookie
Cookie = {
    "cUserId": auth_data["cUserId"],
    "yetAnotherServiceToken": auth_data["serviceToken"],
    "serviceToken": auth_data["serviceToken"],
    "timezone_id": "Asia/Shanghai",          # 本地时区
    "timezone": "GMT+08:00",                # UTC偏移
    "is_daylight": "0",                      # 夏令时
    "dst_offset": "0",                       # 夏令时偏移
    "channel": "MI_APP_STORE",
    "countryCode": "CN",
    "PassportDeviceId": deviceId,
    "locale": "zh_CN",
}
```

### 4.2 请求头

```python
headers = {
    "User-Agent": "Android-15-11.0.701-Xiaomi-...",
    "accept-encoding": "identity",
    "Content-Type": "application/x-www-form-urlencoded",
    "miot-accept-encoding": "GZIP",
    "miot-encrypt-algorithm": "ENCRYPT-RC4",
    "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
}
```

## 五、多账号场景

### 5.1 不同认证路径

```python
# 账号A
api_a = miiotpcAPI(auth_data_path="/path/to/account_a.json")
api_a.login()

# 账号B（独立认证数据）
api_b = miiotpcAPI(auth_data_path="/path/to/account_b.json")
api_b.login()

# 两个账号的认证数据互不影响
```

### 5.2 认证文件独立性

每个 auth.json 文件包含完整的认证状态，包括：
- 所有必要的 token 和密钥
- UA 和 deviceId（用于标识客户端）
- 保存时间和过期时间

## 六、错误场景

### 6.1 认证文件损坏

```python
try:
    api = miiotpcAPI()
except json.JSONDecodeError:
    # auth.json 不是有效的 JSON
    # 处理: 删除损坏文件，重新登录
    Path(api.auth_data_path).unlink(missing_ok=True)
    api = miiotpcAPI()
    api.login()
```

### 6.2 Token 过期且刷新失败

```python
try:
    devices = api.get_devices_list()
except LoginError:
    # Token 过期，_refresh_token() 失败
    # 处理: 重新登录
    api.login()
    devices = api.get_devices_list()
```

### 6.3 网络错误

```python
try:
    devices = api.get_devices_list()
except APIError as e:
    code, message = e.args
    if code == -10007:
        # 设备离线
        pass
    elif "网络" in str(message):
        # 网络错误
        pass
```

## 七、安全注意事项

1. **auth.json 包含敏感信息**：不要提交到版本控制
2. **ssecurity 是会话密钥**：泄露会导致账号被冒用
3. **Token 有效期约30天**：过期后需要重新登录
4. **建议定期清理**：删除不再使用的认证文件
5. **多设备登录**：小米允许同时多个设备登录，不会互踢
