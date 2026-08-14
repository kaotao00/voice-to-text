"""
本地语音识别转文字工具

按 Ctrl+T 开始录音，再按一次停止并将识别结果插入到光标位置。
录音与识别过程中，会在鼠标附近显示一个悬浮状态指示器。
"""

import sys

# 强制控制台使用 UTF-8。Windows 的 cmd 默认是 GBK 代码页，
# 直接 python voice_to_text.py（不经 start.bat）时，打印中文和
# emoji 会抛 UnicodeEncodeError。errors="replace" 保证即使终端
# 字体不支持某些字符也只显示替代符，而不是让程序崩掉。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass  # Python < 3.7 或非标准 stdout，忽略

import os
import queue
import tempfile
import threading
import time
import wave

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from opencc import OpenCC

try:
    import tkinter as tk
    HAS_TK = True
except ImportError:
    # 极少数精简版 Python 未打包 tkinter，此时降级为纯控制台输出
    HAS_TK = False


# 指示器状态
IDLE = "idle"
RECORDING = "recording"
TRANSCRIBING = "transcribing"

# 状态 -> (显示文字, 背景色, 前景色)
STYLES = {
    RECORDING: ("● 录音中", "#c0392b", "#ffffff"),
    TRANSCRIBING: ("◌ 识别中", "#2c3e50", "#ffffff"),
}

