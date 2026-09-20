# 测试策略

## 测试框架

使用 **pytest**，作为可选开发依赖声明在 `pyproject.toml` 中：

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "mcp>=2",      # test_mcp_server.py 需要；CLI 用户不会被强制安装
]
```

> 早期草稿曾写「使用 Python 内置 unittest，不引入额外测试依赖」，但代码示例与
> 实际实现均为 pytest。本文档已更正为与实现一致。

`mcp` 只出现在 `dev` 与 `mcp` 两个 extra 里，**不在主依赖中**：只用 CLI 的用户
不需要 MCP SDK。`__init__.py` 不得导入 `mcp_server`，这条由
`TestConsistency.test_package_init_does_not_import_mcp_server` 守护。

## 运行测试

```bash
# 全部测试
uv run --extra dev pytest tests/ -v

# 单个文件
uv run --extra dev pytest tests/test_mcp_server.py -v

# 指定测试类
uv run --extra dev pytest tests/test_device.py::TestStatusSemantics -v

# 指定用例
uv run --extra dev pytest tests/test_cli.py::TestForceUtf8Stdio -v

# 只跑回归防护（status 判读语义）
uv run --extra dev pytest tests/ -k "StatusSemantics or Consistency" -v
```

pytest 是可选依赖，声明在 `dev` extra 中。**全新环境（刚 clone、venv 未装 dev 依赖）
下必须带 `--extra dev`**，否则报 `Failed to spawn: pytest`。

注意：一旦用 `--extra dev` 跑过一次，pytest 会留在 venv 里，之后裸 `uv run pytest`
也能用。所以「不带 `--extra dev` 就会失败」只在全新环境下成立，
换机器或重建 venv 时仍需加上。

## 测试结构

```
tests/
├── test_api.py         # find_pc_devices 关键词筛选逻辑          17 个
├── test_device.py      # PCDevice.status 语义（核心回归防护）    40 个
├── test_cli.py         # 参数解析、设备列表输出、UTF-8、一致性   37 个
└── test_mcp_server.py  # MCP server 渲染层与工具层               85 个
```

合计 **179 个用例**，全部**不联网**。API 层一律通过 `object.__new__` 构造并注入
桩方法，替代真实设备与网络请求。

## 各文件覆盖范围

### test_device.py — status 判读语义

这是全项目最关键的一组回归防护，锁定了 v0.1.3 确认的三维判读规则：

| 字段 | 含义 | 关机时 |
|------|------|--------|
| `status` | **OS 运行状态**，8=运行中，**非 8 即非运行中** | `2`（唯一开关机判据） |
| `isOnline` | 米家上报的联网状态 | `true`（EC 待机供电，联网模块仍在） |
| `data_is_live` | 属性值是否实时 | `true`（EC 仍在上报） |

关键用例 `test_powered_off_but_online_still_reports_live_values` 锁定一条容易被
"修好"的事实：**OS 关机 ≠ 数值过期**。温度与电量由主板 EC 上报，EC 始终有
待机供电并持续采样，所以 `isOnline=True` + `status=2` 时 `data_is_live` 依然为
`True`，且不应出现 `warning`。只有设备真正离线（断网/拔电）时 `data_is_live`
才为 `False`。

同时覆盖：

- `status` 字段对 MIoT 枚举 1/2/3/4/6/8 的透传
- `pc.is_on()` 的判据是 `status == 8`
- 返回的 `capabilities` 是副本，外部改动不污染内部状态
- 单个属性读取失败时内联为 `<读取失败: ...>` 字符串，不中断整体查询
- 取值走 MIoT 原始属性名（`battery-level`）而非语义名（`battery_level`）
- docstring 必须写全枚举、包含「非 8 即非运行中」和 EC 机制说明

**v0.1.4 新增：离线设备跳过查询**

真正离线（`isOnline=False`，断网/拔电）的设备不再发起属性查询——云端只会返回
最后一次上报的过期值，查询没有意义。`TestOfflineSkipsQuery` 类锁定这一行为。

关键在于断言**查询真的没有发生**，而不只是返回值变了：

```python
class FakeDevice:
    def get(self, prop_name):
        self.get_calls.append(prop_name)   # 记录每一次读取
        ...
