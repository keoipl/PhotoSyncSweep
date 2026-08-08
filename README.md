<div align="center">
  <img src="docs/images/app-icon.png" width="150" alt="Photo SyncSweep 图标">
  <h1>Photo SyncSweep 照片联动清理助手</h1>
  <p>根据同名 JPG / RAW 的保留结果，安全整理照片文件与 XMP 边车文件。</p>
  <p><a href="README_EN.md">English</a> · <a href="https://github.com/keoipl/Photo-SyncSweep/releases">下载最新版</a></p>
</div>

![Version](https://img.shields.io/badge/version-1.0.0-6FAF7B)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-6FAF7B)
![Architecture](https://img.shields.io/badge/architecture-x64-6FAF7B)
![Python](https://img.shields.io/badge/source-Python%203.12%2B-6FAF7B)

## 软件简介

Photo SyncSweep 是一款面向摄影筛片工作流的 Windows 桌面工具。你可以先在 JPG 中完成筛选并删除废片，再让程序找出没有同名 JPG 的 RAW；也可以反向根据 RAW 整理 JPG，或自行定义任意“依据格式 → 待整理格式”。

程序始终先扫描和预览，不会在扫描时直接处理照片。正式执行前，每个候选文件都能单独取消勾选。

## 主要功能

- 三种匹配模式：`JPG → RAW`、`RAW → JPG`、自定义格式。
- 支持 Sony ARW、Canon CR3、Nikon NEF 等预设，并可保存自定义方案。
- 扫描后默认选中全部候选文件，每个文件可单独勾选或取消。
- 支持移动到暂存文件夹、复制到暂存文件夹、移入 Windows 回收站。
- 可选联动处理同名 XMP 文件，默认关闭。
- 候选数量超过目标文件总数的 80% 时显示醒目警告并二次确认。
- 支持同一文件夹、不同文件夹以及递归扫描子文件夹。
- 移动和安全复制操作支持撤销，不覆盖已有同名文件。
- 英文、中文合并在同一个程序中，可一键切换并记住语言。
- Windows 11 / Fluent 2 风格界面，淡绿色主题。
- 完全本地运行，无遥测、无自动上传。

## 下载与运行

1. 打开 [Releases](https://github.com/keoipl/Photo-SyncSweep/releases)。
2. 下载 `Photo SyncSweep 照片联动清理助手.exe` 或 Windows x64 压缩包。
3. 双击 EXE 运行，无需安装 Python。

当前发布版适用于 64 位 Windows 10/11。程序暂未进行商业代码签名，首次运行可能出现 Windows“未知发布者”提示；确认下载来源后，可选择“更多信息 → 仍要运行”。

## 基本使用流程

1. 选择整理方案或匹配方向。
2. 选择依据文件夹和待整理文件夹；两种格式位于同一目录时启用“JPG 与 RAW 在同一文件夹”。
3. 设置暂存文件夹和处理方式。
4. 点击“扫描并预览”。
5. 检查候选列表，取消不希望处理的文件。
6. 确认数量与路径无误后执行。

建议第一次使用时先复制少量照片进行测试。

## 匹配示例

假设文件夹中原本有：

```text
DSC001.JPG
DSC001.ARW
DSC002.ARW
```

使用 `JPG → RAW` 模式扫描时，`DSC002.ARW` 因为没有同名 JPG，会成为待整理候选；`DSC001.ARW` 不会被处理。

## 安全设计

- 扫描与执行分离，先预览再操作。
- 每个候选文件可以单独取消。
- 超过 80% 时触发高风险警告。
- 暂存目录中的同名文件不会被覆盖。
- 递归模式保留相对目录结构，减少同名冲突。
- XMP 联动默认关闭。
- 配置和日志保存在 `%APPDATA%\PhotoRawSync`，不会写入照片目录。

## 从源码运行

需要 Windows、Python 3.12 或更高版本，以及随 Python 安装的 Tkinter：

```powershell
$env:PYTHONPATH = "src"
python src/photo_syncsweep_standalone.py
```

运行测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

生成独立 EXE：

```powershell
.\build.ps1
```

## 隐私

软件不会上传照片、文件名、路径或使用数据，也不会自动访问网络。只有用户主动点击界面中的 GitHub 按钮时，系统浏览器才会打开作者主页。详见 [PRIVACY.md](PRIVACY.md)。

## 作者

**ZJ_X** — [GitHub @keoipl](https://github.com/keoipl)

如果这个工具对你的摄影工作流有帮助，欢迎给项目点一个 Star。
