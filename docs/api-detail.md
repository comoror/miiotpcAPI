# api.py 详细实现规格

> 从 mijiaAPI/apis.py 精简而来的核心 API 客户端，逐方法说明

## 一、类初始化

### `miiotpcAPI.__init__(self, auth_data_path=None)`

```python
class miiotpcAPI:
    def __init__(self, auth_data_path: Optional[str] = None):
        self.locale = locale.getlocale()[0] if locale.getlocale()[0] else "zh_CN"
        if '_' not in self.locale:
            self.locale = "zh_CN"
        self.api_base_url = "https://api.mijia.tech/app"
        self.login_url = "https://account.xiaomi.com/longPolling/loginUrl"
        self.service_login_url = (
            f"https://account.xiaomi.com/pass/serviceLogin"
            f"?_json=true&sid=mijia&_locale={self.locale}"
        )

        # 默认路径: ~/.config/miiotpc-api/auth.json
        if auth_data_path is None:
            self.auth_data_path = Path.home() / ".config" / "miiotpc-api" / "auth.json"
        elif Path(auth_data_path).is_dir():
            self.auth_data_path = Path(auth_data_path) / "auth.json"
        else:
            self.auth_data_path = Path(auth_data_path)

        self._available_cache = None
        self._available_cache_time = 0

        if self.auth_data_path.exists():
            with open(self.auth_data_path, "r") as f:
                self.auth_data = json.load(f)
            self._init_session()
        else:
            self.auth_data = {}
```

**改动点：**
- 默认路径 `~/.config/mijia-api/` → `~/.config/miiotpc-api/`
- 其余逻辑完全不变

---

## 二、Session 管理（原样保留）

### `_init_session(self)`

完全复制原版。设置 requests.Session 的 headers，包含：
- User-Agent（模拟 Android 15 设备）
- RC4 加密相关 headers
- Cookie（cUserId, serviceToken, timezone 等）

```python
def _init_session(self):
    self.session = requests.Session()
    self.session.headers.update({
        "User-Agent": self.user_agent,
        "accept-encoding": "identity",
        "Content-Type": "application/x-www-form-urlencoded",
        "miot-accept-encoding": "GZIP",
        "miot-encrypt-algorithm": "ENCRYPT-RC4",
        "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
        "Cookie": f"cUserId={self.auth_data['cUserId']};"
                  f"yetAnotherServiceToken={self.auth_data['serviceToken']};"
                  f"serviceToken={self.auth_data['serviceToken']};"
                  f"timezone_id={tzlocal.get_localzone_name()};"
                  f"timezone=GMT{datetime.now().astimezone().strftime('%z')[:3]}:"
                  f"{datetime.now().astimezone().strftime('%z')[3:]};"
                  f"is_daylight={time.daylight};"
                  f"dst_offset={time.localtime().tm_isdst * 60 * 60 * 1000};"
                  f"channel=MI_APP_STORE;"
                  f"countryCode={self.locale.split('_')[1] if self.locale else 'CN'};"
                  f"PassportDeviceId={self.deviceId};"
                  f"locale={self.locale}",
    })
```

### 属性方法（原样保留）

| 属性 | 说明 |
|------|------|
| `available` | 检查认证是否有效（60秒缓存） |
| `pass_o` | 16位随机 hex 字符串 |
| `user_agent` | 模拟小米 Android 设备的 UA 字符串 |
| `deviceId` | 16位随机设备标识 |

---

## 三、登录流程（原样保留）

### `login(self) → dict` / `QRlogin(self) → dict`

入口方法，先尝试刷新 token，失败则走二维码流程。

### `_get_qr_login_data(self) → dict`

获取二维码数据，不阻塞。返回：
```python
{
    "refreshed": True,  # 如果 token 刷新成功
    # 或
    "loginUrl": "https://...",  # 二维码原始链接
    "qr": "https://...",        # 二维码图片链接
    "lp": "https://...",        # 长轮询地址
}
```

### `_complete_qr_login(self, login_data: dict) → dict`

长轮询等待扫码（120秒超时），完成登录，保存认证数据。

### `_print_qr(loginurl, box_size=10)` [静态方法]

在终端打印 ASCII 二维码。

### `_save_auth_data(self)`

保存认证数据到 JSON 文件，添加 `saveTime` 字段。

### `_get_location(self) → dict`

Token 刷新的核心方法。访问 `account.xiaomi.com/pass/serviceLogin` 获取新的 serviceToken。

### `_refresh_token(self) → dict`

