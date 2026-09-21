---
name: miiotpc-api
description: 查询/控制米家账号下的笔记本 PC 设备（是否开机、CPU 温度、电池电量、电源操作）。首选 MCP 工具 mcp__miiotpc__*（返回已解读的中文结果，无需自己翻译枚举）；未注册时退回 miiotpcApi CLI。含 status/isOnline/data_is_live 三维判读规则与主板 EC 上报机制——关机设备的温度电量依然是实时值，不是过期快照。
---

# miiotpcApi — 米家笔记本/PC 设备

查询与控制米家账号下注册的笔记本/PC 设备。

## 第 0 步：判断当前可用的接入方式

**先看工具列表里有没有 `mcp__miiotpc__*` 形态的工具。**

| 情况 | 走哪条路 |
|------|----------|
| 有 `mcp__miiotpc__get_power_status` 等工具 | **路线 A：MCP 工具**（首选） |
| 没有这些工具 | **路线 B：CLI**（兜底） |

两条路的**判读规则完全相同**，见下一章——那是本 skill 最重要的部分，
无论走哪条路都要读。

---

## 判读规则（最重要，两种接入方式通用）

三个字段回答**三个不同的问题**，彼此正交，不可互相替代：

| 字段 | 回答的问题 | 关机（`status: 2`）但联网时 | **真正离线（`isOnline: false`）时** |
|------|-----------|--------------------------|-----------------------------------|
| **`status`** | **OS 现在运行着吗？** | `2`（**判断开关机只看它**） | 无数据（无法判断） |
| `isOnline` | 米家云端认为它联网吗？ | `true`（EC 待机供电，联网模块仍在） | `false` |
| `data_is_live` | 属性数值是不是实时的？ | `true`（EC 仍在上报，**照常查询**） | `false`（**跳过查询，无数据**） |

**判断口径：**

- 想知道**开没开机** → 只看 `status`
- 想知道**数值能不能用** → 只看 `data_is_live`（不是 `status`）
- **`status` 非 8 即非运行中**

### 主板 EC：为什么关机时数值依然是实时的

> **关机 ≠ 数值过期。**

温度与电量由**主板 EC（Embedded Controller）**上报。"关机"只是操作系统停止
运行，EC 始终有待机供电、持续采样，所以关机设备返回的 `temperature` /
`battery_level` **是真实的实时值**，不是断电前的快照。

因此下面这个组合**完全正常且正确**，不要当成矛盾或异常：

```json
{ "isOnline": true, "data_is_live": true, "status": 2,
  "temperature": 33, "battery_level": 59 }
```

含义：这台机器 **OS 已关机**（`status: 2`），但**当前**主板温度 33 °C、电池 59%。

**相反，`isOnline: false` 才意味着没有数值。** 此时云端只剩最后一次上报的过期
快照，任何查询都不会发出、也不会返回数字。正确回答是「设备离线，查不到当前
状态」，**不要编造或推测数值**。

### 枚举值

`status`（MIoT laptop spec）：

| 值 | 含义 | 是否运行中 |
|----|------|:---:|
| `1` | 正在唤醒（Waking Up） | ❌ |
| `2` | 已关机（Power Off） | ❌ |
| `3` | 已睡眠（Sleep） | ❌ |
| `4` | 正在关机（Shutting Down） | ❌ |
| `6` | 正在进入睡眠（Going Sleep） | ❌ |
| `8` | **运行中（Running）** | ✅ |

`charging-state`：

| 值 | 含义 |
|----|------|
| `1` | 插电（AC Power） |
| `2` | 电池供电（Battery Power） |

### 回答模板

**用户问「笔记本开了吗」** → 只看 `status`：

- `8` → 「在运行」
- `2` → 「已关机」
- `3` → 「已睡眠」
- 离线 / 无数据 → 「设备离线，无法判断当前是否开机」

**用户问「现在多少度 / 还有多少电」** → 先看数值新不新鲜：

- 在线（含关机/睡眠）→ 直接给数值；若 `status != 8`，补一句
  「机器目前是关机/睡眠状态，这是主板 EC 上报的实时值」，避免误以为是运行中的工况。
- 离线 → 「设备已离线，无法查询当前温度/电量」，**不要编造数值**。

