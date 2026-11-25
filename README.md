# wuwa-score

鸣潮声骸实时评分工具，使用 Python 源码独立运行。切换单个声骸时，窗口会更新当前评分、理论最高分及词条档位。评分模板可按角色名搜索。

## 安装与启动

在 Windows 10 或 11（Intel / AMD x64）上解压或克隆整个项目，再双击根目录的 **`install.cmd`**。安装需要联网。显示安装完成后，双击 **`start.cmd`** 启动。

安装脚本会复用可用的项目虚拟环境。全新安装从 Python 官网下载 64 位 Python 3.14，核验 SHA-256 后解压到项目的 `.runtime`，再创建 `.venv` 并安装依赖。若原生库无法加载，脚本会尝试安装微软 Visual C++ 运行库，Windows 可能弹出管理员确认。

依赖包自带 PP-OCRv6 small 模型。安装最后会验证图形界面依赖，并在本机运行一次 OCR 自检。

更新代码或移动项目目录后，可以重新运行 `install.cmd`。脚本会处理旧版 PP-OCRv5 依赖。若项目虚拟环境无法使用，会先保留副本，再新建环境。

## 实时评分

1. 「自动」默认开启。识别到右下角的「共鸣者名称＋装配中」后，会选用此共鸣者的模板。同一共鸣者有多套模板时，沿用 OKWW 选最后一套的规则。从详情进入强化页时沿用这一匹配。没有装配角色时使用下拉框中的模板。要指定某一套，取消「自动」再选择。
2. 将鸣潮切到前台，打开简体中文的单个声骸详情或声骸强化页面。推荐使用窗口化或无边框窗口模式。
3. 「画面内评分」默认开启。当前分和理论最高分显示在游戏画面上方，每条词条旁会标出得分，副词条额外显示档位。浮层可以点击穿透，切出游戏或在游戏中离开声骸页面时隐藏。

设置窗口可最小化。需要单独查看设置窗口里的评分表时，可关闭「画面内评分」或开启设置窗口的「置顶」。

主词条按 +25 的数值计分。理论最高分保留已调谐词条及其档位，用不同的最高档有效词条补齐剩余位置。切到其他应用时暂停取图，窗口保留最近的结果。回到鸣潮后恢复识别，离开声骸页面时清空分数。

双暴概率表示保留已调谐副词条、填满五星声骸的五个副词条后，同时获得暴击和暴击伤害的概率。计算按剩余词条类型等概率、不重复抽取。评分窗口和画面内浮层会随识别结果更新。 [库洛调谐概率公示](https://sdk-prod-cdn-aws.kurogame-service.com/pro/agreement/common/language_ko/product_info.pdf#page=3)

最高分概率表示保留已调谐副词条，开满其余位置后恰好达到当前模板所显示的理论最高分的概率。计算使用库洛公示的数值档位概率，计入所有同分的词条类型组合和数值档位。小于 0.01% 的非零概率以科学计数法显示。 [库洛词条档位概率表](https://sdk-prod-cdn-aws.kurogame-service.com/pro/agreement/common/language_ko/product_info.pdf#page=5)

## 截图验证

可以使用游戏客户区的完整截图验证识别和评分。

```powershell
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png'
.\.venv\Scripts\python.exe main.py --image 'E:\截图\声骸.png' --template '嘉贝莉娜-通用'
```

## 来源

评分公式沿用 ok-wuthering-waves。装配角色匹配参考 `slim` 分支的声骸评分插件 0.3.13，OCR 使用 PP-OCRv6 small。内置模板的上游提交号记录在 [templates.json](wuwa_score/templates.json)。

实时输入来自 Windows 可见桌面像素。评分工具的依赖和运行入口均在本项目内。

许可见 [LICENSE.txt](LICENSE.txt)。

## 更新评分模板

安装 Git 后，可在评分窗口点「更新角色权重」。联网拉取后，程序会刷新模板列表，并用新权重重算当前声骸。通过窗体更新无需重启。

也可以在项目目录运行以下命令。第一条查看新增、更新及移除的模板，第二条生成新的模板快照。

```powershell
.\.venv\Scripts\python.exe scripts\update_xwuid_echo_templates.py --check
.\.venv\Scripts\python.exe scripts\update_xwuid_echo_templates.py
```

脚本从 [XutheringWavesUID-Resources](https://cnb.cool/loping151/XutheringWavesUID-Resources) 的 `main` 分支读取全量角色及多模态权重、条件和提交号。资源缓存位于 `cache\xwuid-score-resources`。已有资源检出时，可在命令末尾加 `--no-fetch <资源目录>` 使用本地版本。通过命令行更新后，已打开的评分工具可点一次「更新角色权重」加载新模板。
