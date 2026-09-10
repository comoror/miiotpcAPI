# 错误处理参考

## 异常类

所有异常定义在 `errors.py` 中：

| 异常类 | 说明 | 常见触发场景 |
|--------|------|-------------|
| `LoginError(code, message)` | 认证失败 | Token 过期且刷新失败、扫码超时 |
| `APIError(code, message)` | API 请求失败 | 网络错误、服务端异常 |
| `DeviceNotFoundError(did)` | 设备未找到 | did/name 不存在 |
| `MultipleDevicesFoundError(message)` | 找到多个同名设备 | 需用 did 精确指定 |
| `DeviceGetError(dev_name, name, code)` | 获取属性失败 | 设备离线、属性不可读 |
| `DeviceSetError(dev_name, name, code)` | 设置属性失败 | 设备离线、值超出范围 |
| `DeviceActionError(dev_name, name, code)` | 执行动作失败 | 设备离线、动作不存在 |
| `GetDeviceInfoError(model)` | 获取MIoT Spec失败 | 网络错误、model不正确 |

## 错误码参考

以下是小米 IoT 平台常见的错误码（定义在 `errors.py` 的 `ERROR_CODE` 字典中）：

### 通用错误

| 错误码 | 含义 | PC场景说明 |
|--------|------|-----------|
| `-10000` | 未知错误 | |
| `-10005` | 权限不足 | 设备未授权 |
| `-10006` | 执行超时 | 请求超时 |
| `-10007` | 设备离线或不存在 | PC关机/断网 |

### 设备相关

| 错误码 | 含义 | PC场景说明 |
|--------|------|-----------|
| `-704042011` | 设备离线 | PC关机或断网 |
| `-704053036` | 设备操作超时 | PC响应慢 |
| `-704053100` | 设备在当前状态下无法执行此操作 | 重复开关机 |
| `-704042001` | Device不存在 | did 错误 |

### 属性相关

| 错误码 | 含义 | PC场景说明 |
|--------|------|-----------|
| `-704030013` | Property不可读 | 尝试读取只写属性 |
| `-704030023` | Property不可写 | 尝试写入只读属性 |
| `-704040003` | Property不存在 | 设备不支持该属性 |
| `-704220043` | Property值错误 | 值超出范围或类型错误 |

### 动作相关

| 错误码 | 含义 | PC场景说明 |
|--------|------|-----------|
| `-704040005` | Action不存在 | 设备不支持该动作 |
| `-704220025` | Action参数个数不匹配 | 参数缺失 |
| `-704220035` | Action参数错误 | 参数值无效 |

## 错误处理示例

### Python 代码中的错误处理

```python
from miiotpcApi import (
    miiotpcAPI, PCDevice,
    LoginError, APIError,
    DeviceNotFoundError, DeviceGetError, DeviceSetError,
)

api = miiotpcAPI()

# 认证错误处理
try:
    api.login()
except LoginError as e:
    print(f"登录失败: {e}")
    print("请检查网络连接或重新扫码")

# 设备操作错误处理
try:
    pc = PCDevice(api, dev_name="我的笔记本")
    pc.power_on()
except DeviceNotFoundError:
    print("未找到设备，请检查设备名称")
except DeviceSetError as e:
    print(f"设置失败: {e}")
    # 错误码在 e.args 中，可访问
except APIError as e:
    code, message = e.args
    print(f"API错误 [{code}]: {message}")
```

### 获取错误码详情

```python
from miiotpcApi.errors import ERROR_CODE

# 将错误码转为中文描述
code = -704042011
desc = ERROR_CODE.get(str(code), "未知错误")
print(f"错误 {code}: {desc}")  # 错误 -704042011: 设备离线
```

## 常见问题排查

### 设备离线 (`-704042011`)

**原因**：PC 关机、断网、或米家 APP 未连接

**排查步骤**：
1. 确认 PC 已开机且网络正常
2. 在米家 APP 中检查设备是否显示在线
3. 检查 PC 是否安装了米家设备客户端

### 属性不可读/不可写 (`-704030013` / `-704030023`)

**原因**：设备不支持该属性的读/写操作

**排查步骤**：
1. 运行 `miiotpcApi --get_device_info <model>` 查看属性权限
2. 确认属性的 `rw` 字段包含 `r`（读）或 `w`（写）

### 操作超时 (`-704053036`)

**原因**：设备响应慢或网络延迟

**排查步骤**：
1. 检查网络连接
2. 尝试增加 sleep_time（MiotDevice 构造函数参数）
3. 确认设备未处于高负载状态