---

## 路线 A：MCP 工具（首选）

### 注册（一次性）

```bash
claude mcp add --transport stdio miiotpc \
  -- uvx --from "miiotpcApi[mcp]@latest" miiotpcApi-mcp
```

> **必须带 `@latest`（或固定版本号），不要写裸 `miiotpcApi[mcp]`。**
> 实测裸 spec 会被 uv 解析到 **0.1.0**——旧版本没有 `miiotpcApi-mcp` 入口，
> server 直接起不来。`@latest`、`==0.2.0`、`>=0.2.0` 三种写法均正确解析到 0.2.0。
> 想锁定版本就用 `"miiotpcApi[mcp]==0.2.0"`。

> **0.2.0 已于 2026-09-20 发布到 PyPI**（多源实测：PyPI JSON API 报
> `info.version = 0.2.0`；由 PyPI 版经 stdio 启动的 server，其
> `server_info.version` 同为 0.2.0，5 个工具齐全、无 login 工具、
> 中文经协议传输无乱码）。
>
> 源码仓库内同样可用：`uv run miiotpcApi-mcp`。

### 工具清单

| 工具 | 用途 | 副作用 |
|------|------|--------|
| `list_devices()` | 列出 PC/笔记本：did、名称、型号、联网状态 | 无 |
| `get_power_status(did=None)` | **开了吗**；不传 did 则批量查全部 | 无 |
| `get_full_status(did=None)` | 完整状态：运行 + 温度 + 电量 + 充电 | 无 |
| `set_power(did, action)` | `on` / `sleep` / `off` 电源操作 | **有，需谨慎** |
| `get_device_spec(model)` | 查 MIoT Spec（**免认证**，笔记本走内置） | 无 |

工具在模型侧命名为 `mcp__miiotpc__<工具名>`。

### 使用要点

- **工具返回的是已解读的中文文本，可以直接引用给用户**，不需要自己翻译枚举。
  例如不会只给 `status: 3`，而是给「已睡眠（status=3，非运行中）」。
- **判读规则已写进工具返回值**：关机/睡眠设备的输出会注明温度电量来自 EC、
  是实时值；离线设备的输出会注明无数据、不要推测。
- **没有 login 工具**，这是有意为之——二维码扫码必须由人完成，暴露成工具只会
  诱使调用一个必然阻塞的接口。认证失效时工具会返回提醒用户自行登录的文案。
- **`set_power` 有真实副作用**，会影响用户正在使用的电脑。执行前确认：
  用户确实要求了、did 正确、action 取值无误。**没有 toggle，也没有重启。**
- **电源指令返回成功不等于状态已变**：米家只确认指令被接收，实际状态变更需要
  数秒。不要紧接着断言「机器已经关了」，要确认请再调 `get_power_status`。
- **`get_power_status` 比 `get_full_status` 快**：前者只查 status 一个属性，
  后者查全量。只想知道开没开机就用前者。
- **设备 Spec 不支持某动作时不要重试**，那是硬件/固件限制，向用户说明即可。

---

## 路线 B：CLI 兜底

在没有 MCP 工具时使用。

### 执行方式

| 当前目录 | 命令前缀 |
|----------|----------|
| **在本项目源码仓库内** | `uv run miiotpcApi ...`（本地源码，改完即生效） |
| **仓库外** | `uvx miiotpcApi@latest ...`（**必须带 `@latest`**） |

> 裸 `uvx miiotpcApi` 会静默复用缓存里的旧版本，是「同一命令时好时坏」的
> 最常见原因。永远带 `@latest`，并用 `miiotpcApi -v` 确认实际版本。
>
> `uvx` 与 `uv tool run` 是**同一个命令**（别名），不是两级回退。

实测（2026-09-20）：`uvx miiotpcApi@latest` 解析到 **0.2.0**，
仓库内外能力一致。**Windows 下中文输出已自动处理，无需设置 `PYTHONUTF8`。**

### 关键命令

