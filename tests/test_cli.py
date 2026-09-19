"""CLI 测试：参数解析、设备列表输出、UTF-8 流重配置

覆盖 v0.1.3 改动：
- print_devices() 的「联网状态」标签与 note 提示
- force_utf8_stdio() 的幂等性与容错
- main() 入口确实调用了 force_utf8_stdio()（程序化入口同样生效）
- 版本号与 status 枚举在代码/文档之间保持一致
"""

import inspect
import re
import sys
from pathlib import Path

import pytest

import miiotpcApi.__main__ as cli
from miiotpcApi.__main__ import force_utf8_stdio, parse_args, print_devices
from miiotpcApi.version import version as package_version

FULL_STATUS_ENUM = {"1", "2", "3", "4", "6", "8"}


# ---------------------------------------------------------------- 参数解析


class TestParseArgs:
    def test_list_pc(self):
        args = parse_args(["--list-pc"])
        assert args.list_pc is True
        assert args.command is None

    def test_list_devices_short_flag(self):
        args = parse_args(["-l"])
        assert args.list_devices is True

    def test_status_batch_without_device(self):
        """批量 --status：不带 --did/--dev-name 时也是合法的"""
        args = parse_args(["--status"])
        assert args.status is True
        assert args.did is None
        assert args.dev_name is None

    def test_status_with_did(self):
        args = parse_args(["--status", "--did", "2047118207"])
        assert args.status is True
        assert args.did == "2047118207"

    def test_status_with_dev_name(self):
        args = parse_args(["--status", "--dev-name", "我的笔记本"])
        assert args.dev_name == "我的笔记本"

    @pytest.mark.parametrize(
        "value,expected", [("on", "on"), ("sleep", "sleep"), ("off", "off")]
    )
    def test_power_choices(self, value, expected):
        args = parse_args(["--dev-name", "x", "--power", value])
        assert args.power == expected

    def test_power_rejects_unknown_value(self):
        """电源操作没有 toggle，非法取值必须报错"""
        with pytest.raises(SystemExit):
            parse_args(["--dev-name", "x", "--power", "toggle"])

    def test_did_and_dev_name_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_args(["--did", "1", "--dev-name", "x", "--status"])

    @pytest.mark.parametrize("flag", ["--temperature", "--battery", "--charging-state"])
    def test_pc_actions_mutually_exclusive_with_status(self, flag):
        with pytest.raises(SystemExit):
            parse_args(["--dev-name", "x", "--status", flag])

    @pytest.mark.parametrize(
        "argv,expected",
        [
            (["login"], "login"),
            (["get", "--dev-name", "x", "--prop-name", "status"], "get"),
            (["set", "--dev-name", "x", "--prop-name", "p", "--value", "1"], "set"),
            (["action", "--dev-name", "x", "--action-name", "turn-on"], "action"),
        ],
    )
    def test_subcommands(self, argv, expected):
        assert parse_args(argv).command == expected

    def test_get_requires_prop_name(self):
        with pytest.raises(SystemExit):
            parse_args(["get", "--dev-name", "x"])

    def test_get_device_info(self):
        args = parse_args(["--get-device-info", "xiaomi.laptop.p59"])
        assert args.get_device_info == "xiaomi.laptop.p59"

    def test_version_flag(self, capsys):
        """-v 打印版本号并以 0 退出。

        注意 prog 名在 pytest 下不是 "miiotpcApi"（argparse 取 sys.argv[0]），
        所以只断言版本号本身。
        """
        with pytest.raises(SystemExit) as exc:
            parse_args(["-v"])
        assert exc.value.code == 0
        assert package_version in capsys.readouterr().out

    def test_no_action_falls_through_without_error(self):
        """顶层没有动作但有 --list-pc 时不应报错"""
        args = parse_args(["--list-pc"])
        assert args.command is None and args.list_pc is True


# ------------------------------------------------------------ 设备列表输出


class TestPrintDevices:
    def test_label_and_note_rendered(self, capsys):
        print_devices(
            [{"name": "笔记本A", "did": "100", "model": "xiaomi.laptop.p59", "isOnline": True}],
            "PC/笔记本设备",
            note="联网状态不代表是否开机",
        )
        out = capsys.readouterr().out
        assert "联网状态: 在线" in out
        assert "提示: 联网状态不代表是否开机" in out

    def test_offline_device_rendered(self, capsys):
        print_devices(
            [{"name": "B", "did": "2", "model": "m", "isOnline": False}], "PC/笔记本设备"
        )
        assert "联网状态: 离线" in capsys.readouterr().out

    def test_missing_fields_have_placeholders(self, capsys):
        print_devices([{}], "设备列表")
        out = capsys.readouterr().out
        assert "<未命名设备>" in out
        assert "<未知>" in out

    def test_empty_list_prints_not_found_and_skips_note(self, capsys):
        """现状（保持）：列表为空时提前 return，note 不打印"""
        print_devices([], "PC/笔记本设备", note="这条不会出现")
        out = capsys.readouterr().out
        assert "未找到PC/笔记本设备。" in out
        assert "这条不会出现" not in out

    def test_note_omitted_when_not_provided(self, capsys):
        print_devices([{"name": "X", "did": "1", "model": "m", "isOnline": True}], "PC/笔记本设备")
        assert "提示:" not in capsys.readouterr().out


