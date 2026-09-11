# miiotpcApi — 米家笔记本/PC 设备控制 API
# Copyright (C) 2026 comor <304593790@qq.com>
#
# 本文件是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
# 的衍生作品，基于 apis.py 精简而来。原项目著作权归 Do1e <i@do1e.cn> 所有。
#
# 本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
# （或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
# 但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。
#
# 完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。

import json
import locale
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union
from urllib import parse

import requests
import tzlocal
from qrcode import QRCode

from .errors import ERROR_CODE, APIError, LoginError
from .logger import logger
from .miutils import (
    decrypt,
    gen_nonce,
    generate_enc_params,
    get_signed_nonce,
)


class miiotpcAPI():
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

        if auth_data_path is None:
            self.auth_data_path = Path.home() / ".config" / "miiotpc-api" / "auth.json"
        elif Path(auth_data_path).is_dir():
            self.auth_data_path = Path(auth_data_path) / "auth.json"
        else:
            self.auth_data_path = Path(auth_data_path)

        self._available_cache = None
        self._available_cache_time = 0
        self._devices_list_cache = None
        self._devices_list_cache_time = 0

        if self.auth_data_path.exists():
            with open(self.auth_data_path, "r") as f:
                self.auth_data = json.load(f)
            self._init_session()
        else:
            self.auth_data = {}

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
                      f"timezone=GMT{datetime.now().astimezone().strftime('%z')[:3]}:{datetime.now().astimezone().strftime('%z')[3:]};"
                      f"is_daylight={time.daylight};"
                      f"dst_offset={time.localtime().tm_isdst * 60 * 60 * 1000};"
                      f"channel=MI_APP_STORE;"
                      f"countryCode={self.locale.split('_')[1] if self.locale else 'CN'};"
                      f"PassportDeviceId={self.deviceId};"
                      f"locale={self.locale}",
        })

    @property
    def available(self) -> bool:
        if not self.auth_data:
            return False
        if any(key not in self.auth_data for key in ["ua", "ssecurity", "userId", "cUserId", "serviceToken"]):
            return False

        current_time = int(time.time())
        if current_time - self._available_cache_time < 60:
            logger.debug(f"使用缓存的available结果: {self._available_cache}")
            return self._available_cache

        try:
            self.check_new_msg(refresh_token=False)
        except Exception:
            self._available_cache = None
            self._available_cache_time = 0
            return False

        self._available_cache = True
        self._available_cache_time = current_time
        return True

    @property
    def pass_o(self) -> str:
        if "pass_o" in self.auth_data:
            return self.auth_data["pass_o"]
        self.auth_data["pass_o"] = "".join(random.choices("0123456789abcdef", k=16))
        return self.auth_data["pass_o"]

    @property
    def user_agent(self) -> str:
        if "ua" in self.auth_data:
            return self.auth_data["ua"]
        ua_id1 = "".join(random.choices("0123456789ABCDEF", k=40))
        ua_id2 = "".join(random.choices("0123456789ABCDEF", k=32))
        ua_id3 = "".join(random.choices("0123456789ABCDEF", k=32))
        ua_id4 = "".join(random.choices("0123456789ABCDEF", k=40))
        self.auth_data["ua"] = (
            f"Android-15-11.0.701-Xiaomi-23046RP50C-OS2.0.212.0.VMYCNXM-"
            f"{ua_id1}-{self.locale.split('_')[1] if self.locale else 'CN'}-"
            f"{ua_id3}-{ua_id2}-SmartHome-MI_APP_STORE-{ua_id1}|{ua_id4}|{self.pass_o}-64"
        )
        return self.auth_data["ua"]

    @property
    def deviceId(self) -> str:
        if "deviceId" in self.auth_data:
            return self.auth_data["deviceId"]
        self.auth_data["deviceId"] = "".join(
            random.choices("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-", k=16)
        )
        return self.auth_data["deviceId"]

    def _parse_service_ret(self, service_ret: requests.Response) -> dict:
        text = service_ret.text.replace("&&&START&&&", "")
        service_data = json.loads(text)
        return service_data

    def _handle_ret(self, fetch_ret: requests.Response, verify_code: bool = True) -> dict:
        if fetch_ret.status_code != 200:
            raise LoginError(fetch_ret.status_code, fetch_ret.text)
        fetch_data = self._parse_service_ret(fetch_ret)
        if verify_code and fetch_data.get("code", 0) != 0:
            raise LoginError(fetch_data["code"], fetch_data.get("desc", "未知错误"))
        return fetch_data

    @staticmethod
    def _print_qr(loginurl: str, box_size: int = 10):
        logger.info("请使用米家APP扫描下方二维码")
        qr = QRCode(border=1, box_size=box_size)
        qr.add_data(loginurl)
        try:
            qr.print_ascii(invert=True, tty=True)
        except OSError:
            qr.print_ascii(invert=True, tty=False)
            logger.info("如果无法扫描二维码，请更改终端字体，如`Maple Mono`、`Fira Code`等。")

    def _save_auth_data(self):
        self.auth_data["saveTime"] = int(time.time() * 1000)
        self.auth_data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.auth_data_path, "w") as f:
            json.dump(self.auth_data, f, indent=2, ensure_ascii=False)
        logger.debug(f"已保存认证数据到 {self.auth_data_path}")

    def _get_location(self) -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": f"deviceId={self.deviceId};"
                      f"pass_o={self.pass_o};"
                      f"passToken={self.auth_data.get('passToken', '')};"
                      f"userId={self.auth_data.get('userId', '')};"
                      f"cUserId={self.auth_data.get('cUserId', '')};"
                      f"uLocale={self.locale};",
        }
        service_ret = requests.get(self.service_login_url, headers=headers)
        service_data = self._handle_ret(service_ret, verify_code=False)
        location = service_data["location"]
        if service_data['code'] == 0:
            ret = self.session.get(location)
            if ret.status_code == 200 and ret.text == "ok":
                cookies = self.session.cookies.get_dict()
                self.auth_data.update(cookies)
                self.auth_data["ssecurity"] = service_data["ssecurity"]
                return {"code": 0, "message": "刷新Token成功"}
        location_data = parse.parse_qs(parse.urlparse(location).query)
        return {k: v[0] for k, v in location_data.items()}

    def _refresh_token(self) -> dict:
        if self.available:
            logger.debug("Token 有效，无需刷新")
            return self.auth_data
        location_data = self._get_location()
        if location_data.get("code", -1) == 0 and location_data.get("message", "") == "刷新Token成功":
            self._save_auth_data()
            self._init_session()
            logger.debug("刷新Token成功")
            return self.auth_data
        else:
            raise LoginError(-1, "刷新Token失败，请重新登录")

    def login(self, *args, **kwargs) -> dict:
        """二维码登录方法"""
        return self.QRlogin()

    def QRlogin(self) -> dict:
        """二维码登录方法"""
        login_data = self._get_qr_login_data()
        if login_data.get("refreshed"):
            return self.auth_data
        self._print_qr(login_data["loginUrl"])
        print(f"也可以访问链接查看二维码图片: {login_data['qr']}")
        return self._complete_qr_login(login_data)

    def _get_qr_login_data(self) -> dict:
        """获取二维码登录数据"""
        location_data = self._get_location()
        if location_data.get("code", -1) == 0 and location_data.get("message", "") == "刷新Token成功":
            self._save_auth_data()
            self._init_session()
            logger.info("刷新Token成功，无需登录")
            return {"refreshed": True}

        location_data.update({
            "theme": "",
            "bizDeviceType": "",
            "_hasLogo": "false",
            "_qrsize": "240",
            "_dc": str(int(time.time() * 1000)),
        })
        url = self.login_url + "?" + parse.urlencode(location_data)
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "keep-alive",
        }
        login_ret = requests.get(url, headers=headers)
        login_data = self._handle_ret(login_ret)
        return login_data

    def _complete_qr_login(self, login_data: dict) -> dict:
        """长轮询等待扫码并完成登录"""
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "keep-alive",
        }
        session = requests.Session()
        try:
            lp_ret = session.get(login_data["lp"], headers=headers, timeout=120)
            lp_data = self._handle_ret(lp_ret)
        except requests.exceptions.Timeout:
            raise LoginError(-1, "超时，请重试")

        auth_keys = ["psecurity", "nonce", "ssecurity", "passToken", "userId", "cUserId"]
        for key in auth_keys:
            self.auth_data[key] = lp_data[key]
        callback_url = lp_data["location"]
        session.get(callback_url, headers=headers)
        cookies = session.cookies.get_dict()
        self.auth_data.update(cookies)
        self.auth_data.update({
            "expireTime": int((datetime.now() + timedelta(days=30)).timestamp() * 1000),
        })
        self._save_auth_data()
        logger.info("登录成功")
        self._init_session()
        return self.auth_data

    def _request(self, uri: str, data: dict, refresh_token: bool = True) -> dict:
        logger.debug(f"请求 URI: {uri}，数据: {data}")
        if refresh_token:
            self._refresh_token()
        url = self.api_base_url + uri
        params = {"data": json.dumps(data, separators=(',', ':'))}
        nonce = gen_nonce()
        signed_nonce = get_signed_nonce(self.auth_data["ssecurity"], nonce)
        params = generate_enc_params(uri, "POST", signed_nonce, nonce, params, self.auth_data["ssecurity"])
        ret = self.session.post(url, data=params)
        try:
            ret_data = json.loads(ret.text)
        except json.JSONDecodeError:
            dec_data = decrypt(self.auth_data["ssecurity"], nonce, ret.text)
            ret_data = json.loads(dec_data)
        logger.debug(f"响应数据: {ret_data}")
        if ret_data.get("code", 0) != 0 or "result" not in ret_data:
            raise APIError(ret_data["code"], ret_data.get("message", ret_data.get("desc", "未知错误")))
        return ret_data["result"]

    def check_new_msg(self, begin_at: int = int(time.time()) - 3600, refresh_token: bool = True) -> dict:
        uri = "/v2/message/v2/check_new_msg"
        data = {"begin_at": begin_at}
        return self._request(uri, data, refresh_token=refresh_token)

    def get_devices_list(self, use_cache: bool = True) -> list:
        """
        获取所有设备列表（含共享设备）

        参数:
            use_cache: 是否使用短 TTL 缓存。批量操作会反复构造设备对象，
                       每次都拉一遍列表既慢又无必要；默认缓存 30 秒。

        返回值:
            list: 设备信息列表，每个元素包含 did, name, model, isOnline 等字段
        """
        if use_cache and self._devices_list_cache is not None:
            if time.time() - self._devices_list_cache_time < 30:
                logger.debug("使用缓存的设备列表")
                return self._devices_list_cache

        devices = self._get_all_devices()
        self._devices_list_cache = devices
        self._devices_list_cache_time = time.time()
        return devices

    def _get_all_devices(self) -> list:
        """通过共享设备接口获取所有设备"""
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

    def get_shared_devices_list(self) -> list:
        """
        获取共享设备列表

        返回值:
            list: 共享设备信息列表
        """
        devices = self._get_all_devices()
        return [d for d in devices if d.get("owner", False)]

    def find_pc_devices(self, keyword: Optional[str] = None) -> list:
        """
        筛选PC/笔记本相关设备

        通过设备名称或model关键词过滤。默认匹配: pc, 电脑, 笔记本, laptop, desktop, notebook

        参数:
            keyword: 额外的自定义关键词

        返回值:
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

    def get_devices_prop(self, data: Union[list, dict]) -> Union[list, dict]:
        """
        获取设备属性

        参数:
            data: dict 单个属性 {"did", "siid", "piid"} 或 list 批量属性

        返回值:
            Union[list, dict]: 属性结果，包含 did, siid, piid, value, code
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

    def set_devices_prop(self, data: Union[list, dict]) -> Union[list, dict]:
        """
        设置设备属性

        参数:
            data: dict 单个属性 {"did", "siid", "piid", "value"} 或 list 批量属性

        返回值:
            Union[list, dict]: 设置结果，包含 did, siid, piid, code, message
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

    def run_action(self, data: Union[list, dict]) -> Union[list, dict]:
        """
        执行设备动作

        参数:
            data: dict 单个动作 {"did", "siid", "aiid", "value"(可选)} 或 list 批量动作

        返回值:
            Union[list, dict]: 执行结果，包含 did, siid, aiid, code, message
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
