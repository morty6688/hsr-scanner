# HSR Scanner 本地自用版

用途：中文遗器扫描 → 保守评分 → 预览 → 逐件核验并标记弃置。
保留 Tauri/React/FastAPI、模板编辑与本地导入导出；不提供官网、自动更新、自动强化或分解。

## 当前实现与边界

- 已移除上游更新请求、下载提示、签名配置、更新脚本和资源发布工作流。
- 中文 PP-OCRv4 模型已放入 `backend/app/assets/paddle/ch`；运行时不下载模型。
- 游戏词典来自 StarRailRes 固定提交，包含 62 个套装与 98 个角色条目，并保留旧模板角色别名。
- 来源、提交及模型归档校验值见 `backend/app/assets/local_manifest.json`。`game_version: null` 表示尚未核验客户端版本，不代表完整支持最新版本。
- 当前检测模型仍为原 YOLO 权重。没有真实客户端标注截图，未宣称已训练或通过实机测试。
- 生效状态、五星、锁定、装备、弃置状态缺少本机校准时保持未知，不进入自动标记清单。
- 导航暂沿用游戏列表的 D 键。遇到重复内容、识别错误、失焦或超时停止；重复不等于保证完整遍历背包，预览页会提示核对。
- 扫描范围仅针对五星遗器；词条未知、角色模板未覆盖均不会自动弃置。

## 首次安装

需要 Windows x64、Node/pnpm、Rust，以及 Visual Studio Build Tools 的 C++ 桌面开发组件（包括 MSVC 和 Windows SDK）。本机若提示 `link.exe not found`，须先安装该组件。