如果 `available` 为 False，调用 `_get_location()` 刷新 token。

### `check_new_msg(self, begin_at=None, refresh_token=True) → dict`

调用 `/v2/message/v2/check_new_msg`。在 `available` 属性中用于检测 token 是否有效。

---

## 四、加密请求（原样保留）

### `_request(self, uri, data, refresh_token=True) → dict`

核心请求方法。流程：
1. 刷新 token（可选）
2. 拼接 URL：`api_base_url + uri`
3. JSON 序列化 data
4. 生成 nonce → signed_nonce
5. RC4 加密参数 + HMAC-SHA1 签名
6. POST 请求
7. 解析响应（可能需要 RC4 解密）
8. 检查 code != 0 则抛出 APIError

```python
def _request(self, uri: str, data: dict, refresh_token: bool = True) -> dict:
    logger.debug(f"请求 URI: {uri}，数据: {data}")
    if refresh_token:
        self._refresh_token()
    url = self.api_base_url + uri
    params = {"data": json.dumps(data, separators=(',', ':'))}
    nonce = gen_nonce()
    signed_nonce = get_signed_nonce(self.auth_data["ssecurity"], nonce)
    params = generate_enc_params(
        uri, "POST", signed_nonce, nonce, params, self.auth_data["ssecurity"]
    )
    ret = self.session.post(url, data=params)
    try:
        ret_data = json.loads(ret.text)
    except json.JSONDecodeError:
        dec_data = decrypt(self.auth_data["ssecurity"], nonce, ret.text)
        ret_data = json.loads(dec_data)
    logger.debug(f"响应数据: {ret_data}")
    if ret_data.get("code", 0) != 0 or "result" not in ret_data:
        raise APIError(
            ret_data["code"],
            ret_data.get("message", ret_data.get("desc", "未知错误"))
        )
    return ret_data["result"]
```

---

## 五、设备列表（精简）

### `_get_all_devices(self) → list` [新增内部方法]

原版通过 `get_homes_list()` → 遍历每个 home → `_get_devices_list(home_id)` 获取设备。

精简版直接使用共享设备接口获取全部设备（已包含主设备）：

```python
def _get_all_devices(self) -> list:
    """获取所有设备（通过共享设备接口，返回结果已包含主设备）"""
    uri = "/v2/home/device_list_page"
    data = {
        "ssid": "<unknown ssid>",
        "bssid": "02:00:00:00:00:00",
        "getVirtualModel": True,
        "getHuamiDevices": 1,
        "get_split_device": True,
        "support_smart_home": True,
        "get_cariot_device": True,
        "get_third_device": True,
        "get_phone_device": True,
        "get_miwear_device": True,
    }
    ret = self._request(uri, data)
    return ret.get("list", [])
```

> **注意**：如果此接口不能获取全部设备，需要回退到原版方案（保留 `get_homes_list()` + `_get_devices_list()`）。实际测试时验证。

### `get_devices_list(self) → list`

```python
def get_devices_list(self) -> list:
    """获取所有设备列表（含共享设备）"""
    return self._get_all_devices()
```

### `get_shared_devices_list(self) → list`

保留原版逻辑，但简化返回：

```python
def get_shared_devices_list(self) -> list:
    """获取共享设备列表"""
    uri = "/v2/home/device_list_page"
    data = {
        "ssid": "<unknown ssid>",
        "bssid": "02:00:00:00:00:00",
        "getVirtualModel": True,
        "getHuamiDevices": 1,
        "get_split_device": True,
        "support_smart_home": True,
        "get_cariot_device": True,
        "get_third_device": True,
        "get_phone_device": True,
        "get_miwear_device": True,
    }
    ret = self._request(uri, data)
    devices = [item for item in ret["list"] if item.get("owner", False)]
    for device in devices:
        device.update({"home_id": "shared"})
    return devices
```

### `find_pc_devices(self, keyword=None) → list` [新增]

```python
def find_pc_devices(self, keyword: Optional[str] = None) -> list:
    """筛选PC/笔记本相关设备

    通过设备名称或 model 关键词过滤。
    默认匹配关键词: pc, 电脑, 笔记本, laptop, desktop, notebook

    参数:
        keyword: 额外的自定义关键词

    返回:
        list: 匹配的设备信息列表
    """
    devices = self.get_devices_list()
    pc_keywords = {"pc", "电脑", "笔记本", "laptop", "desktop", "notebook"}
    if keyword:
        pc_keywords.add(keyword.lower())

    results = []
    for device in devices:
        name_lower = device.get("name", "").lower()
        model_lower = device.get("model", "").lower()
        if any(kw in name_lower or kw in model_lower for kw in pc_keywords):
            results.append(device)
    return results
```

