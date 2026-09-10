# 快速开始指南

## 安装

```bash
# 开发模式安装（推荐）
cd e:\Work.py\miiotpcApi
uv sync

# 或者 pip 安装
pip install -e .
```

## 首次登录

```bash
# 启动登录流程
miiotpcApi login

# 终端会显示二维码，用米家APP扫码
# 扫码成功后认证数据保存到 ~/.config/miiotpc-api/auth.json
```

## 查看设备

```bash
# 列出所有米家设备
miiotpcApi -l

# 仅列出PC/笔记本设备
miiotpcApi --list_pc

# 查看某个设备的MIoT Spec（确认支持哪些属性和动作）
miiotpcApi --get_device_info xiaomi.pc.v1
```

## PC 控制

```bash
# 查看PC状态
miiotpcApi --dev_name "我的笔记本" --status

# 开机
miiotpcApi --dev_name "我的笔记本" --power on

# 关机
miiotpcApi --dev_name "我的笔记本" --power off

# 睡眠
miiotpcApi --dev_name "我的笔记本" --power sleep

# 唤醒
miiotpcApi --dev_name "我的笔记本" --wake

# 锁屏
miiotpcApi --dev_name "我的笔记本" --lock
```

## Python 代码调用

```python
from miiotpcApi import miiotpcAPI, PCDevice, MiotDevice

# 初始化 API
api = miiotpcAPI()
api.login()  # 首次需要扫码

# 高层 PCDevice 接口
pc = PCDevice(api, dev_name="我的笔记本")
print(pc.status)          # 查看状态
pc.power_on()             # 开机
pc.set_brightness(80)     # 设置亮度

# 底层 MiotDevice 接口（通用）
device = MiotDevice(api, dev_name="我的笔记本")
print(device.get("on"))   # 读取属性
device.set("on", True)    # 设置属性
device.run_action("reboot")  # 执行动作
```

## 认证说明

- 认证文件默认保存在 `~/.config/miiotpc-api/auth.json`
- Token 有效期约 30 天，过期后自动刷新
- 如刷新失败，需要重新 `miiotpcApi login` 扫码

## 常见问题

**Q: 设备列表中找不到我的PC**
A: 确认设备名称中包含 "PC"、"电脑"、"笔记本" 等关键词。可以在米家APP中修改设备名称。

**Q: 提示 "设备不支持 XX 操作"**
A: 运行 `miiotpcApi --get_device_info <model>` 查看设备支持的属性和动作。

**Q: 认证失败**
A: 运行 `miiotpcApi login` 重新扫码登录。
