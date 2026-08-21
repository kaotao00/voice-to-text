"""Local-first meeting recorder and minutes server.

Run this on the meeting-room device.  It only binds to the local network by
default; recordings, transcripts, and minutes remain on the device.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
import wave
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from faster_whisper import WhisperModel
from opencc import OpenCC

APP_DIR = Path(os.environ.get("MEETING_HOME", Path(__file__).parent)).resolve()
DATA_DIR = APP_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "meetings.db"
MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")
MAX_SPEAKERS = max(1, int(os.environ.get("MAX_SPEAKERS", "6")))

app = Flask(__name__)
converter = OpenCC("t2s")
model_lock = threading.Lock()
_model: WhisperModel | None = None


class DeviceRecorder:
    """Captures the meeting-room device's default microphone to a WAV file."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.meeting_id: str | None = None
        self.stream: sd.InputStream | None = None
        self.frames: list[np.ndarray] = []
        self.sample_rate = 16000

    def start(self, meeting_id: str) -> None:
        with self.lock:
            if self.stream is not None:
                raise RuntimeError("设备正在录制另一场会议")
            self.meeting_id = meeting_id
            self.frames = []
            self.stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="float32", callback=self._on_audio
            )
            self.stream.start()

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        if self.stream is not None:
            self.frames.append(indata.copy())

    def stop(self, meeting_id: str) -> Path:
        with self.lock:
            if self.stream is None or self.meeting_id != meeting_id:
                raise RuntimeError("该会议当前未使用设备麦克风录音")
            self.stream.stop()
            self.stream.close()
            self.stream = None
            if not self.frames:
                raise RuntimeError("未录制到音频数据，请检查设备麦克风")
            audio = np.concatenate(self.frames, axis=0)
            self.frames = []
            self.meeting_id = None
        audio_path = AUDIO_DIR / f"{meeting_id}.wav"
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        return audio_path


