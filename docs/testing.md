# 测试策略

## 测试框架

使用 Python 内置 `unittest`，不引入额外测试依赖。

## 测试结构

```
tests/
├── test_api.py       # API 客户端测试
├── test_device.py    # 设备封装测试
└── test_cli.py       # CLI 参数解析测试
```

## 测试用例设计

### test_api.py

```python
"""API 客户端测试 - Mock 网络请求"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# --- 测试初始化 ---

class TestAPIInit:
    def test_default_auth_path(self):
        """默认认证路径为 ~/.config/miiotpc-api/auth.json"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI()
        expected = Path.home() / ".config" / "miiotpc-api" / "auth.json"
        assert api.auth_data_path == expected

    def test_custom_auth_path(self):
        """自定义认证路径"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/test-auth.json")
        assert api.auth_data_path == Path("/tmp/test-auth.json")

    def test_auth_path_as_directory(self):
        """传入目录时自动添加 auth.json"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/test-dir")
        assert api.auth_data_path == Path("/tmp/test-dir/auth.json")

    def test_missing_auth_file(self):
        """认证文件不存在时 auth_data 为空字典"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        assert api.auth_data == {}


# --- 测试认证状态 ---

class TestAPIAuth:
    def test_available_no_data(self):
        """无认证数据时 available 为 False"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        assert api.available == False

    def test_available_missing_keys(self):
        """认证数据缺少必要字段时 available 为 False"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI()
        api.auth_data = {"ua": "test"}  # 缺少 ssecurity, userId 等
        assert api.available == False


# --- 测试 PC 设备筛选 ---

class TestFindPCDevices:
    @patch('miiotpcApi.api.requests.Session')
    def test_find_pc_devices_by_name(self, mock_session):
        """通过设备名称筛选PC设备"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api.get_devices_list = MagicMock(return_value=[
            {"did": "1", "name": "我的笔记本", "model": "xiaomi.pc.v1", "isOnline": True},
            {"did": "2", "name": "客厅灯", "model": "yeelink.light.lamp4", "isOnline": True},
            {"did": "3", "name": "工作电脑", "model": "generic.desktop", "isOnline": False},
        ])

        result = api.find_pc_devices()
        assert len(result) == 2
        assert result[0]["did"] == "1"
        assert result[1]["did"] == "3"

    @patch('miiotpcApi.api.requests.Session')
    def test_find_pc_devices_with_keyword(self, mock_session):
        """通过自定义关键词筛选"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api.get_devices_list = MagicMock(return_value=[
            {"did": "1", "name": "小米笔记本Pro", "model": "xiaomi.notebook.v1", "isOnline": True},
            {"did": "2", "name": "客厅灯", "model": "yeelink.light.lamp4", "isOnline": True},
        ])

        result = api.find_pc_devices(keyword="小米")
        assert len(result) == 1
        assert result[0]["name"] == "小米笔记本Pro"


# --- 测试设备属性读写（Mock）---

class TestDevicePropAPI:
    def test_get_devices_prop_single(self):
        """单个属性查询"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api._request = MagicMock(return_value=[
            {"did": "123", "siid": 2, "piid": 1, "value": True, "code": 0}
        ])

        result = api.get_devices_prop({"did": "123", "siid": 2, "piid": 1})
        assert result["value"] == True

    def test_set_devices_prop_code_1(self):
        """设置属性返回 code=1（网关已接收）"""
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api._request = MagicMock(return_value=[
            {"did": "123", "siid": 2, "piid": 1, "code": 1}
        ])

        result = api.set_devices_prop({"did": "123", "siid": 2, "piid": 1, "value": True})
        assert result["message"] == "成功"
```

### test_device.py