```

只检查 `result["temperature"] is None` 是不够的——实现可能只是把过期值改成
`None` 但仍发了请求。所以断言 `pc._device.get_calls == []`。

同一组里还有一条**对照测试** `test_online_powered_off_device_still_queries`：
`isOnline=True` + `status=2`（关机但 EC 在线）时必须照常查询、返回实时值。
这条防止「离线跳过」被过度泛化成「非运行就跳过」——正是本项目最容易搞错的地方。

`pc.is_on()` 离线时返回 `None` 而非 `False`：「查不到」和「确认没开机」是两回事，
返回值类型是 `Optional[bool]`。

### test_cli.py — 参数解析与输出

参数解析：

- `--list-pc` / `-l` / `--status`（含批量形态：不带 `--did`/`--dev-name` 合法）
- `--power on/sleep/off`；非法取值（如 `toggle`）必须 `SystemExit`
  —— 电源操作**没有 toggle**
- `--did` 与 `--dev-name` 互斥
- 顶层动作互斥：`--status` 不能与 `--temperature`/`--battery`/`--charging-state` 并用
- 子命令 `login`/`get`/`set`/`action` 的 `args.command`；`get` 必须带 `--prop-name`
- `-v/--version` 打印版本号并以 0 退出

`print_devices()`：

- 字段标签必须是**「联网状态」**，不是易被误读为开关机的「状态」
- 提供 `note` 时打印「提示: ...」，未提供则不打印
- **列表为空时提前 return，`note` 不打印**（当前行为，测试锁定现状）
- 缺失字段渲染为占位符 `<未命名设备>` / `<未知>`

`force_utf8_stdio()`：

- 同时切换 stdout 与 stderr
- 幂等：重复调用无副作用
- 流没有 `reconfigure`（测试捕获、重定向）时静默跳过
- `reconfigure` 抛 `ValueError`/`OSError` 时被捕获，不影响 CLI 运行
- **`main()` 入口必须调用它** —— 程序化入口（测试、第三方集成直接调
  `main(argv)`）同样需要编码修复

一致性守护：

- `version.py` 与 `pyproject.toml` 的版本号必须一致（不一致会导致发版错位）
- `status` 枚举在 `PCDevice.status` docstring 与 CLI `note` 提示语之间必须一致，
  且都是完整的 `{1,2,3,4,6,8}`

> 该守护用例曾暴露真实缺陷：CLI 提示语写成 `（1 唤醒中 / 2 已关机 ...）`，
> 而 docstring 写成 `1=正在唤醒`，信息相同但记法不一致。现已统一为 `N=label`。

`get` 子命令的离线守卫（v0.1.4）：

CLI 有**两条独立的属性查询路径**，行为必须一致：

| 路径 | 实现 |
|------|------|
| 顶层 `--get-prop` | `handle_pc()` → `PCDevice.get_prop()` |
| `get --prop-name` 子命令 | `handle_get()` → `MiotDevice.get()` |

`TestGetSubcommandOfflineGuard` 用桩替换 `MiotDevice`，断言 `get` 子命令在
离线时不调用 `device.get()` 且不输出属性值，在线时正常查询。

> **这组测试的由来**：v0.1.4 首次实现时只给 `PCDevice.get_prop()` 加了守卫，
> `get` 子命令被漏掉，实测对离线设备仍返回 `temperature = 50`（云端过期值）。
> 当时 92 个测试全绿——因为它们都在测 Python API，没有覆盖用户实际走的
> CLI 子命令路径。教训：**要测用户真正调用的那条路径**，不是测改了的那个函数。

### test_mcp_server.py — MCP server

分两层，各测各的职责：

| 层 | 内容 | 测什么 |
|----|------|--------|
| **渲染函数层** | `render_device_list` / `render_power_status` / `render_full_status` / `render_power_action` / `render_device_spec` | 领域解读逻辑：枚举如何变成中文、离线如何处理、EC 机制如何说明 |
| **工具层** | server 上注册的 `@tool` 函数 | 异常如何翻译成提示、工具元数据（名称/annotations/docstring） |

**渲染层是本模块存在的理由**，也是回归防护的重点：MCP 工具的价值在于
**返回已解读的文本**，而不是裸枚举。所以测试主要断言输出文案，而不是数据结构。

桩的构造方式：`FakeAPI` 用 `object.__new__(miiotpcAPI)` 保留真实的
`find_pc_devices()`（纯逻辑，值得测），只替换三个会触网的方法——
`get_devices_list`、`get_devices_prop`、`run_action`。设备型号一律含
`.laptop.`，这样 `get_device_info()` 走内置 Spec，不访问 `home.miot-spec.com`。

`FakeAPI.queried_props` 记录每次查询命中的语义属性名，用于断言**查了什么**：

```python
def test_only_queries_status_property(self):
    """get_power_status 是电源快速路径，只查 status，不碰温度/电量"""
    fake = FakeAPI([RUNNING], {"1001": {"status": 8, "temperature": 55}})
    render_power_status(fake.api)
    assert fake.queried_props == ["status"]