```bash
miiotpcApi --status                          # 批量：所有笔记本状态（推荐，一条命令）
miiotpcApi --did 2047118207 --status         # 单台
miiotpcApi --list-pc                         # 只列设备，拿 did / 名称，不查属性
miiotpcApi --dev-name "我的笔记本" --power on    # 唤醒/开机
miiotpcApi --dev-name "我的笔记本" --power sleep  # 睡眠
miiotpcApi --dev-name "我的笔记本" --power off    # 关机
miiotpcApi --get-device-info xiaomi.laptop.p59   # 查 MIoT Spec（免认证）
```

（按上表补全前缀。）

**批量 `--status` 优先**，不要先 `--list-pc` 再逐台查——那是 1+N 次调用。

输出是 JSON，`status` / `isOnline` / `data_is_live` 三者都要看，判读规则见上文。

设备真正离线时，0.1.4 起会**跳过属性查询**、字段返回 `null` 并附 `warning`；
更早版本仍会返回云端过期值（`data_is_live: false` + 数值），此时**只报告设备
离线，不要把数值当当前值陈述**。

### 命令约束

- 顶层选项（`--power`、`--status`、`--temperature`、`--battery`、
  `--charging-state`、`--get-prop`、`--list-properties`、`--list-actions`）
  **互斥**，一次只能用一个。
- `--did` 与 `--dev-name` 互斥。
- **电源操作必须指定设备**（没有批量形式），查状态用不带设备参数的 `--status`。
- **电源操作没有 `toggle`**。
- 笔记本只有 4 个属性（`status`/`temperature`/`battery-level`/`charging-state`），
  **全部只读**；`set` 对笔记本必然报错，是预期行为。也没有
  `manufacturer`/`serial-number`/`firmware-revision` 之类的属性。
- `--list-pc` 里的「联网状态」是 `isOnline`，**不代表是否开机**——关机设备照样
  显示「在线」。

---

## 认证（两条路线通用）

认证文件：`~/.config/miiotpc-api/auth.json`，**与接入方式、包版本都无关**。

### 绝对不要替用户登录

**不要调用 `login`，也不要尝试修复认证问题。**

登录流程会在终端显示二维码并**阻塞**等待手机扫码，会把会话一直挂起。
MCP server 因此**根本没有 login 工具**；CLI 侧仍有该子命令，但同样不要调用。

看到 `认证文件不存在` 或 `认证已失效且刷新失败` 时，**停止操作**，提醒用户自行执行：

```bash
uvx miiotpcApi@latest login      # 仓库外
uv run miiotpcApi login          # 源码仓库内
```

### 其他不要替用户做的事

- **不要替用户升级包**。需要升级时提醒用户自行执行
  `uv tool upgrade miiotpcApi`。
- **不要在未明确要求的情况下执行电源操作**。关机/睡眠是不可逆影响用户当前
  工作的动作，必须有明确指令。

---

## 附录：CLI 版本差异

仅在**必须**使用旧版 CLI 时才需要关心。MCP 路线不存在这些问题——server 由
宿主启动一次，没有逐次版本解析、没有控制台代码页问题。

| 版本 | 差异 |
|------|------|
| **0.2.0**（PyPI 当前） | 全能力；新增 MCP server（`miiotpcApi-mcp` 入口 + `mcp` extra）|
| 0.1.4 | CLI 全能力；离线设备跳过查询、属性返回 `null`；**无 MCP 入口** |
| 0.1.3 | 离线设备仍返回云端过期值（`data_is_live: false` + 数值） |
| 0.1.2 | **从未发布**，PyPI 上不存在 |
| 0.1.1 | 无批量 `--status`（报「必须指定 --did 或 --dev-name」）；Windows 中文乱码；`--list-pc` 标签是「状态」 |
| 0.1.0 | 另无内置 laptop spec，新机型报「获取设备型号...的设备信息失败」 |

被迫使用 ≤ 0.1.1 时，Windows 下需手动加 `PYTHONUTF8=1`（bash）或
`$env:PYTHONUTF8 = "1"`（PowerShell），否则设备名变乱码。

固定旧版要显式指定：`uvx "miiotpcApi==0.1.1" ...`。
**不要写 `uvx "miiotpcApi>=x.y.z"`** —— PyPI 上没有的版本会直接 unsatisfiable。

提醒用户升级时只说命令，**不要替用户执行**：

```bash
uv tool upgrade miiotpcApi
```