---

## 六、属性读写（原样保留）

### `get_devices_prop(self, data) → Union[list, dict]`

```python
def get_devices_prop(self, data: Union[list, dict]) -> Union[list, dict]:
    """获取设备属性

    参数:
        data: dict 单个属性 / list 批量属性
              每个元素: {"did": "...", "siid": int, "piid": int}

    返回:
        dict/list: {"did", "siid", "piid", "value", "code", "updateTime"}
    """
    if isinstance(data, dict):
        params = [data]
    else:
        params = data
    uri = "/miotspec/prop/get"
    ret_data = self._request(uri, {"params": params, "datasource": 1})
    if isinstance(data, dict) and len(ret_data) == 1:
        return ret_data[0]
    return ret_data
```

### `set_devices_prop(self, data) → Union[list, dict]`

```python
def set_devices_prop(self, data: Union[list, dict]) -> Union[list, dict]:
    """设置设备属性

    参数:
        data: dict 单个属性 / list 批量属性
              每个元素: {"did", "siid", "piid", "value"}

    返回:
        dict/list: {"did", "siid", "piid", "code", "message"}
    """
    if isinstance(data, dict):
        params = [data]
    else:
        params = data
    uri = "/miotspec/prop/set"
    ret_data = self._request(uri, {"params": params})
    for ret in ret_data:
        if ret.get("code", 0) not in (0, 1):
            ret.update({"message": ERROR_CODE.get(str(ret["code"]), "未知错误")})
        else:
            ret.update({"message": "成功"})
    if isinstance(data, dict) and len(ret_data) == 1:
        return ret_data[0]
    return ret_data
```

### `run_action(self, data) → Union[list, dict]`

```python
def run_action(self, data: Union[list, dict]) -> Union[list, dict]:
    """执行设备动作

    参数:
        data: dict 单个动作 / list 批量动作
              每个元素: {"did", "siid", "aiid", "value"(可选)}

    返回:
        dict/list: {"did", "siid", "aiid", "code", "message"}
    """
    if isinstance(data, dict):
        params = [data]
    else:
        params = data
    uri = "/miotspec/action"
    ret_data = []
    for param in params:
        ret = self._request(uri, {"params": param})
        ret_data.append(ret)
    for ret in ret_data:
        if ret.get("code", 0) not in (0, 1):
            ret.update({"message": ERROR_CODE.get(str(ret["code"]), "未知错误")})
        else:
            ret.update({"message": "成功"})
    if isinstance(data, dict) and len(ret_data) == 1:
        return ret_data[0]
    return ret_data
```

---

## 七、移除的方法清单

以下方法**不包含**在 `miiotpcApi` 中：

| 方法 | 原文件位置 | 移除原因 |
|------|-----------|---------|
| `get_homes_list()` | apis.py:404 | 家庭管理非PC核心 |
| `_get_devices_list(home_id)` | apis.py:351 | 简化设备获取方式 |
| `_get_home_owner(home_id)` | apis.py:344 | 家庭管理辅助 |
| `_add_home_id(data, home_id)` | apis.py:333 | 家庭管理辅助 |
| `_get_scenes_list(home_id)` | apis.py:376 | 场景管理 |
| `get_scenes_list(home_id)` | apis.py:487 | 场景管理 |
| `run_scene(scene_id, home_id)` | apis.py:517 | 场景管理 |
| `_get_consumable_items(home_id)` | apis.py:385 | 耗材管理 |
| `get_consumable_items(home_id)` | apis.py:539 | 耗材管理 |
| `get_statistics(data)` | apis.py:782 | 统计功能 |

---

## 八、错误处理

API 级错误通过 `APIError` 抛出，错误码映射见 `errors.py`。

关键错误码（PC 设备可能遇到的）：

| 错误码 | 含义 | 场景 |
|--------|------|------|
| `-704042011` | 设备离线 | PC 关机后尝试操作 |
| `-704053036` | 设备操作超时 | PC 响应慢 |
| `-704053100` | 设备在当前状态下无法执行此操作 | 重复开关机 |
| `-704040003` | Property不存在 | 设备不支持某属性 |
| `-704040005` | Action不存在 | 设备不支持某动作 |
| `-704030013` | Property不可读 | 尝试读取只写属性 |
| `-704030023` | Property不可写 | 尝试写入只读属性 |