```

这条用例锁定了 `get_power_status` 与 `get_full_status` 的**设计差异**：
前者回答「开了吗」只查一个属性，后者才查全量。若将来有人图省事让两者都调
`pc.status`，这条会失败。

**关键回归防护：EC 语义在 MCP 输出里同样成立**

```python
def test_sleeping_but_online_still_reports_live_temperature(self):
    values = {"1002": {"status": 3, "temperature": 41, "battery-level": 41}}
    text = render_full_status(FakeAPI([SLEEPING], values).api)
    assert "41 °C" in text   # 睡眠设备的温度是实时值，必须报告
    assert "EC" in text
    assert "不代表运行中的工况" in text
```

与 `test_device.py` 里的对照测试是同一条规则在不同层面的表达：一个锁数据，
一个锁文案。

**离线设备：输出里不得出现任何数值**

```python
def test_offline_device_tool_result_has_no_numbers(self):
    fake = FakeAPI([OFFLINE], {"1003": {"status": 2, "temperature": 34, ...}})
    text = tool_text("get_full_status", {})
    assert "无数据（未查询）" in text
    assert "34" not in text and "51" not in text
```

注意断言的是**数值本身不出现**，不只是「标注了离线」。因为调用方（AI agent）
完全可能忽略标注、直接引用看到的数字。

**结构性安全：不暴露 login 工具**

```python
def test_no_login_tool_exists(self):
    names = {t.name for t in list_tools()}
    assert "login" not in names
    assert not any("login" in n.lower() or "qr" in n.lower() for n in names)
```

这比在文档里写「绝对不要调用 login」可靠：文档是祈使句，工具列表里没有的
东西根本调不了。

**元数据与描述即契约**

- `set_power` 必须 `destructive_hint=True`、`read_only_hint=False`
- 其余工具必须 `read_only_hint=True`
- `server.instructions` 必须包含「非 8 即非运行中」「不是开关机判据」「EC」
  「不提供登录工具」等关键规则
- 每个工具的 docstring 必须包含其对应的判读规则

这些规则会被注入模型上下文，所以**写错等于行为错误**，测试把它们钉住。

**schema 校验发生在工具函数之前**

```python
def test_set_power_invalid_action_rejected_by_schema(self):
    with pytest.raises(ToolError) as exc:
        call_tool("set_power", {"did": "1001", "action": "toggle"})
    assert "'on', 'sleep' or 'off'" in str(exc.value)
```

MCP SDK 用类型注解生成输入 schema 并在调用前校验，所以 `toggle` 这类非法取值
根本到不了业务代码。这比在工具里 try/except 更强——模型在协议层就无法发出
非法调用。渲染函数层仍保留校验（`test_render_layer_still_validates_action_for
_direct_callers`），因为 Python 直接调用时不经过 schema。

**枚举标签以内置 Spec 为唯一权威来源**

```python
def test_status_labels_match_builtin_laptop_spec(self):
    status_prop = next(p for p in LAPTOP_SPEC_PROPERTIES if p["name"] == "status")
    spec_labels = {i["value"]: i["desc_zh_cn"] for i in status_prop["value-list"]}
    assert STATUS_LABELS == spec_labels
