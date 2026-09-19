"""API 客户端测试：PC/笔记本设备筛选逻辑

不发送任何网络请求——miiotpcAPI 通过 object.__new__ 构造，
get_devices_list() 被替换为返回固定列表的桩。

覆盖 find_pc_devices() 的关键词匹配规则，这是 `--list-pc` 能否找到设备的
唯一依据：设备名/型号不含关键词时会返回空列表，是 skill 文档里记载的已知坑。
"""

import pytest

from miiotpcApi.api import miiotpcAPI

DEFAULT_KEYWORDS = {"pc", "电脑", "笔记本", "laptop", "desktop", "notebook"}


def make_api(devices):
    api = object.__new__(miiotpcAPI)
    api.get_devices_list = lambda use_cache=True: list(devices)
    return api


DEVICES = [
    {"name": "REDMI Book Pro 16 2026", "model": "xiaomi.laptop.n56sr", "did": "1"},
    {"name": "卧室的Xiaomi Book Pro 14笔记本电脑", "model": "xiaomi.laptop.p52", "did": "2"},
    {"name": "吸顶灯", "model": "xiaomi.switch.w3", "did": "3"},
    {"name": "插排", "model": "chuangmi.plug.v3", "did": "4"},
    {"name": "客厅的台式机", "model": "xiaomi.desktop.d1", "did": "5"},
]


class TestFindPcDevices:
    def test_matches_laptop_in_model(self):
        results = make_api(DEVICES).find_pc_devices()
        dids = {d["did"] for d in results}
        assert "1" in dids, "model 含 laptop 应被识别为 PC"
        assert "2" in dids, "model 含 laptop 应被识别为 PC"

    def test_matches_chinese_keyword_in_name(self):
        """设备名含「笔记本」即使 model 无 laptop 也应命中"""
        devices = [{"name": "我的笔记本", "model": "xiaomi.unknown.x1", "did": "99"}]
        assert make_api(devices).find_pc_devices() != []

    def test_matches_desktop_keyword(self):
        results = make_api(DEVICES).find_pc_devices()
        assert {d["did"] for d in results} >= {"5"}, "model 含 desktop 应被识别为 PC"

    def test_excludes_non_pc_devices(self):
        results = make_api(DEVICES).find_pc_devices()
        dids = {d["did"] for d in results}
        assert "3" not in dids, "吸顶灯不应被识别为 PC"
        assert "4" not in dids, "插排不应被识别为 PC"

    def test_returns_empty_when_no_keyword_matches(self):
        """skill 文档记载的坑：名称/型号不含关键词时 --list-pc 为空"""
        devices = [
            {"name": "吸顶灯", "model": "xiaomi.switch.w3", "did": "3"},
            {"name": "插排", "model": "chuangmi.plug.v3", "did": "4"},
        ]
        assert make_api(devices).find_pc_devices() == []

    @pytest.mark.parametrize("keyword", sorted(DEFAULT_KEYWORDS))
    def test_every_default_keyword_matches(self, keyword):
        """文档声明的默认关键词集合必须全部生效"""
        devices = [{"name": f"设备_{keyword}", "model": "generic.device.v1", "did": "k"}]
        assert make_api(devices).find_pc_devices() != [], f"关键词 {keyword} 未生效"

    def test_matching_is_case_insensitive(self):
        devices = [{"name": "MY LAPTOP", "model": "GENERIC.DEVICE.V1", "did": "ci"}]
        assert make_api(devices).find_pc_devices() != []

    def test_custom_keyword_is_added_to_defaults(self):
        """自定义关键词是追加，不应覆盖默认集合"""
        devices = [
            {"name": "游戏本", "model": "generic.device.v1", "did": "g"},
            {"name": "我的笔记本", "model": "generic.device.v2", "did": "n"},
        ]
        results = make_api(devices).find_pc_devices(keyword="游戏本")
        dids = {d["did"] for d in results}
        assert "g" in dids, "自定义关键词未生效"
        assert "n" in dids, "自定义关键词不应覆盖默认的「笔记本」"

    def test_custom_keyword_is_lowercased(self):
        devices = [{"name": "workstation alpha", "model": "generic.device.v1", "did": "w"}]
        assert make_api(devices).find_pc_devices(keyword="WORKSTATION") != []

    def test_missing_name_or_model_does_not_crash(self):
        devices = [{"did": "bare"}, {"name": "只有名字笔记本", "did": "n"}]
        results = make_api(devices).find_pc_devices()
        assert {d["did"] for d in results} == {"n"}

    def test_empty_device_list(self):
        assert make_api([]).find_pc_devices() == []

    def test_did_preserved_in_results(self):
        """返回的是原始设备字典，字段不应被改写"""
        results = make_api(DEVICES).find_pc_devices()
        by_did = {d["did"]: d for d in results}
        assert by_did["1"]["model"] == "xiaomi.laptop.n56sr"
        assert by_did["2"]["name"] == "卧室的Xiaomi Book Pro 14笔记本电脑"