在项目根目录运行 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install.ps1
pnpm install
pnpm tauri dev
```

安装脚本仅在你手动执行时联网安装锁定依赖。它将附带 Python 3.9 复制到被 Git 忽略的 `local-data/python`，不修改项目自带的基础运行时。`tools/requirements.txt` 是完整依赖锁定清单；不要直接将 PaddleOCR 升级到 3.x。

以后直接 `pnpm tauri dev`。也可 `pnpm tauri build --no-bundle`；本机编译的程序引用此项目的绝对路径，移动项目后应重新编译，不用于分发。

后端独立诊断：

```powershell
.\local-data\python\python.exe backend/main.py
```

启动只加载本地模型和数据。缺失资源会报出路径，不会自动修复或下载。若需重新准备资源，手动执行以下联网命令（会更新本地词典，先备份）：

```powershell
.\local-data\python\python.exe tools/prepare_local_assets.py
```

## 使用

1. 游戏设为简体中文，进入遗器列表，设好筛选和排序。当前导航适配每行 8 件：滚动到顶部，选中第一行最左侧遗器。
2. 在工具中选择已有模板或创建模板。没有模板也可扫描，但不会产生自动弃置候选。
3. 点击“开始扫描”，在 3 秒内切回游戏。扫描只导航和截图，不标记。
4. 扫描停止后检查截图、属性和原因。输入本次保留阈值，点击重新评分；没有隐含的旧版 40 分阈值。
5. 勾选确认需要标记的候选，将游戏恢复到本次扫描起点，保持排序不变；点击确认后 3 秒内切回游戏。
6. 每一件都会重新识别、核对身份和保护状态；点击后验证弃置标记。失败停止且不重复点击。

Esc 可停止任务；窗口失焦也会停止。扫描暂停后进入当前结果预览，重新扫描会创建新会话。执行停止后保留进度，要再次执行需重新扫描，防止在不明位置继续。

扫描与执行均按蛇形顺序导航：第一行向右，到末列向下，第二行向左，依次换行。每次开始均重置路径，不能从任意列开始。遇到完全相同的属性或按键未移动仍会保守停止；停止并不保证已遍历全部遗器，尤其须人工检查不满一行的末尾。

不要使用会随着标记立即移除遗器的过滤条件。若列表变化，程序会停止，不自动寻找其他位置。

## 四词条评分

中文副属性预览结合 OCR 行位置与文字颜色识别生效状态：亮白文字为已生效；第 4 行须同时呈灰色并明确识别到“（+3可激活）”才判定为待解锁，解锁占用一次强化机会。灰色但缺少提示、颜色或文字不明确时仍为未知。该识别不代表锁定、装备、星级等状态已经通过本机校准。

旧 YOLO 模型的低置信度副属性框仅用于预览（还须通过与主属性框的位置检查），不允许自动标记。OCR 会对低置信度文字进行对比度处理后重读，保留原始与重读结果，不通过模糊匹配修改数字。识别失败截图保存在 `local-data/diagnostics`。

屏幕显示四条不被当作四条均生效：

- `active`：计入当前分。
- `pending`：不计入当前分，按已知属性计入潜力；不再计算随机补出第四条的概率。
- `unknown`：当前分显示待确认，禁止自动标记。

待解锁是否占一次强化机会由本机核验配置的 `pending_unlock_cost`（0 或 1）决定，未确认时不推断。
潜力采用偏保守的上界，不是强化期望或成功概率；只要任一适用模板的上界达标便保留。速度、双暴散件、速度鞋、能量绳与治疗主属性有额外保留规则。
旧阈值不与新算法等价。详见 `PotentialScore.md`。

## 本机状态校准

所有状态模板来自游戏客户区原尺寸截图。窗口大小和 DPI 改变后重新校准。没有配置时可以扫描预览，但自动标记保持关闭。

`tools/calibrate_states.py` 不操作游戏，只裁剪已有截图。示例（坐标必须替换为实际标记区域）：

```powershell
.\local-data\python\python.exe tools/calibrate_states.py add locked.png --field locked --state true --rect 100 100 24 24
.\local-data\python\python.exe tools/calibrate_states.py add unlocked.png --field locked --state false --rect 100 100 24 24
```

字段为 `locked/equipped/discarded`（true/false）、`rarity`（2–5）和 `activation0` 至 `activation3`（active/pending/unknown）。每个字段必须有正反模板；框选状态标记区域，避免包含随遗器变化的文字。未命中或多个模板相似均返回未知。

准备至少 12 张独立验证截图与 JSON 数组，每项形如：

```json
{
  "image": "cases/relic-01.png",
  "expected": {
    "locked": false, "equipped": false, "discarded": false, "rarity": 5,
    "activation0": "active", "activation1": "active",
    "activation2": "active", "activation3": "pending"
  }
}
```

布尔状态须覆盖正反例，星级覆盖五星与非五星；前三条覆盖 active/unknown，第四条覆盖 active/pending。不要用训练模板原图冒充独立验证集。核验实际强化规则后运行：

```powershell
.\local-data\python\python.exe tools/calibrate_states.py verify cases.json --unlock-cost 1
```

这里的 `1` 只是命令示例，必须按客户端实际行为填写。全部样本通过后才设置 `client_verified`。增加或修改模板会清除该标志。当前仓库没有真实截图或已验证的状态配置。

## 本地数据与旧模板

- `local-data/scanner.db`：用户模板和配置。首次启动通过 SQLite backup 从旧数据库复制，旧文件不动。
- `local-data/sessions`：扫描截图、原始 OCR、规则快照、评分原因和执行结果。
- `local-data/recognition.json` 与 `templates`：本机视觉校准。
- `local-data/python`：独立运行时。

这些内容不提交 Git；手动备份 `local-data` 即可。旧模板字符串使用冻结的旧键顺序解码，新导出格式携带键表，避免数据新增或排序变化造成错配。新格式不会兼容原上游程序。

离线重算保存会话（不加载模型、不操作游戏）：

```powershell
.\local-data\python\python.exe tools/reprice_session.py local-data/sessions/会话ID.json --threshold 0.5
```

## 验证

```powershell
$env:PYTHONPATH = 'backend'
.\local-data\python\python.exe -m unittest discover -s backend/tests -v
pnpm build
cargo check --manifest-path src-tauri/Cargo.toml
```

当前自动化测试涵盖四词条状态、未知不弃置、潜力保护、会话变化、失焦、停止、重复内容和点击失败。实机验收还需完成：真实截图回归、YOLO 定位检查、未强化到首次强化的状态变化、小批量标记与停止核验、中文路径启动及关闭进程检查。

## 来源

- 上游代码：[mumawQAQ/hsr-scanner](https://github.com/mumawQAQ/hsr-scanner)
- 游戏数据：[Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes)
- 中文识别模型：[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)

保留上游学习交流、非商业用途说明；数据与模型的权利归各自原作者。