```python
"""设备封装测试"""

import pytest
from unittest.mock import MagicMock, patch

# --- DevProp 测试 ---

class TestDevProp:
    def test_valid_prop(self):
        """合法属性初始化"""
        from miiotpcApi.device import DevProp
        prop = DevProp({
            "name": "on",
            "description": "开关",
            "type": "bool",
            "rw": "rw",
            "range": None,
            "value-list": None,
            "method": {"siid": 2, "piid": 1}
        })
        assert prop.name == "on"
        assert prop.type == "bool"
        assert prop.rw == "rw"
        assert prop.method == {"siid": 2, "piid": 1}

    def test_invalid_type(self):
        """不支持的类型应抛出 ValueError"""
        from miiotpcApi.device import DevProp
        with pytest.raises(ValueError, match="不支持的类型"):
            DevProp({
                "name": "test",
                "description": "测试",
                "type": "object",
                "rw": "r",
                "range": None,
                "method": {"siid": 1, "piid": 1}
            })


# --- MiotDevice 测试 ---

class TestMiotDevice:
    def test_init_requires_did_or_name(self):
        """必须提供 did 或 dev_name"""
        from miiotpcApi.device import MiotDevice
        from miiotpcApi import miiotpcAPI
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")

        with pytest.raises(ValueError, match="必须提供"):
            MiotDevice(api)

    def test_device_not_found(self):
        """设备未找到应抛出异常"""
        from miiotpcApi.device import MiotDevice
        from miiotpcApi import miiotpcAPI
        from miiotpcApi.errors import DeviceNotFoundError
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api.get_devices_list = MagicMock(return_value=[])

        with pytest.raises(DeviceNotFoundError):
            MiotDevice(api, dev_name="不存在的设备")

    def test_multiple_devices_found(self):
        """多个同名设备应抛出异常"""
        from miiotpcApi.device import MiotDevice
        from miiotpcApi import miiotpcAPI
        from miiotpcApi.errors import MultipleDevicesFoundError
        api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")
        api.get_devices_list = MagicMock(return_value=[
            {"did": "1", "name": "笔记本", "model": "a.b.c"},
            {"did": "2", "name": "笔记本", "model": "d.e.f"},
        ])

        with pytest.raises(MultipleDevicesFoundError):
            MiotDevice(api, dev_name="笔记本")


# --- PCDevice 测试 ---

class TestPCDevice:
    def test_check_capability_not_supported(self):
        """不支持的操作应抛出 NotImplementedError"""
        from miiotpcApi.device import PCDevice, MiotDevice
        from unittest.mock import patch

        # Mock MiotDevice 和 get_device_info
        with patch('miiotpcApi.device.MiotDevice') as MockDevice:
            mock_instance = MockDevice.return_value
            mock_instance.prop_list = {}
            mock_instance.action_list = {}

            from miiotpcApi import miiotpcAPI
            api = miiotpcAPI(auth_data_path="/tmp/nonexistent/auth.json")

            pc = PCDevice(api, dev_name="test")
            with pytest.raises(NotImplementedError, match="不支持"):
                pc.power_on()
```

### test_cli.py

```python
"""CLI 参数解析测试"""

import pytest
from miiotpcApi.__main__ import parse_args

class TestCLIArgs:
    def test_login_subcommand(self):
        """login 子命令解析"""
        args = parse_args(['login'])
        assert args.func == 'login'

    def test_get_subcommand(self):
        """get 子命令解析"""
        args = parse_args(['get', '--dev_name', '笔记本', '--prop_name', 'on'])
        assert args.func == 'get'
        assert args.dev_name == '笔记本'
        assert args.prop_name == 'on'

    def test_set_subcommand(self):
        """set 子命令解析"""
        args = parse_args(['set', '--dev_name', '笔记本', '--prop_name', 'brightness', '--value', '80'])
        assert args.func == 'set'
        assert args.value == '80'

    def test_pc_list(self):
        """pc --list 解析"""
        args = parse_args(['pc', '--list'])
        assert args.func == 'pc'
        assert args.list == True

    def test_pc_power_on(self):
        """pc --power on 解析"""
        args = parse_args(['pc', '--dev_name', '笔记本', '--power', 'on'])
        assert args.func == 'pc'
        assert args.power == 'on'
        assert args.dev_name == '笔记本'

    def test_pc_sleep(self):
        """pc --sleep 解析"""
        args = parse_args(['pc', '--did', '12345', '--sleep'])
        assert args.func == 'pc'
        assert args.sleep == True
        assert args.did == '12345'

    def test_list_devices(self):
        """-l 选项解析"""
        args = parse_args(['-l'])
        assert args.list_devices == True

    def test_list_pc(self):
        """--list_pc 选项解析"""
        args = parse_args(['--list_pc'])
        assert args.list_pc == True

    def test_get_device_info(self):
        """--get_device_info 选项解析"""
        args = parse_args(['--get_device_info', 'xiaomi.pc.v1'])
        assert args.get_device_info == 'xiaomi.pc.v1'
```

## 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/test_api.py -v

# 运行指定测试类
uv run pytest tests/test_device.py::TestMiotDevice -v

# 运行指定测试方法
uv run pytest tests/test_cli.py::TestCLIArgs::test_pc_power_on -v
```

## 测试原则

1. **Mock 网络请求**：所有对外部 API 的调用都通过 `unittest.mock` 模拟，不发送真实请求
2. **测试异常路径**：覆盖所有可能的错误场景（设备未找到、属性不可写、认证失败等）
3. **CLI 参数解析**：单独测试 argparse 的参数解析逻辑
4. **不测试加密逻辑**：`miutils.py` 直接从 mijiaAPI 复制，不额外测试
5. **不测试认证流程**：`login()` 需要真实扫码，仅测试初始化和状态检查
