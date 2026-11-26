# wuwa-score 技术说明

日常安装与使用见 [项目首页](../README.md)。

## 安装脚本与运行环境

`install.cmd` 调用 Windows PowerShell 运行 `scripts/install.ps1`。脚本以自身所在 `scripts` 目录的上一级作为项目根目录，可以从任意工作目录调用。

脚本优先复用可用的 `.venv`。全新安装时从 Python 官网下载 64 位 Python 3.14，核验 SHA-256 后解压到项目的 `.runtime`，再创建 `.venv` 并安装依赖。现有虚拟环境无法使用时，脚本会先保留副本，再新建环境。脚本也会处理与新版 OCR 包共用模块目录的旧版 PP-OCRv5 依赖。

安装时会检查 OpenCV 和 OpenVINO 能否加载。如果检查触发 Visual C++ 运行库的补装，脚本会下载并验证微软安装程序的签名，再请求管理员授权。最后验证 Tk 图形界面依赖并运行一次本地 OCR 自检。

## 截图与识别

实时输入来自 Windows 可见桌面像素。OCR 使用依赖包自带的 PP-OCRv6 small 模型。切到其他应用时暂停取图，窗口保留最近的结果。回到鸣潮后恢复识别，离开声骸页面时清空分数。画面上的评分浮层支持鼠标点击穿透。

可以在项目目录使用游戏客户区的完整截图验证识别和评分。

```powershell
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png'
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png' --template '嘉贝莉娜-通用'
```

## 评分与概率

评分公式沿用 `ok-wuthering-waves`。装配角色匹配参考 `slim` 分支的声骸评分插件 0.3.13。识别到「共鸣者名称＋装配中」时按角色选择模板。同一角色有多套时选最后一套，从详情进入强化页时沿用这次匹配。未识别到装配角色时使用下拉框选定的模板。

主词条按 +25 的数值计分。理论最高分保留已调谐词条及其档位，用尚未出现的词条类型按各自最高档得分补齐剩余位置。

- **双暴概率**按剩余词条类型等概率、不重复抽取，计算五星声骸开满五条副词条后同时拥有暴击和暴击伤害的概率。 [库洛调谐概率公示](https://sdk-prod-cdn-aws.kurogame-service.com/pro/agreement/common/language_ko/product_info.pdf#page=3)
- **理论最高分概率**使用库洛公示的数值档位概率，计入所有能达到理论最高分的词条类型组合和数值档位。小于 0.01% 的非零概率以科学计数法显示。 [库洛词条档位概率表](https://sdk-prod-cdn-aws.kurogame-service.com/pro/agreement/common/language_ko/product_info.pdf#page=5)

## 模板维护

更新脚本从 XutheringWavesUID-Resources 的 `main` 分支读取全量角色和各形态的权重及条件，资源缓存位于 `cache\xwuid-score-resources`。生成的 `wuwa_score/templates.json` 记录上游提交号。 [上游资源仓库](https://cnb.cool/loping151/XutheringWavesUID-Resources) · [模板快照](../wuwa_score/templates.json)

在项目目录运行以下命令。第一条查看新增、更新和移除的模板，第二条生成新的模板快照。

```powershell
.\.venv\Scripts\python.exe scripts\update_xwuid_echo_templates.py --check
.\.venv\Scripts\python.exe scripts\update_xwuid_echo_templates.py
```

如果本机已有上游资源检出，可以在命令末尾加 `--no-fetch <资源目录>`。通过评分窗口的「更新角色权重」按钮更新时，程序会重新加载模板并重算当前声骸。通过命令行更新后，已打开的窗口可点一次该按钮加载新的权重。

## 发布 Windows ZIP

发布需要手动启动。先把要发布的提交推送到 `main`，再在 GitHub 的「Actions」中打开「Publish Windows ZIP」，点击「Run workflow」，选择 `main` 后确认运行。也可用 GitHub CLI 启动。

```powershell
gh workflow run release.yml --ref main
```

工作流在开始时按北京时间生成日历版本号，月份和日期补零。当天首版只用日期，例如 `2026.11.26`。同日后续版本从 `.1` 开始，在已有标签的最大序号上加一。旧格式的 `.0` 标签同样计为当天首版。次日首版只用新日期，例如 `2026.11.27`。每次只执行一个发布任务，避免取到相同的版本号。

工作流为所选提交创建标签（如 `v2026.11.26`），并在 Release 的「Assets」下附上 `wuwa-score-v2026.11.26-windows-x64.zip`。推送代码或标签均不会触发发布。目标电脑解压后仍需运行 `install.cmd` 联网安装依赖。
