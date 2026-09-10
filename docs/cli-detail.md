# __main__.py 详细实现规格

> CLI 入口，从 mijiaAPI/__main__.py 精简而来

## 一、模块结构

```python
"""miiotpcApi.__main__ - CLI 入口

子命令:
    login   二维码登录米家账号
    get     获取设备属性
    set     设置设备属性
    action  执行设备动作
    pc      PC设备控制

选项:
    -l, --list_devices     列出所有设备
    --list_pc              仅列出PC/笔记本设备
    --get_device_info MODEL 获取设备MIoT Spec
"""
```

---

## 二、argparse 参数定义

### 2.1 顶级参数

```python
parser = argparse.ArgumentParser(description=f"miiotpcApi PC设备控制 CLI (v{version})")

# 全局选项
parser.add_argument(
    '-v', '--version',
    action='version',
    version=f"%(prog)s {version}",
)
parser.add_argument(
    '-p', '--auth_path',
    type=Path,
    default=Path.home() / ".config" / "miiotpc-api" / "auth.json",
    help="认证文件路径，默认 ~/.config/miiotpc-api/auth.json",
)
parser.add_argument(
    '-l', '--list_devices',
    action='store_true',
    help="列出所有米家设备",
)
parser.add_argument(
    '--list_pc',
    action='store_true',
    help="仅列出PC/笔记本设备",
)
parser.add_argument(
    '--get_device_info',
    type=str,
    metavar='MODEL',
    help="获取设备MIoT Spec信息，如 'xiaomi.pc.v1'",
)
```

### 2.2 login 子命令

```python
login_cmd = subparsers.add_parser('login', help="二维码登录米家账号")
login_cmd.set_defaults(func='login')
login_cmd.add_argument(
    '-p', '--auth_path',
    type=Path,
    default=Path.home() / ".config" / "miiotpc-api" / "auth.json",
)
```

### 2.3 get 子命令

```python
get_cmd = subparsers.add_parser('get', help="获取设备属性")
get_cmd.set_defaults(func='get')
get_cmd.add_argument('-p', '--auth_path', type=Path, default=...)
get_cmd.add_argument('--did', type=str, help="设备did")
get_cmd.add_argument('--dev_name', type=str, help="设备名称")
get_cmd.add_argument('--prop_name', type=str, required=True, help="属性名")
```

### 2.4 set 子命令

```python
set_cmd = subparsers.add_parser('set', help="设置设备属性")
set_cmd.set_defaults(func='set')
set_cmd.add_argument('-p', '--auth_path', type=Path, default=...)
set_cmd.add_argument('--did', type=str)
set_cmd.add_argument('--dev_name', type=str)
set_cmd.add_argument('--prop_name', type=str, required=True)
set_cmd.add_argument('--value', type=str, required=True)
```

### 2.5 action 子命令

```python
action_cmd = subparsers.add_parser('action', help="执行设备动作")
action_cmd.set_defaults(func='action')
action_cmd.add_argument('-p', '--auth_path', type=Path, default=...)
action_device = action_cmd.add_mutually_exclusive_group(required=True)
action_device.add_argument('--did', type=str)
action_device.add_argument('--dev_name', type=str)
action_cmd.add_argument('--action_name', type=str, required=True)
action_cmd.add_argument(
    '--params', type=json_object,
    help='动作参数JSON对象，如 {"value":[2]}',
    default=None,
)
```

### 2.6 顶层 PC 控制选项

PC 控制是本工具的默认操作，不使用额外的 `pc` 子命令。以下选项直接添加到顶层 parser：

```python
add_device_arguments(parser, required=False)
pc_action = parser.add_mutually_exclusive_group()
pc_action.add_argument('--power', choices=['on', 'sleep', 'off'], help="电源操作")
pc_action.add_argument('--sleep', action='store_true', help="睡眠")
pc_action.add_argument('--wake', action='store_true', help="唤醒")
pc_action.add_argument('--lock', action='store_true', help="锁屏")
pc_action.add_argument('--brightness', type=int, metavar='N', help="设置亮度(0-100)")
pc_action.add_argument('--get-brightness', action='store_true', help="获取亮度")
pc_action.add_argument('--volume', type=int, metavar='N', help="设置音量(0-100)")
pc_action.add_argument('--get-volume', action='store_true', help="获取音量")
pc_action.add_argument('--status', action='store_true', help="获取状态概览")
```

使用 `--list-pc` 列出 PC/笔记本设备。

---

## 三、辅助函数

### 3.1 `json_object(value)`