```

`LAPTOP_SPEC_PROPERTIES` 来自真机规格，是唯一权威。MCP、CLI、文档三处都要
对齐它，而不是互相抄。

> 充电枚举是例外：Spec 写「插电状态/离电状态」，而给用户看的输出统一用
> 「插电/电池供电」。措辞可以不同，**取值集合必须一致**，见
> `test_charging_labels_cover_all_spec_values`。

> **一个踩过的坑**：判断「包没有导入 mcp_server」时不能用
> `hasattr(miiotpcApi, "mcp_server")`——测试模块自己导入了该子模块，Python 会
> 因此在包对象上设置属性，断言必然失败。要看的是 `__init__.py` 的**源码**。

### test_api.py — 设备筛选逻辑

`find_pc_devices()` 是 `--list-pc` 与 MCP `list_devices` 能否找到设备的
**唯一**依据，覆盖：

- 默认关键词 `pc`/`电脑`/`笔记本`/`laptop`/`desktop`/`notebook` 每一个都生效
- 匹配大小写不敏感（`MY LAPTOP` 能命中）
- 名称与 model 任一命中即可
- **无关键词命中时返回空列表** —— 已知坑：设备名不含 PC 关键词时查询为空，
  MCP `list_devices` 的返回文案会说明这一点
- 自定义 `keyword` 是**追加**到默认集合，不覆盖
- 自定义关键词自动转小写
- `name`/`model` 字段缺失时不抛异常
- 返回的是原始设备字典，字段不被改写

## 测试原则

1. **不联网**：所有对外部 API 的调用用桩对象替代，不发送真实请求
2. **不测试加密逻辑**：`miutils.py` 直接复用自 mijiaAPI，不重复测试
3. **不测试认证流程**：`login()` 需要真实扫码，属人工流程，禁止在测试中触发
   —— MCP server 侧同理，`AuthUnavailableError` 用桩触发，不构造真实缺失的认证
4. **锁定语义而非实现细节**：`data_is_live`、EC 上报这类语义一旦变更必须是
   显式决策，测试的作用是让这种变更无法悄悄发生
5. **守护文档与代码的一致性**：枚举值、版本号这类分散在多处的信息，
   用测试强制对齐
6. **断言「没发生查询」而不只是「返回了什么」**：离线跳过、电源快速路径
   都靠记录调用来验证，只看返回值会被「发了请求但返回 None」骗过
7. **给用户看的文本也是契约**：MCP 输出会被 agent 直接引用，文案错误等同于
   行为错误，所以关键措辞有测试钉住

## 已知局限

- **`tests/` 不覆盖真实设备交互**：桩对象无法发现米家云端行为变化
  （例如某个 model 的 Spec 变更）。这类问题只能靠实机调用发现。
- **MCP 的 stdio 子进程路径不在 pytest 覆盖范围内**：测试通过
  `server.call_tool()` 进程内调用，**没有**起真实子进程走 JSON-RPC。
  该路径已用一次性脚本实机验证（真实设备 + SDK 的 `Client`/`StdioServerParameters`），
  但脚本未纳入仓库。若 server 无法启动、或日志写到 stdout 污染协议流，
  pytest 发现不了。
- **PowerShell 形态的 CLI 调用未纳入测试**：pytest 只跑 Python 进程内逻辑，
  文档中的 PowerShell 管道示例需人工验证。
- **`get`/`set`/`action` 的网络错误路径未覆盖**：这些路径需要 mock
  `requests` 会话，当前测试集未包含。

> **一条与 MCP 相关的隐患，测试无法覆盖**：`logger.py` 使用
> `logging.StreamHandler()`（无参，默认写 **stderr**），所以日志不会污染
> MCP 的 stdout JSON-RPC 流。若将来有人改成显式传 `sys.stdout`，MCP server
> 会立刻失效，而 pytest 全绿。改动 `logger.py` 时必须手工验证 stdio 路径。
