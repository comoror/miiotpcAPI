# 常见问题排查

## 认证相关

### Q: 运行 `miiotpcApi login` 无反应

**可能原因：**
1. 网络连接问题
2. 小米服务器不可达

**排查步骤：**
```bash
# 测试网络连通性
curl -I https://account.xiaomi.com

# 使用 DEBUG 日志查看详细信息
MIIOTPC_LOG_LEVEL=DEBUG miiotpcApi login
```

**解决方案：**
- 检查网络连接
- 尝试使用代理
- 确认小米服务器是否在维护

---

### Q: 扫码后提示 "登录超时"

**可能原因：**
1. 未在 120 秒内完成扫码
2. 米家 APP 版本过旧

**排查步骤：**
```bash
# 重新登录
miiotpcApi login
# 立即扫码，不要等待
```

**解决方案：**
- 确保在 120 秒内完成扫码
- 更新米家 APP 到最新版本
- 确保米家 APP 已登录小米账号

---

### Q: 提示 "认证已失效且刷新失败"

**可能原因：**
1. Token 过期超过 30 天
2. 账号被修改或注销

**排查步骤：**
```bash
# 检查认证文件
cat ~/.config/miiotpc-api/auth.json

# 重新登录
miiotpcApi login
```

**解决方案：**
- 重新运行 `miiotpcApi login` 扫码登录
- 如持续失败，删除认证文件后重试：
  ```bash
  rm ~/.config/miiotpc-api/auth.json
  miiotpcApi login
  ```

---

### Q: 认证文件损坏 (JSON 解析错误)

**可能原因：**
1. 手动编辑了 auth.json
2. 写入过程中断电

**解决方案：**
```bash
# 删除损坏的文件
rm ~/.config/miiotpc-api/auth.json

# 重新登录
miiotpcApi login
```

---

## 设备相关

### Q: 设备列表为空

**可能原因：**
1. 米家 APP 中未添加设备
2. 设备未绑定到当前账号
3. 网络问题

**排查步骤：**
```bash
# 检查认证状态
miiotpcApi -l  # 应该显示设备列表

# 使用 DEBUG 查看请求详情
MIIOTPC_LOG_LEVEL=DEBUG miiotpcApi -l
```

**解决方案：**
- 确认米家 APP 中已添加设备
- 确认设备已绑定到当前小米账号
- 检查网络连接

---

### Q: 提示 "未找到设备"

**可能原因：**
1. 设备名称拼写错误
2. 设备已被删除或解绑

**排查步骤：**
```bash
# 列出所有设备
miiotpcApi -l

# 使用 did 而非名称
miiotpcApi --did "123456789" --status
```

**解决方案：**
- 使用 `miiotpcApi -l` 确认设备名称
- 尝试使用 did（设备ID）指定设备
- 在米家 APP 中检查设备状态

---

### Q: 提示 "找到多个同名设备"

**可能原因：**
1. 多个设备使用相同名称

**解决方案：**
```bash
# 使用 did 精确指定
miiotpcApi --did "123456789" --power on

# 或在米家 APP 中修改设备名称
```

---

### Q: 设备显示离线

**可能原因：**
1. 设备断电或断网
2. 设备固件问题
3. 网络延迟

**排查步骤：**
```bash
# 检查设备状态
miiotpcApi --dev_name "我的笔记本" --status

# 查看设备详细信息
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 确认设备已通电且网络正常
- 在米家 APP 中检查设备状态
- 重启设备或路由器

---

## 属性操作相关

### Q: 提示 "属性不可读" 或 "属性不可写"

**可能原因：**
1. 设备不支持该属性的读/写操作

**排查步骤：**
```bash
# 查看设备支持的属性
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 检查属性的 `rw` 字段：`r`=只读, `w`=只写, `rw`=读写
- 使用支持的操作

---

### Q: 提示 "值超出范围"

**可能原因：**
1. 设置的值不在属性允许的范围内

**排查步骤：**
```bash
# 查看属性的范围
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 检查属性的 `range` 字段：`[min, max, step]`
- 确保值在范围内且符合步长要求

---

### Q: 提示 "无效值"（枚举值错误）

**可能原因：**
1. 设置的值不在属性的枚举值列表中

**排查步骤：**
```bash
# 查看属性的枚举值
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 检查属性的 `value-list` 字段
- 使用枚举值列表中的值