```python
def json_object(value: str) -> dict:
    """解析 JSON 字符串参数"""
    try:
        result = json.loads(value)
    except json.JSONDecodeError as e:
        raise argparse.ArgumentTypeError(f"无效 JSON: {e.msg}") from e
    if not isinstance(result, dict):
        raise argparse.ArgumentTypeError("必须是 JSON 对象")
    return result
```

### 3.2 `init_api(auth_path)`

```python
def init_api(auth_path: Path) -> miiotpcAPI:
    """初始化 API 客户端，检查认证状态"""
    if Path(auth_path).is_dir():
        auth_path = auth_path / "auth.json"
    if not auth_path.exists():
        print(f"认证文件不存在: {auth_path}")
        print("请运行 'miiotpcApi login' 扫码登录")
        sys.exit(1)
    try:
        api = miiotpcAPI(auth_data_path=auth_path)
    except json.JSONDecodeError:
        print(f"认证文件已损坏: {auth_path}")
        print("请运行 'miiotpcApi login' 重新登录")
        sys.exit(1)
    if not api.available:
        try:
            api._refresh_token()
        except Exception:
            pass
        if not api.available:
            print(f"认证已失效且刷新失败: {auth_path}")
            print("请运行 'miiotpcApi login' 重新登录")
            sys.exit(1)
    return api
```

### 3.3 `get_devices_list(api, verbose)`

```python
def get_devices_list(api: miiotpcAPI, verbose: bool = True) -> dict:
    """获取设备列表并可选打印"""
    devices = api.get_devices_list()
    if verbose:
        print("设备列表:")
        for device in devices:
            online = "在线" if device.get("isOnline") else "离线"
            print(f"  - {device['name']}")
            print(f"    did: {device['did']}")
            print(f"    model: {device['model']}")
            print(f"    状态: {online}")
    return {device['did']: device for device in devices}
```

### 3.4 `get_pc_devices(api, verbose)`

```python
def get_pc_devices(api: miiotpcAPI, verbose: bool = True) -> list:
    """获取PC/笔记本设备列表"""
    devices = api.find_pc_devices()
    if verbose:
        if not devices:
            print("未找到PC/笔记本设备。请确认设备名称中包含 'PC'、'电脑'、'笔记本' 等关键词。")
            return devices
        print("PC/笔记本设备列表:")
        for device in devices:
            online = "在线" if device.get("isOnline") else "离线"
            print(f"  - {device['name']}")
            print(f"    did: {device['did']}")
            print(f"    model: {device['model']}")
            print(f"    状态: {online}")
    return devices
```

### 3.5 `pc_action_handler(api, args)`

```python
def pc_action_handler(api: miiotpcAPI, args) -> None:
    """处理顶层 PC 控制选项"""
    # --list：列出PC设备
    if args.list:
        get_pc_devices(api)
        return

    # 解析设备标识
    did = getattr(args, 'did', None)
    dev_name = getattr(args, 'dev_name', None)
    if did is None and dev_name is None:
        print("错误: 必须指定 --did 或 --dev_name 参数")
        print("示例: miiotpcApi --dev_name '我的笔记本' --power on")
        return

    # 创建 PCDevice
    pc = PCDevice(api, did=did, dev_name=dev_name)

    # --status：状态概览
    if args.status:
        print(f"设备: {pc.name} ({pc.model})")
        print(f"  did: {pc.did}")
        status = pc.status
        print(f"  支持的能力: {status['capabilities']}")
        for key, value in status.items():
            if key in ('name', 'model', 'did', 'capabilities'):
                continue
            print(f"  {key}: {value}")
        return

    # --power on/sleep/off
    if args.power:
        if args.power == 'on':
            pc.power_on()
            print(f"{pc.name} 已开机")
        elif args.power == 'off':
            pc.power_off()
            print(f"{pc.name} 已关机")
        elif args.power == 'toggle':
            pc.sleep()
            print(f"{pc.name} 已进入睡眠")
        return

    # --sleep
    if args.sleep:
        pc.sleep()
        print(f"{pc.name} 已进入睡眠")
        return

    # --wake
    if args.wake:
        pc.wake()
        print(f"{pc.name} 已唤醒")
        return

    # --lock
    if args.lock:
        pc.lock_screen()
        print(f"{pc.name} 已锁屏")
        return

    # --brightness N
    if args.brightness is not None:
        pc.set_brightness(args.brightness)
        print(f"{pc.name} 亮度已设置为 {args.brightness}")
        return

    # --get-brightness
    if args.get_brightness:
        value = pc.get_brightness()
        print(f"{pc.name} 亮度: {value}")
        return

    # --volume N
    if args.volume is not None:
        pc.set_volume(args.volume)
        print(f"{pc.name} 音量已设置为 {args.volume}")
        return

    # --get-volume
    if args.get_volume:
        value = pc.get_volume()
        print(f"{pc.name} 音量: {value}")
        return

    print("请指定操作，例如 --power on / --sleep / --status")
```

