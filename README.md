# 本地语音识别转文字工具

基于 Whisper 的本地语音识别工具，支持按 `Ctrl+T` 快捷键进行语音输入，识别结果自动插入到当前光标位置。

## ✨ 特性

- 🎤 **全局快捷键**: 使用 `Ctrl+T` 在任何应用中启动录音
- 👁️ **状态可见**: 鼠标旁悬浮小窗显示「录音中 / 识别中」，不必去看控制台
- 📝 **自动插入**: 识别结果直接插入到当前光标位置
- 🚀 **本地运行**: 所有处理在本地完成，无需联网，保护隐私
- ⚡ **快速响应**: 使用 Whisper tiny 模型，速度优先
- 🇨🇳 **中文优化**: 针对中文语音识别进行优化

## 📋 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.8 或更高版本
- **内存**: 至少 2GB 可用内存
- **磁盘**: 约 500MB 空间（包括模型文件）

## ⚠️ Python 版本要求

**必须使用 Python 3.9 - 3.12。Python 3.13 目前不可用。**

原因是 faster-whisper 依赖 CTranslate2 作为推理引擎，而 CTranslate2 至今**尚未发布 Python 3.13 的预编译 wheel**（[官方 issue](https://github.com/OpenNMT/CTranslate2/issues/1853)），在 3.13 上安装会报 `No matching distribution found for ctranslate2`。

用 `python --version` 查看你的版本。如果是 3.13，见下方「用 conda 指定 Python 3.12」。

## 🚀 快速开始

### 1. 安装

双击运行 `install.bat`，脚本会自动：
- 检查 Python 环境
- 安装所需依赖包
- 安装成功后验证所有模块能否正常导入
- 若失败，会提示你是否撞上了 3.13 的兼容问题

### 2. 启动

双击运行 `start.bat` 启动程序。

### 3. 使用

同一个 `Ctrl+T` 键负责开始和结束，交替切换：

1. 光标点进要输入的地方，按 `Ctrl+T` — 鼠标旁出现红色「● 录音中」
2. 正常说完一句话
3. 再按一次 `Ctrl+T` — 指示器变成深蓝「◌ 识别中」，录音停止
4. 识别完成，指示器消失，文字自动出现在光标处

指示器消失就代表这一轮结束了，可以接着按 `Ctrl+T` 说下一句。用 tiny 模型时，一句话通常一两秒内出结果。

### 4. 退出

直接关闭那个黑色控制台窗口即可。程序运行期间该窗口需保持打开（可以最小化）。

## 📦 项目结构

```
voice_to_text/
├── voice_to_text.py    # 主程序
├── requirements.txt    # Python 依赖
├── install.bat         # 安装脚本
├── start.bat           # 启动脚本（系统 Python）
├── start-conda.bat     # 启动脚本（conda 环境，Python 3.13 用户用这个）
└── README.md           # 说明文档
```

全部文件必须放在**同一个文件夹**内，脚本靠相对路径互相查找。

## 🔧 技术栈

- **faster-whisper**: OpenAI Whisper 的高性能实现
- **sounddevice**: 跨平台音频采集
- **keyboard**: 全局快捷键监听
- **pyperclip**: 剪贴板读写（用于插入中文文本）
- **numpy**: 音频数据处理

文本插入采用「写入剪贴板 + 模拟 Ctrl+V」的方式，而非逐字符模拟按键。原因是模拟按键依赖键盘扫描码，无法可靠输入中文等非 ASCII 字符。粘贴完成后程序会恢复原有剪贴板内容。

## 🐍 用 conda 指定 Python 3.12

如果你的系统 Python 是 3.13，用 conda 建一个 3.12 的独立环境即可，**不需要卸载或降级现有的 3.13**。

没装 conda 的话，推荐 [Miniconda](https://docs.conda.io/en/latest/miniconda.html)（比完整版 Anaconda 小很多）。装好后打开「Anaconda Prompt」（不是普通 cmd），依次执行：

```bash
conda create -n voice python=3.12
conda activate voice
cd /d 你放文件的文件夹
pip install -r requirements.txt
```

之后每次启动用 `start-conda.bat`（而不是 `start.bat`），它会自动激活 `voice` 环境再运行程序。

两点注意：`conda activate` 只在 conda 已为 cmd.exe 初始化的情况下有效，若 `start-conda.bat` 报激活失败，改从「Anaconda Prompt」里运行它。另外若你把环境取了别的名字，需相应修改 `start-conda.bat` 里的 `set ENVNAME=voice`。

## ⚙️ 高级配置

### 切换模型大小

编辑 `voice_to_text.py` 最后一行：

```python
# 可选: tiny, base, small, medium, large
vtt = VoiceToText(model_size="tiny")  # 默认使用 tiny
```

模型对比：

| 模型 | 大小 | 速度 | 准确度 | 推荐场景 |
|------|------|------|--------|----------|
| tiny | ~75MB | ⚡⚡⚡ | ⭐⭐ | 日常快速输入 |
| base | ~150MB | ⚡⚡ | ⭐⭐⭐ | 平衡速度和准确度 |
| small | ~500MB | ⚡ | ⭐⭐⭐⭐ | 专业场景 |

### 启用 GPU 加速

如果有 NVIDIA 显卡，可以编辑 `voice_to_text.py`：

```python
# 将 device="cpu" 改为 device="cuda"
self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
```

需要先安装 CUDA 支持：
```bash
pip install nvidia-cublas-cu11 nvidia-cudnn-cu11
```

### 修改快捷键

编辑 `voice_to_text.py` 中的快捷键注册：

```python
# 将 'ctrl+t' 改为其他组合键
keyboard.add_hotkey('ctrl+t', self.toggle_recording)
```

支持的按键组合示例：
- `'ctrl+shift+v'`
- `'alt+space'`
- `'ctrl+alt+r'`

## 🐛 常见问题

### Q: 提示 "未检测到音频设备"
**A**: 确保麦克风已连接并在系统设置中启用。

### Q: 识别结果不准确
**A**: 
- 尝试更换到更大的模型（base 或 small）
- 确保录音环境安静
- 说话清晰，语速适中

### Q: 程序启动后无法使用快捷键
**A**: 
- 确保程序以管理员权限运行
- 检查是否有其他程序占用了 `Ctrl+T` 快捷键

### Q: 首次运行很慢
**A**: 第一次运行时需要下载模型文件（约 75MB），请耐心等待。后续运行会直接加载本地模型。

### Q: 双击 .bat 后窗口闪一下就消失了
**A**: 说明脚本在执行到 `pause` 之前就异常退出了。要看到错误信息，请**在控制台里手动运行**，这样窗口不会关闭：

1. 按 `Win+R`，输入 `cmd`，回车
2. 输入 `cd /d ` 后面加上文件所在文件夹路径，例如：
   ```
   cd /d C:\voice-input
   ```
3. 输入 `install.bat` 回车，完整错误就会留在屏幕上

常见原因有三个：文件不在同一个文件夹（脚本现已内置检查并给出提示）；文件被杀毒软件拦截或删除；文件被编辑器保存成了 LF 换行，导致 cmd 把整个文件当成一行执行（此时 `pause` 也不会生效）。把上一步看到的报错发给我即可。

### Q: 运行 .bat 时满屏 "'xxx' 不是内部或外部命令" 和乱码
**A**: 这是 `.bat` 文件的编码或换行符被破坏了。批处理文件必须是 **CRLF 换行 + 纯 ASCII 内容**：如果是 LF 换行，cmd 会把多行粘成一行；如果含中文，cmd 默认按 GBK 解析 UTF-8 字节会变乱码。

本项目的两个 `.bat` 已改为纯英文 + CRLF。如果你用文本编辑器改过它们，保存时请确认：换行符选 `CRLF`，编码选 `ANSI` 或 `UTF-8 无 BOM`，并且**不要在 `.bat` 里写中文**。中文说明放在这个 README 里就好。

### Q: 直接运行 python voice_to_text.py 报 UnicodeEncodeError
**A**: cmd 默认代码页是 GBK，无法输出 emoji。程序开头已用 `sys.stdout.reconfigure` 强制 UTF-8，正常不会遇到。若仍报错，改用 `start.bat` 启动（它会执行 `chcp 65001` 切换代码页）。

### Q: 文字无法插入到某些应用
**A**: 某些应用（如游戏、管理员权限的程序）可能会阻止模拟键盘输入。尝试以管理员权限运行本工具。

### Q: 悬浮指示器一直挂在屏幕上不消失
**A**: 正常情况下识别结束会自动隐藏（代码在 `finally` 块中处理，出错也会收起）。若真的卡住，关闭控制台窗口即可一并退出。

### Q: 指示器能不能贴着文字光标显示？
**A**: 目前跟随**鼠标指针**显示。贴着文本插入点需要调用 Windows API 获取 caret 坐标，但很多现代应用（Electron 程序、部分浏览器输入框）不上报该坐标，可靠性不足，因此没有采用。

### Q: 为什么会用到剪贴板？
**A**: 文本插入通过「写入剪贴板 + 模拟 Ctrl+V」实现，因为直接模拟按键无法可靠输入中文。程序会在粘贴完成后自动恢复你原本的剪贴板内容，但如果在录音识别的瞬间复制了其他东西，仍有极小概率被覆盖。

### Q: 按 Ctrl+T 会不会触发其他程序的功能？
**A**: 不会。程序注册快捷键时使用了 `suppress=True`，会拦截该按键，因此在浏览器中按 Ctrl+T 不会额外打开新标签页。副作用是程序运行期间，`Ctrl+T` 在所有应用中的原有功能都会失效。如果你需要保留原功能，可以改用一个不冲突的组合键（见下方「修改快捷键」）。

## 📝 使用技巧

1. **录音长度**: 建议每次录音 5-30 秒，过短可能识别不准，过长会增加识别时间
2. **环境音**: 在安静环境下识别效果最佳
3. **标点符号**: Whisper 会自动添加标点符号
4. **专业术语**: 如需识别专业术语，建议使用 base 或更大的模型

## 🔒 隐私说明

- 所有语音识别在本地完成
- 不会上传任何音频数据到云端
- 不会收集或存储用户数据

## 📄 许可证

本项目仅供学习和个人使用。

## 🤝 贡献

欢迎提交问题反馈和改进建议！

---

**注意**: 首次运行时请确保网络连接正常，以便下载模型文件。
