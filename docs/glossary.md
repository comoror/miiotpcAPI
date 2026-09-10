# 术语表

## 核心概念

| 术语 | 英文 | 说明 |
|------|------|------|
| MIoT Spec | MIoT Specification | 小米IoT设备规范协议，定义设备的属性和动作 |
| did | Device ID | 设备唯一标识符，由小米平台分配 |
| model | Model | 设备型号，格式如 `brand.category.name`（如 `yeelink.light.lamp4`） |
| siid | Service ID | MIoT Spec 中的服务ID，标识设备的一个功能模块 |
| piid | Property ID | MIoT Spec 中的属性ID，标识服务下的一个属性 |
| aiid | Action ID | MIoT Spec 中的动作ID，标识服务下的一个动作 |
| RC4 | Rivest Cipher 4 | 小米API使用的流加密算法 |
| nonce | Number used ONCE | 一次性随机数，用于加密签名 |
| signed nonce | Signed Nonce | 由 ssecurity 和 nonce 经 SHA256 生成的签名值 |
| ssecurity | Session Security | 会话密钥，用于加密和签名 |
| serviceToken | Service Token | 服务令牌，用于API认证 |
| passToken | Pass Token | 通行证令牌，用于登录认证 |

## MIoT Spec 属性相关

| 术语 | 英文 | 说明 |
|------|------|------|
| prop | Property | 设备属性，如开关状态、亮度、温度 |
| DevProp | Device Property | miiotpcApi 中的属性描述符类 |
| rw | Read/Write | 属性的读写权限：`r`=只读, `w`=只写, `rw`=读写 |
| value-list | Value List | 属性的枚举值列表 |
| value-range | Value Range | 属性的数值范围 [min, max, step] |

## MIoT Spec 动作相关

| 术语 | 英文 | 说明 |
|------|------|------|
| action | Action | 设备动作，如开机、重启、锁屏 |
| DevAction | Device Action | miiotpcApi 中的动作描述符类 |
| params | Parameters | 动作的输入参数 |

## 设备类型

| 术语 | 英文 | 说明 |
|------|------|------|
| MiotDevice | MIoT Device | 通用MIoT设备封装，适用于所有米家设备 |
| PCDevice | PC Device | PC/笔记本设备高层封装，提供语义化控制接口 |
| shared device | Shared Device | 被共享给当前用户的设备（非主设备） |

## API 相关

| 术语 | 英文 | 说明 |
|------|------|------|
| miiotpcAPI | MIoT PC API | 本包的核心API客户端类 |
| session | Session | requests.Session 实例，管理HTTP连接和Cookie |
| auth data | Authentication Data | 认证数据，存储在 auth.json 中 |
| token refresh | Token Refresh | 刷新过期的 serviceToken |
| long polling | Long Polling | 长轮询，用于等待扫码登录响应 |

## 错误相关

| 术语 | 英文 | 说明 |
|------|------|------|
| error code | Error Code | 小米IoT平台返回的数字错误码 |
| APIError | API Error | API请求失败时抛出的异常 |
| LoginError | Login Error | 认证失败时抛出的异常 |

## 加密相关

| 术语 | 英文 | 说明 |
|------|------|------|
| nonce | Nonce | 8字节随机数 + 4字节时间戳的Base64编码 |
| signed nonce | Signed Nonce | SHA256(ssecurity + nonce) 的Base64编码 |
| RC4 encrypt | RC4 Encryption | 小米API使用的加密方法，跳过前1024字节 |
| HMAC-SHA1 | HMAC-SHA1 | 用于生成请求签名的哈希算法 |
| GZIP | GNU ZIP | 响应数据的压缩格式 |

## 文件路径

| 术语 | 英文 | 说明 |
|------|------|------|
| auth_path | Auth Path | 认证文件路径，默认 `~/.config/miiotpc-api/auth.json` |
| cache_path | Cache Path | MIoT Spec 缓存目录，跟随 auth_path 的父目录 |
| pyproject.toml | Python Project Config | Python项目配置文件 |
