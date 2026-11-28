# wuwa-score

鸣潮声骸实时评分工具。在游戏画面里查看当前分、各词条得分和副词条档位，也能看到继续调谐的理论最高分和概率。

## 安装与启动

需要 Windows 10 或 11（Intel / AMD 64 位）。安装时需要联网，脚本会准备 Python 和所需组件。

1. 在 GitHub 的 Releases 页面打开最新版本，在「Assets」下下载 `wuwa-score-v版本号-windows-x64.zip`。还没有发布版本时，可在仓库首页点击「Code」→「Download ZIP」。 [打开 Releases](https://github.com/IceHe/wuwa-score/releases)
2. 把 ZIP 解压到自己有写入权限的位置，例如 `D:\Tools\wuwa-score`。**包含 `install.cmd` 的文件夹就是安装目录**，Python 和所需组件也会放在里面。
3. 打开该文件夹，双击 `install.cmd`，等到出现 `Installation complete`。
4. 双击同一文件夹里的 `start.cmd`。以后直接双击 `start.cmd` 即可。

**通常无需管理员权限。** 只有脚本尝试补装微软 Visual C++ 运行库时，Windows 才会提示管理员授权。没有管理员权限时，可以请电脑管理员协助补装，再运行 `install.cmd`。

如果移动了项目文件夹，在新位置重新运行一次 `install.cmd`。

## 使用方法

1. 将鸣潮切到前台，打开简体中文的单个声骸详情或强化页面。推荐使用窗口化或无边框窗口模式。
2. 评分会出现在游戏画面上。想在工具窗口查看评分时，可以关闭「画面内评分」或打开「置顶」。
3. 模板默认按声骸的装配角色自动匹配。要手动指定，取消勾选「自动」，输入角色名或模板名的一部分，再从下拉列表选择。模板名后的「自动匹配」和「用户指定」表示当前模板的选择方式。

切换声骸时会先收起旧分数，显示「正在分析新声骸…」。新面板识别完成后再显示评分。

识别默认使用 CPU。评分窗口的「优先使用 GPU」可在运行中切换，旁边会显示所用的设备。检测不到可用 GPU 时，选项会置灰。旧版本升级后，重新运行 `install.cmd` 即可补装 GPU 识别所需的组件。

理论最高分保留已调谐的词条，估算剩余位置都开到最佳时的分数。「双暴概率」和「理论最高分概率」分别表示开满副词条后同时拥有暴击与暴击伤害、达到理论最高分的概率。

已安装 Git 时，点击「更新角色权重」可联网更新评分模板，更新后立即生效。

## 作者与致谢

`wuwa-score` 由 IceHe 开发和维护。 [GitHub 项目主页](https://github.com/IceHe/wuwa-score)

- 感谢 ok-oldking 和 OKWW 的贡献者。实时识别和声骸评分参考了 OKWW 的实现。 [OKWW](https://github.com/ok-oldking/ok-wuthering-waves)
- 感谢 Loping151、tyql688 和 XW-UID 的贡献者。角色评分模板来自 XW-UID 的资源仓库。 [XutheringWavesUID](https://github.com/Loping151/XutheringWavesUID) · [评分资源](https://cnb.cool/loping151/XutheringWavesUID-Resources)

本项目程序代码采用 AGPL-3.0。各上游项目的许可及角色权重来源见第三方许可说明。 [许可证](LICENSE.txt) · [第三方许可](NOTICE.md) · [技术说明](docs/technical.md)