---

## 动作执行相关

### Q: 提示 "Action不存在"

**可能原因：**
1. 设备不支持该动作

**排查步骤：**
```bash
# 查看设备支持的动作
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 使用设备支持的动作名
- 检查动作名拼写

---

### Q: 提示 "设备在当前状态下无法执行此操作"

**可能原因：**
1. 设备当前状态不允许执行该动作（如已开机时再次开机）

**解决方案：**
- 检查设备当前状态
- 根据当前状态选择 `power_on()`、`sleep()` 或 `power_off()`

---

## PCDevice 相关

### Q: 提示 "设备不支持 XX 操作"

**可能原因：**
1. 设备的 MIoT Spec 中没有对应的属性或动作
2. 能力检测关键词未匹配

**排查步骤：**
```bash
# 查看设备支持的能力
miiotpcApi --dev_name "我的笔记本" --status

# 查看完整规格
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
- 使用 `--status` 查看设备支持的能力
- 如需自定义关键词匹配，修改 `device.py` 中的 PCDevice 类属性

---

### Q: 能力检测未识别到我的设备

**可能原因：**
1. 设备属性/动作名不在默认关键词列表中

**排查步骤：**
```bash
# 查看设备的完整属性和动作
miiotpcApi --get_device_info <MODEL>
```

**解决方案：**
修改 `device.py` 中的 PCDevice 类，添加自定义关键词：

```python
class PCDevice:
    _POWER_PROPS = {"on", "power", "switch", "power-status", "your-custom-keyword"}
    # 添加你的设备属性名
```

---

## CLI 相关

### Q: 命令无响应或卡住

**可能原因：**
1. 网络请求超时

**解决方案：**
- 使用 `Ctrl+C` 中断
- 检查网络连接
- 使用 DEBUG 日志查看详情：
  ```bash
  MIIOTPC_LOG_LEVEL=DEBUG miiotpcApi --dev_name "..." --status
  ```

---

### Q: 提示 "命令未找到"

**可能原因：**
1. 未安装或未在 PATH 中

**解决方案：**
```bash
# 确认安装
cd e:\Work.py\miiotpcApi
uv sync

# 使用 uv run 运行
uv run miiotpcApi login

# 或添加到 PATH
export PATH="$PWD/.venv/bin:$PATH"
miiotpcApi login
```

---

### Q: Python 版本不兼容

**可能原因：**
1. Python 版本低于 3.10

**解决方案：**
```bash
# 检查 Python 版本
python --version

# 安装 Python 3.10+
# Windows: 从 python.org 下载
# macOS: brew install python@3.12
# Linux: apt install python3.12
```

---

## 日志调试

### 如何开启 DEBUG 日志

```bash
# Linux/macOS
export MIIOTPC_LOG_LEVEL=DEBUG
miiotpcApi --dev_name "..." --status

# Windows PowerShell
$env:MIIOTPC_LOG_LEVEL = "DEBUG"
miiotpcApi --dev_name "..." --status

# 单次运行
MIIOTPC_LOG_LEVEL=DEBUG miiotpcApi --dev_name "..." --status
```

### 日志输出示例

```
# INFO 级别（默认）
2024-01-01 12:00:00.000 - miiotpcApi - INFO: 登录成功
2024-01-01 12:00:01.000 - miiotpcApi - INFO: 获取属性: 我的笔记本 -> on, 结果: {...}

# DEBUG 级别
2024-01-01 12:00:00.000 - miiotpcApi - DEBUG: 请求 URI: /miotspec/prop/get，数据: {...}
2024-01-01 12:00:00.500 - miiotpcApi - DEBUG: 响应数据: {...}
2024-01-01 12:00:01.000 - miiotpcApi - DEBUG: 获取属性: 我的笔记本 -> on, 结果: {...}
```

---

## 获取帮助

如以上方案均无法解决问题：

1. 查看 [错误码参考](error-handling.md) 了解错误码含义
2. 开启 DEBUG 日志查看详细请求/响应
3. 检查 [协议参考](protocol.md) 了解底层通信细节
4. 在 GitHub Issues 中搜索或提交问题