device_recorder = DeviceRecorder()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds REAL DEFAULT 0,
                audio_path TEXT,
                minutes_json TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS utterances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id TEXT NOT NULL,
                speaker TEXT NOT NULL,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY(meeting_id) REFERENCES meetings(id)
            );
            """
        )


def get_model() -> WhisperModel:
    global _model
    with model_lock:
        if _model is None:
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        return _model


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def speaker_features(path: Path, start: float, end: float) -> np.ndarray:
    """Small CPU-only voice descriptor used for anonymous speaker clustering.

    It intentionally labels speakers anonymously.  It is useful for ordinary
    round-table meetings, but is not a biometric identity system.
    """
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        wav.setpos(max(0, int(start * rate)))
        frames = wav.readframes(max(1, int((end - start) * rate)))
        signal = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768
        channels = wav.getnchannels()
    if channels > 1:
        signal = signal.reshape(-1, channels).mean(axis=1)
    if signal.size < 512:
        return np.zeros(12, dtype=np.float32)
    window = np.hanning(min(len(signal), rate * 3)).astype(np.float32)
    signal = signal[: len(window)] * window
    spectrum = np.abs(np.fft.rfft(signal)) + 1e-8
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    power = spectrum * spectrum
    centroid = float((freqs * power).sum() / power.sum()) / 4000
    bandwidth = float(np.sqrt(((freqs - centroid * 4000) ** 2 * power).sum() / power.sum())) / 4000
    rolloff = float(freqs[np.searchsorted(np.cumsum(power), power.sum() * 0.85)]) / 4000
    chunks = np.array_split(np.log(spectrum), 9)
    bands = [float(np.mean(chunk)) for chunk in chunks]
    return np.asarray([centroid, bandwidth, rolloff, *bands], dtype=np.float32)


def assign_speakers(path: Path, utterances: list[dict]) -> None:
    if len(utterances) < 2:
        for item in utterances:
            item["speaker"] = "发言人 1"
        return
    features = np.vstack([speaker_features(path, item["start"], item["end"]) for item in utterances])
    # A compact, dependency-free online clustering pass.  This is deliberately
    # anonymous: it groups similar acoustic segments into meeting-local labels,
    # rather than identifying a person from a global voiceprint database.
    features = (features - features.mean(axis=0)) / (features.std(axis=0) + 1e-5)
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels: list[int] = []
    for feature in features:
        distances = [float(np.linalg.norm(feature - center)) for center in centroids]
        closest = int(np.argmin(distances)) if distances else -1
        if closest < 0 or (distances[closest] > 3.8 and len(centroids) < MAX_SPEAKERS):
            centroids.append(feature.copy())
            counts.append(1)
            closest = len(centroids) - 1
        else:
            counts[closest] += 1
            centroids[closest] += (feature - centroids[closest]) / counts[closest]
        labels.append(closest)
    aliases: dict[int, str] = {}
    for item, label in zip(utterances, labels):
        aliases.setdefault(label, f"发言人 {len(aliases) + 1}")
        item["speaker"] = aliases[label]


def build_minutes(title: str, utterances: list[dict]) -> dict:
    full_text = " ".join(item["text"] for item in utterances)
    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", full_text)
    stop = {"我们", "你们", "这个", "就是", "然后", "因为", "可以", "需要", "一个", "会议", "问题", "目前"}
    keywords = [word for word, _ in Counter(word for word in words if word not in stop).most_common(8)]
    decisions = [item["text"] for item in utterances if re.search(r"决定|确认|通过|采用|上线|完成|负责", item["text"])][:6]
    actions = [item["text"] for item in utterances if re.search(r"待办|跟进|负责|下周|明天|安排|提交", item["text"])][:6]
    highlights = [item["text"] for item in utterances[: min(5, len(utterances))]]
    speaker_stats = Counter(item["speaker"] for item in utterances)
    return {
        "title": title,
        "summary": "本次会议已完成本地转写与整理，共识别出 %d 段发言。" % len(utterances),
        "keywords": keywords,
        "highlights": highlights,
        "decisions": decisions or ["未自动识别到明确决策，请结合完整记录确认。"],
        "actions": actions or ["未自动识别到明确待办事项。"],
        "speaker_stats": speaker_stats,
    }


def process_meeting(meeting_id: str, audio_path: Path) -> None:
    try:
        with db() as connection:
            title = connection.execute("SELECT title FROM meetings WHERE id = ?", (meeting_id,)).fetchone()["title"]
            connection.execute("UPDATE meetings SET status = 'processing' WHERE id = ?", (meeting_id,))
        segments, _ = get_model().transcribe(
            str(audio_path), language="zh", beam_size=5, vad_filter=True,
            initial_prompt="请使用简体中文输出会议发言内容。",
        )
        utterances = [
            {"start": round(segment.start, 2), "end": round(segment.end, 2),
             "text": converter.convert(segment.text.strip())}
            for segment in segments if segment.text.strip()
        ]
        assign_speakers(audio_path, utterances)
        minutes = build_minutes(title, utterances)
        with db() as connection:
            connection.executemany(
                "INSERT INTO utterances(meeting_id, speaker, start_seconds, end_seconds, text) VALUES (?, ?, ?, ?, ?)",
                [(meeting_id, u["speaker"], u["start"], u["end"], u["text"]) for u in utterances],
            )
            connection.execute(
                "UPDATE meetings SET status = 'ready', ended_at = ?, duration_seconds = ?, minutes_json = ? WHERE id = ?",
                (now(), wav_duration(audio_path), json.dumps(minutes, ensure_ascii=False), meeting_id),
            )
    except Exception as error:  # Preserve the meeting record for diagnosis.
        with db() as connection:
            connection.execute("UPDATE meetings SET status = 'failed', error = ? WHERE id = ?", (str(error), meeting_id))


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    try:
        microphone = sd.query_devices(kind="input")["name"]
    except Exception:
        microphone = None
    return jsonify({"ok": True, "model": MODEL_NAME, "storage": str(DATA_DIR), "microphone": microphone})


@app.get("/api/meetings")
def meetings():
    with db() as connection:
        rows = connection.execute(
            "SELECT id, title, status, created_at, ended_at, duration_seconds FROM meetings ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/meetings")
def create_meeting():
    body = request.get_json(silent=True) or {}
    meeting_id = uuid.uuid4().hex
    title = str(body.get("title") or f"会议 {datetime.now().strftime('%Y-%m-%d %H:%M')}").strip()[:100]
    with db() as connection:
        connection.execute("INSERT INTO meetings(id, title, status, created_at) VALUES (?, ?, 'new', ?)",
                           (meeting_id, title, now()))
    return jsonify({"id": meeting_id, "title": title}), 201


@app.post("/api/meetings/<meeting_id>/audio")
def upload_audio(meeting_id: str):
    with db() as connection:
        meeting = connection.execute("SELECT id FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if not meeting:
        abort(404)
    payload = request.get_data()
    if len(payload) < 44 or len(payload) > 2 * 1024 * 1024 * 1024:
        return jsonify({"error": "音频文件无效或过大"}), 400
    audio_path = AUDIO_DIR / f"{meeting_id}.wav"
    audio_path.write_bytes(payload)
    try:
        duration = wav_duration(audio_path)
    except wave.Error:
        audio_path.unlink(missing_ok=True)
        return jsonify({"error": "仅支持浏览器生成的 WAV 音频"}), 400
    with db() as connection:
        connection.execute("UPDATE meetings SET status = 'queued', audio_path = ?, duration_seconds = ? WHERE id = ?",
                           (str(audio_path), duration, meeting_id))
    threading.Thread(target=process_meeting, args=(meeting_id, audio_path), daemon=True).start()
    return jsonify({"status": "queued", "duration_seconds": duration})


@app.post("/api/meetings/<meeting_id>/device-recording/start")
def start_device_recording(meeting_id: str):
    try:
        device_recorder.start(meeting_id)
    except Exception as error:
        return jsonify({"error": str(error)}), 409
    with db() as connection:
        connection.execute("UPDATE meetings SET status = 'recording' WHERE id = ?", (meeting_id,))
    return jsonify({"status": "recording"})


@app.post("/api/meetings/<meeting_id>/device-recording/stop")
def stop_device_recording(meeting_id: str):
    try:
        audio_path = device_recorder.stop(meeting_id)
        duration = wav_duration(audio_path)
        with db() as connection:
            connection.execute("UPDATE meetings SET status = 'queued', audio_path = ?, duration_seconds = ? WHERE id = ?",
                               (str(audio_path), duration, meeting_id))
        threading.Thread(target=process_meeting, args=(meeting_id, audio_path), daemon=True).start()
    except Exception as error:
        return jsonify({"error": str(error)}), 409
    return jsonify({"status": "queued", "duration_seconds": duration})


@app.get("/api/meetings/<meeting_id>")
def meeting_detail(meeting_id: str):
    with db() as connection:
        meeting = connection.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not meeting:
            abort(404)
        utterances = connection.execute(
            "SELECT speaker, start_seconds, end_seconds, text FROM utterances WHERE meeting_id = ? ORDER BY id", (meeting_id,)
        ).fetchall()
    result = dict(meeting)
    result["minutes"] = json.loads(result.pop("minutes_json") or "{}")
    result["utterances"] = [dict(item) for item in utterances]
    return jsonify(result)


@app.get("/api/meetings/<meeting_id>/audio")
def meeting_audio(meeting_id: str):
    with db() as connection:
        row = connection.execute("SELECT audio_path FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if not row or not row["audio_path"]:
        abort(404)
    path = Path(row["audio_path"])
    return send_from_directory(path.parent, path.name, mimetype="audio/wav", as_attachment=False)


initialize()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8090")), threaded=True)