---

## 四、主入口 `main(args)`

```python
def main(args):
    args = parse_args(args)

    # --get_device_info：查看设备规格
    if args.get_device_info:
        from .device import get_device_info
        device_info = get_device_info(args.get_device_info)
        print(json.dumps(device_info, indent=2, ensure_ascii=False))
        return

    # 无任何操作时退出
    has_list = args.list_devices or args.list_pc
    has_func = hasattr(args, 'func') and args.func is not None
    if not has_list and not has_func:
        return

    # login 子命令
    if has_func and args.func == 'login':
        from .api import miiotpcAPI
        auth_path = args.auth_path
        file_path = Path(auth_path) / "auth.json" if Path(auth_path).is_dir() else Path(auth_path)
        try:
            api = miiotpcAPI(auth_data_path=auth_path)
        except json.JSONDecodeError:
            file_path.unlink(missing_ok=True)
            api = miiotpcAPI(auth_data_path=auth_path)
        if not api.available:
            api.login()
        return

    # 其他命令需要认证
    api = init_api(args.auth_path)

    # --list_devices
    if args.list_devices:
        get_devices_list(api)

    # --list_pc
    if args.list_pc:
        get_pc_devices(api)

    # 子命令分发
    if has_func:
        if args.func == 'get':
            handle_get(api, args)
        elif args.func == 'set':
            handle_set(api, args)
        elif args.func == 'action':
            handle_action(api, args)
        elif args.func == 'pc':
            pc_action_handler(api, args)
```

---

## 五、子命令处理函数

### 5.1 `handle_get(api, args)`

```python
def handle_get(api: miiotpcAPI, args):
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    value = device.get(args.prop_name)
    print(f"{device.name} ({device.did}) 的 {args.prop_name} = {value}")
```

### 5.2 `handle_set(api, args)`

```python
def handle_set(api: miiotpcAPI, args):
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    try:
        device.set(args.prop_name, args.value)
    except Exception as e:
        print(f"设置失败: {device.name} 的 {args.prop_name} = {args.value}: {e}")
        return
    print(f"{device.name} ({device.did}) 的 {args.prop_name} 已设置为 {args.value}")
```

### 5.3 `handle_action(api, args)`

```python
def handle_action(api: miiotpcAPI, args):
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    device.run_action(args.action_name, **(args.params or {}))
    print(f"{device.name} ({device.did}) 的动作 {args.action_name} 执行成功")
```

---

## 六、CLI 入口点

```python
def cli():
    main(sys.argv[1:])

if __name__ == "__main__":
    main(sys.argv[1:])
```

---

## 七、完整使用示例

```bash
# 登录（首次使用）
miiotpcApi login

# 列出所有设备
miiotpcApi -l

# 仅列出PC设备
miiotpcApi --list_pc

# 查看设备MIoT Spec
miiotpcApi --get_device_info xiaomi.pc.v1

# --- PC 设备控制 ---
# 查看PC状态
miiotpcApi --dev_name "我的笔记本" --status

# 开机
miiotpcApi --dev_name "我的笔记本" --power on

# 关机
miiotpcApi --dev_name "我的笔记本" --power off

# 睡眠
miiotpcApi --dev_name "我的笔记本" --sleep

# 唤醒
miiotpcApi --dev_name "我的笔记本" --wake

# 锁屏
miiotpcApi --dev_name "我的笔记本" --lock

# 设置亮度
miiotpcApi --dev_name "我的笔记本" --brightness 80

# 获取亮度
miiotpcApi --dev_name "我的笔记本" --get-brightness

# 设置音量
miiotpcApi --dev_name "我的笔记本" --volume 50

# 获取音量
miiotpcApi --dev_name "我的笔记本" --get-volume

# --- 通用属性操作 ---
# 读取属性
miiotpcApi get --dev_name "我的笔记本" --prop_name on

# 设置属性
miiotpcApi set --dev_name "我的笔记本" --prop_name brightness --value 80

# 执行动作
miiotpcApi action --dev_name "我的笔记本" --action_name power-on
```

---

## 八、日志级别控制

通过环境变量 `MIIOTPC_LOG_LEVEL` 控制日志级别：

```bash
# 默认 INFO
MIIOTPC_LOG_LEVEL=DEBUG miiotpcApi --dev_name "我的笔记本" --status
```

支持级别: DEBUG / INFO / WARNING / ERROR / CRITICAL
