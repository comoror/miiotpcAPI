# 测试策略

## 测试框架

使用 **pytest**，作为可选开发依赖声明在 `pyproject.toml` 中：

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0"]
```

> 早期草稿曾写「使用 Python 内置 unittest，不引入额外测试依赖」，但代码示例与
> 实际实现均为 pytest。本文档已更正为与实现一致。

## 运行测试

```bash
# 全部测试
uv run --extra dev pytest tests/ -v

# 单个文件
uv run --extra dev pytest tests/test_cli.py -v

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
├── test_api.py      # find_pc_devices 关键词筛选逻辑
├── test_device.py   # PCDevice.status 语义（核心回归防护）
└── test_cli.py      # 参数解析、设备列表输出、UTF-8 重配置、一致性守护
```

所有用例**不联网**：`miiotpcAPI` 与 `PCDevice` 均通过 `object.__new__` 构造，
注入桩对象替代真实设备与网络请求。

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

### test_api.py — 设备筛选逻辑

`find_pc_devices()` 是 `--list-pc` 能否找到设备的**唯一**依据，覆盖：

- 默认关键词 `pc`/`电脑`/`笔记本`/`laptop`/`desktop`/`notebook` 每一个都生效
- 匹配大小写不敏感（`MY LAPTOP` 能命中）
- 名称与 model 任一命中即可
- **无关键词命中时返回空列表** —— skill 文档记载的已知坑：
  设备名不含 PC 关键词时 `--list-pc` 为空，应改用 `--list-devices`
- 自定义 `keyword` 是**追加**到默认集合，不覆盖
- 自定义关键词自动转小写
- `name`/`model` 字段缺失时不抛异常
- 返回的是原始设备字典，字段不被改写

## 测试原则

1. **不联网**：所有对外部 API 的调用用桩对象替代，不发送真实请求
2. **不测试加密逻辑**：`miutils.py` 直接复用自 mijiaAPI，不重复测试
3. **不测试认证流程**：`login()` 需要真实扫码，属人工流程，禁止在测试中触发
4. **锁定语义而非实现细节**：`data_is_live` 这类语义一旦变更必须是显式决策，
   测试的作用是让这种变更无法悄悄发生
5. **守护文档与代码的一致性**：枚举值、版本号这类分散在多处的信息，
   用测试强制对齐

## 已知局限

- **`tests/` 不覆盖真实设备交互**：桩对象无法发现米家云端行为变化
  （例如某个 model 的 Spec 变更）。这类问题只能靠实机调用发现。
- **PowerShell 形态的 CLI 调用未纳入测试**：pytest 只跑 Python 进程内逻辑，
  文档中的 PowerShell 管道示例需人工验证。
- **`get`/`set`/`action` 的网络错误路径未覆盖**：这些路径需要 mock
  `requests` 会话，当前测试集未包含。