# ------------------------------------------------------------ UTF-8 流重配置


class _StreamWithReconfigure:
    def __init__(self, encoding="gbk"):
        self.encoding = encoding
        self.calls = []

    def reconfigure(self, encoding=None):
        self.calls.append(encoding)
        self.encoding = encoding


class _StreamNoReconfigure:
    """模拟被测试框架替换、没有 reconfigure 的流"""

    def __init__(self):
        self.encoding = "gbk"


class _StreamRaises:
    def __init__(self, exc):
        self.encoding = "gbk"
        self.exc = exc

    def reconfigure(self, encoding=None):
        raise self.exc


class TestForceUtf8Stdio:
    def test_switches_both_streams_to_utf8(self, monkeypatch):
        out, err = _StreamWithReconfigure(), _StreamWithReconfigure()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", err)
        force_utf8_stdio()
        assert out.encoding == "utf-8"
        assert err.encoding == "utf-8"

    def test_is_idempotent(self, monkeypatch):
        out = _StreamWithReconfigure()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", _StreamWithReconfigure())
        force_utf8_stdio()
        force_utf8_stdio()
        assert out.calls == ["utf-8", "utf-8"]
        assert out.encoding == "utf-8"

    @pytest.mark.parametrize("exc", [ValueError("wrapped"), OSError("closed")])
    def test_swallows_reconfigure_errors(self, monkeypatch, exc):
        """流不支持运行时重配置时必须静默跳过，不能影响 CLI 运行"""
        monkeypatch.setattr(sys, "stdout", _StreamRaises(exc))
        monkeypatch.setattr(sys, "stderr", _StreamRaises(exc))
        force_utf8_stdio()  # 不应抛出

    def test_skips_streams_without_reconfigure(self, monkeypatch):
        out = _StreamNoReconfigure()
        monkeypatch.setattr(sys, "stdout", out)
        monkeypatch.setattr(sys, "stderr", _StreamNoReconfigure())
        force_utf8_stdio()  # 不应抛出
        assert out.encoding == "gbk"  # 未被改动

    def test_main_entry_applies_utf8(self, monkeypatch):
        """main() 是程序化入口，必须自己调用 force_utf8_stdio()"""
        calls = []
        monkeypatch.setattr(cli, "force_utf8_stdio", lambda: calls.append(1))
        with pytest.raises(SystemExit):
            cli.main([])  # 无动作时打印 help 并退出
        assert calls == [1], "main() 入口未调用 force_utf8_stdio()"


# ------------------------------------------------------------ 一致性守护


class TestConsistency:
    def test_version_matches_pyproject(self):
        """version.py 与 pyproject.toml 必须同步，否则发布会出现版本错位"""
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert match, "pyproject.toml 中找不到 version"
        assert package_version == match.group(1)

    def test_status_enum_consistent_across_docstring_and_cli(self):
        """status 枚举在 PCDevice.status docstring 与 CLI 提示语之间必须一致

        回归防护：两者曾经只列了 8/2/3，遗漏了 1/4/6。

        CLI 侧只扫描 ``note=(...)`` 那段字符串字面量——整个 __main__.py 源码里
        还有 ``sleep_time=0`` 之类的写法，会被 ``\\d=`` 误抓成枚举值。
        """
        from miiotpcApi.device import PCDevice

        doc_enums = set(re.findall(r"(?<!\d)(\d)=", inspect.getdoc(PCDevice.status)))

        source = inspect.getsource(cli)
        note_block = re.search(r"note=\((.*?)\),", source, re.DOTALL)
        assert note_block, "__main__.py 中找不到 --list-pc 的 note 提示语"
        cli_enums = set(re.findall(r"(?<!\d)(\d)=", note_block.group(1)))

        assert doc_enums == FULL_STATUS_ENUM, f"docstring 枚举异常: {sorted(doc_enums)}"
        assert cli_enums == FULL_STATUS_ENUM, f"CLI 提示语枚举异常: {sorted(cli_enums)}"

    def test_docstring_states_non_eight_rule(self):
        from miiotpcApi.device import PCDevice

        doc = inspect.getdoc(PCDevice.status)
        assert "非 8 即非运行中" in doc
