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

### 可选：GPU OCR

有兼容 NVIDIA 显卡时，手动运行 `powershell -ExecutionPolicy Bypass -File tools/install-gpu.ps1`。脚本将 Paddle GPU 2.6.2、CUDA 11.8 运行库和 cuDNN 8 安装到 `local-data/gpu-runtime`，执行真实 GPU OCR 检查，通过后才写入 `local-data/ocr-runtime.json` 的 `{"device":"gpu"}`。不会替换基础 CPU Python 依赖，也不需要修改系统 CUDA 路径；下载仅发生在手动安装时。

重启应用后生效。日志中的 `OCR device: gpu` 表示使用 GPU；遇到兼容问题可将配置改为 `{"device":"cpu"}` 后重启，或在启动进程前设置环境变量 `HSR_OCR_DEVICE=cpu`。显式指定 GPU 而运行库缺失时会报错，不会悄悄使用 CPU。GPU 与游戏共用显卡，实际速度须以游戏运行时为准。

### 扫描与预览

1. 游戏设为简体中文，进入遗器列表，设好筛选和排序。当前导航适配每行 8 件：滚动到顶部，选中第一行最左侧遗器。
2. 在工具中选择已有模板或创建模板。没有模板也可扫描，但不会产生自动弃置候选。
3. 点击“开始扫描”，在 3 秒内切回游戏。扫描只导航和截图，不标记。
   首件建立面板缓存，之后只截必要的面板区域，在 OCR 识别当前件时最多提前截取下一件。换件必须检测到属性画面变化并稳定；未变化、失焦或布局变化则停止。无法建立可靠缓存时沿用逐件识别。启动切回游戏的 3 秒倒计时和标记阶段的核验等待仍保留。
4. 扫描停止后检查截图、属性和原因。输入本次保留阈值，点击重新评分；没有隐含的旧版 40 分阈值。
5. 勾选确认需要标记的候选，将游戏恢复到本次扫描起点，保持排序不变；点击确认后 3 秒内切回游戏。
6. 每一件都会重新识别、核对身份和保护状态；点击后验证弃置标记。失败停止且不重复点击。

Esc 可停止任务；窗口失焦也会停止。扫描暂停后进入当前结果预览，重新扫描会创建新会话。执行停止后保留进度，要再次执行需重新扫描，防止在不明位置继续。

扫描与执行均按蛇形顺序导航：第一行向右，到末列向下，第二行向左，依次换行。每次开始均重置路径，不能从任意列开始。遇到完全相同的属性或按键未移动仍会保守停止；停止并不保证已遍历全部遗器，尤其须人工检查不满一行的末尾。

自动定位的扫描阶段会缓存首次完整识别的标题、主属性、副属性区域，后续从新截图裁切，避免每件都运行 YOLO。复用前检查窗口位置和大小，以及标题下划线、右上角关闭按钮两个固定标记；检查不通过或 OCR 不完整时重新定位，连续复用 24 次后强制刷新。手动框选不走此缓存。每次扫描重新建立缓存，执行标记时完全禁用缓存并逐件重新检测。

会话 JSON 中每件遗器的 `detection_source` 记录 `fresh/cache`，`timings_ms` 记录截图、定位或缓存检查、OCR 和观察总耗时。扫描模式的总耗时不再包含 PNG 编码，流水线帧的换件与取图时间单独记录为 `capture_wait_ms`，与 OCR 有重叠，不能直接相加当作单件速度。缓存失败后重做的时间记录为 `cache_fallback_ms`。可用 `tools/benchmark_scan.py 截图1.png 截图2.png ...` 离线对比，结果写入 `local-data/cache-benchmark.json`，不会操作游戏。

PNG 压缩与记录写入在后台串行执行，最多保留一个待保存任务，结束前等待写入完成。预览截图主要显示遗器面板。扫描停止时游戏可能比最后一条结果提前一件；执行标记前仍须回到扫描起点。已截取帧的 OCR 重试始终使用原帧，禁止读入已经切换的下一件。

扫描中逐件追加 `.jsonl` 记录，每 50 件及结束时保存完整会话 JSON，避免每件重复复制、写入全部历史；原有 JSON 格式与历史文件保持不变。界面扫描期间仅展示最近 20 件，停止后显示完整清单；截图按需加载缩略图，点击可查看原图。轮询省略原始 OCR 等大字段，磁盘记录仍完整保留。

换件稳定性仅比较标题、主属性的金色文字与副属性的白灰文字，避免面板背景动画持续触发变化。持续未变化或未稳定时仍停止，在 `local-data/diagnostics/switch-timeout-*` 保存截图和逐次差异；可能原因包括相同内容、导航未移动或列表末尾。`capture_polls` 记录取图次数。

标题下划线校验只比对线条主体，忽略周围新增的金色背景像素，并容忍 1 像素渲染偏差；关闭按钮比对白色图形。主属性左侧金色竖线属于可变高亮，不再用于持续布局校验。短暂校验失败会在本件原地重试，不再立即认定布局变化；持续失败时停止，并在 `local-data/diagnostics/panel-layout-*` 保存截图、窗口及参考标记。