class StatusIndicator:
    """
    无边框置顶小窗，显示在鼠标指针附近。

    tkinter 不是线程安全的，且 mainloop 必须占用主线程。而 keyboard
    的快捷键回调运行在它自己的线程里，所以其他线程只能通过 push()
    把状态投进队列，由主线程轮询队列后再更新界面。
    """

    def __init__(self):
        self.queue = queue.Queue()
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 去掉标题栏与边框
        self.root.attributes("-topmost", True)
        self.root.withdraw()  # 初始隐藏

        self.label = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 11),
                              padx=14, pady=8)
        self.label.pack()

    def push(self, state):
        """线程安全：可从任意线程调用"""
        self.queue.put(state)

    def _poll(self):
        """主线程定时排空队列。50ms 间隔在响应感和 CPU 占用间取平衡。"""
        try:
            while True:
                self._apply(self.queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _apply(self, state):
        if state == IDLE:
            self.root.withdraw()
            return
        text, bg, fg = STYLES[state]
        self.label.config(text=text, bg=bg, fg=fg)
        self.root.config(bg=bg)
        self._move_near_cursor()
        self.root.deiconify()
        self.root.lift()  # 某些环境下 deiconify 后会掉到其他窗口后面

    def _move_near_cursor(self):
        """挪到鼠标右下方，并夹住坐标避免超出屏幕边缘"""
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        x = min(self.root.winfo_pointerx() + 16,
                self.root.winfo_screenwidth() - w - 4)
        y = min(self.root.winfo_pointery() + 20,
                self.root.winfo_screenheight() - h - 4)
        self.root.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def run(self, on_ready):
        """占用当前线程跑事件循环。on_ready 在循环启动后触发。"""
        self.root.after(50, self._poll)
        self.root.after(100, on_ready)
        self.root.mainloop()


class NullIndicator:
    """tkinter 不可用时的降级实现：不显示任何界面"""

    def push(self, state):
        pass

    def run(self, on_ready):
        on_ready()
        keyboard.wait()


class VoiceToText:
    def __init__(self, indicator, model_size="tiny"):
        """
        Args:
            indicator: StatusIndicator 或 NullIndicator
            model_size: Whisper 模型大小 (tiny, base, small, medium, large)
        """
        self.indicator = indicator
        self.converter = OpenCC("t2s")
        print(f"正在加载 Whisper {model_size} 模型...")
        # 使用 CPU；如有 NVIDIA GPU 可改为 device="cuda", compute_type="float16"
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("模型加载完成！")

        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 16000  # Whisper 推荐采样率
        self.stream = None
        self.lock = threading.Lock()  # 防止快速连按导致状态错乱

    def insert_text(self, text):
        """
        将文本插入到当前光标位置。

        通过剪贴板 + Ctrl+V 实现，而不是 keyboard.write()：
        后者依赖键盘扫描码，无法可靠输入中文等非 ASCII 字符。
        插入后恢复用户原有的剪贴板内容。
        """
        try:
            original = pyperclip.paste()
        except Exception:
            original = None

        pyperclip.copy(text)
        time.sleep(0.05)  # 等剪贴板写入生效，否则部分应用会粘到旧内容
        keyboard.send("ctrl+v")

        if original is not None:
            time.sleep(0.3)  # 等粘贴完成再恢复，避免抢在粘贴前覆盖
            try:
                pyperclip.copy(original)
            except Exception:
                pass

    def audio_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            self.audio_data.append(indata.copy())

    def start_recording(self):
        print("\n🎤 开始录音... (说完后再按一次 Ctrl+T 停止)")
        self.is_recording = True
        self.audio_data = []
        self.indicator.push(RECORDING)

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=self.audio_callback,
            dtype=np.float32,
        )
        self.stream.start()

    def stop_recording_and_transcribe(self):
        """
        停止录音并识别。运行在独立线程中。

        调用方 toggle_recording 已在持锁状态下把 is_recording 置为
        False，因此这里不再重复设置。
        """
        print("⏹️  停止录音，正在识别...")
        self.indicator.push(TRANSCRIBING)

        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None

            if not self.audio_data:
                print("❌ 没有录制到音频数据")
                return

            audio = np.concatenate(self.audio_data, axis=0)

            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                with wave.open(temp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.sample_rate)
                    wf.writeframes((audio * 32767).astype(np.int16).tobytes())

                segments, _ = self.model.transcribe(
                    temp_path,
                    language="zh",
                    beam_size=5,
                    vad_filter=True,  # 过滤静音段
                    initial_prompt="请使用简体中文输出。",
                )
                text = self.converter.convert(
                    " ".join(s.text for s in segments).strip()
                )

                if text:
                    print(f"✅ 识别结果: {text}")
                    self.insert_text(text)
                else:
                    print("❌ 未识别到有效内容")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            print(f"❌ 识别出错: {e}")
        finally:
            # 无论成功失败都要收起指示器，否则会一直挂在屏幕上
            self.indicator.push(IDLE)

    def toggle_recording(self):
        with self.lock:
            if self.is_recording:
                # 在持锁状态下立即置 False：既能马上停止 audio_callback
                # 采集，也能防止快速连按启动两个识别线程
                self.is_recording = False
                threading.Thread(target=self.stop_recording_and_transcribe,
                                 daemon=True).start()
            else:
                self.start_recording()

    def register(self):
        # suppress=True 拦截按键，否则 Ctrl+T 会同时触发前台程序的默认
        # 行为（例如浏览器额外开一个新标签页）
        keyboard.add_hotkey("ctrl+t", self.toggle_recording, suppress=True)
        print("\n" + "=" * 52)
        print("🎙️  语音识别工具已就绪")
        print("=" * 52)
        print("按 Ctrl+T        开始录音")
        print("再按 Ctrl+T      停止录音并插入文字")
        print("关闭此窗口       退出程序")
        print("=" * 52 + "\n")


if __name__ == "__main__":
    indicator = StatusIndicator() if HAS_TK else NullIndicator()
    if not HAS_TK:
        print("提示：未检测到 tkinter，将不显示悬浮指示器。")

    vtt = VoiceToText(indicator, model_size="base")
    # 快捷键在 mainloop 启动后再注册：这样指示器已能响应状态更新，
    # 不会出现"按了 Ctrl+T 但窗口还没准备好"的空档
    indicator.run(on_ready=vtt.register)
