# wuwa-score

鸣潮声骸实时评分工具，使用 Python 源码独立运行。切换单个声骸时，窗口会更新当前评分、理论最高分及词条档位。评分模板可按角色名搜索。

## 启动

依赖装好后，双击项目根目录的 `start.cmd`，或在 PowerShell 中运行 `.\start.cmd`。

首次安装需要 Windows 10/11 和 64 位 Python 3.13。在 PowerShell 中执行以下命令。

```powershell
cd E:\projects\wuwa-score
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.cmd
```

安装包自带 PP-OCRv5 模型，OCR 在本机运行，首次识别时会初始化并缓存模型。

## 实时评分

1. 「自动」默认开启。识别到右下角的「共鸣者名称＋装配中」后，会选用此共鸣者的模板。同一共鸣者有多套模板时，沿用 OKWW 选最后一套的规则。从详情进入强化页时沿用这一匹配。没有装配角色时使用下拉框中的模板。要指定某一套，取消「自动」再选择。
2. 将鸣潮切到前台，打开简体中文的单个声骸详情或声骸强化页面。推荐使用窗口化或无边框窗口模式。
3. 保持游戏中的词条区域无遮挡。可以拖动评分窗口，或取消「置顶」。

主词条按 +25 的数值计分。理论最高分保留已调谐词条及其档位，用不同的最高档有效词条补齐剩余位置。切到其他应用时暂停取图，窗口保留最近的结果。回到鸣潮后恢复识别，离开声骸页面时清空分数。

## 截图验证

可以使用游戏客户区的完整截图验证识别和评分。

```powershell
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png'
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png' --template '嘉贝莉娜-通用'
```

## 来源

评分公式沿用 ok-wuthering-waves。装配角色匹配参考 `slim` 分支的声骸评分插件 0.3.13，OCR 使用同款 `onnxocr-ppocrv5` 模型。内置 68 套模板，与该插件所用的 XutheringWavesUID-Resources 快照 `c2bd6cd0036a1065ed56ac23243a7779c8f310e0` 一致。

实时输入来自 Windows 可见桌面像素。评分工具的依赖和运行入口均在本项目内。

许可见 [LICENSE.txt](LICENSE.txt)。