OCR 默认先用颜色与像素行投影分出标题、主属性名称/数值及四条副属性名称/数值，共 11 行，统一交给 Paddle 识别器批量处理，跳过五次重复文字检测。行数、名称与数值的对齐、置信度或词典匹配不通过时，回退完整 OCR；灰色词条仍保留颜色与“+3可激活”的双重校验。记录中的 `ocr_path` 为 `batch` 或 `legacy`。启动前设置 `HSR_OCR_BATCH=0` 可禁用快速路径，便于回归比较。

定期刷新 YOLO 漏检时，如果旧缓存仍通过窗口、双锚点与区域边界检查，允许继续用于扫描预览，并记录 `detection_refresh_fallback=true`；无法通过检查则不复用。执行标记仍禁用缓存。每件记录中的 `ocr_device` 明确记载实际初始化的 OCR 设备 `cpu/gpu`。

OCR 文字匹配失败不会直接清空位置缓存。重新定位失败时，必须重新通过窗口、固定标记与边界校验才能复用；重试后仍有未知文字则保留为待确认，不无限重试，也不强行纠正名称。

标题含 OCR 字典未收录的字时（例如“勇烈的玄枵面甲”的“枵”），额外识别套装名与部位。二者都须精确匹配已知名称、置信度至少 0.95，且唯一对应同一遗器，才使用其标准名称；记录 `title_source=set_part` 与交叉识别证据。无法满足条件仍显示未知，不使用模糊替换。

本地名称与实际识别器字符表核对发现，当前未收录字为“鞲、枵、坼、辔、桹”，统一走上述套装与部位交叉识别。如果标题和套装名都恰好漏了同一个汉字（例如“莳者”两处都漏“莳”），要求两处其余文字完全一致、部位精确且候选唯一后才能恢复名称；不接受替字、多个漏字或低置信度结果，原文和匹配方式保留在证据中。只有标题未知不会再触发重复 YOLO 定位。

扫描模式下常规定位缺少文字区域时，会以 1280 输入尺寸补检测一次，仅补缺失区域，保持原有置信度门槛；已有区域及弃置点击目标不被补检测覆盖。

主属性仍缺失时，扫描预览允许使用置信度至少 0.65 的候选，但必须同时通过高置信度标题、副属性的位置关系及金色竖线验证。保留实际置信度，低于 0.8 的结果标为待确认、禁止自动弃置；执行阶段不启用此兜底。

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

推荐使用首页的“本机状态校准”：

1. 游戏中选中一件已知状态的遗器，点击“截取当前遗器”，3 秒内切回游戏。截图后切回工具；此过程不切换、不修改遗器。
2. 本自用版按用户确认全部按五星处理，不进行星级识别。仅为锁定、装备、弃置制作已/未状态模板。拖动框选区域后保存，同一字段沿用同一位置。锁定/弃置紧贴白色图标；装备选固定状态文字、避开角色头像。图形匹配有歧义时返回未知。
3. 换其他遗器截图，仅填写锁定、装备、弃置并独立验证。不限定截图数量，界面提示尚缺哪些正反状态。模板截图不能用于验证，重复截图不重复计入。词条生效沿用颜色与激活提示自动识别，不参与本机人工校准；无法确认时仍禁止自动标记。
4. 全部通过后完成校准，再重新扫描。修改模板或验证失败会撤销已验证状态；失败后需重新验证。校准前的旧扫描记录不会自动改成已验证。

状态与匹配证据保存在扫描记录中；首页显示“按五星处理（用户设定）”、锁定、装备、弃置及验证状态。星级来源记为 `user_assumed`，不冒充识别结果。校准截图保存在 `local-data/calibration`，修改前备份配置至其 `backups` 子目录。模板保存在 `local-data/templates`，整体备份 `local-data` 即可。

下列命令行工具用于旧的手工模板流程；界面校准可替代它：

`tools/calibrate_states.py` 不操作游戏，只裁剪已有截图。示例（坐标必须替换为实际标记区域）：

```powershell
.\local-data\python\python.exe tools/calibrate_states.py add locked.png --field locked --state true --rect 100 100 24 24
.\local-data\python\python.exe tools/calibrate_states.py add unlocked.png --field locked --state false --rect 100 100 24 24
```

字段为 `locked/equipped/discarded`（true/false）和 `activation0` 至 `activation3`（active/pending/unknown）。每个字段必须有正反模板；框选状态标记区域，避免包含随遗器变化的文字。未命中或多个模板相似均返回未知。

准备覆盖所需状态的独立验证截图与 JSON 数组，每项形如：

```json
{
  "image": "cases/relic-01.png",
  "expected": {
    "locked": false, "equipped": false, "discarded": false,
    "activation0": "active", "activation1": "active",
    "activation2": "active", "activation3": "pending"
  }
}
```

布尔状态须覆盖正反例；前三条覆盖 active，第四条覆盖 active/pending。不要用训练模板原图冒充独立验证集。核验实际强化规则后运行：

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
