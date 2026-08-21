# 会记：本地会议纪要终端

这是会议室 Wi-Fi 硬件终端的软件版本。终端运行本地 Web 服务；会议人员在同一局域网中访问 `http://设备IP:8090` 即可录音、查看转写、播放原始音频和阅读会议纪要。

## 已实现能力

- 浏览器端采集麦克风音频并以 WAV 上传到本地设备；
- `faster-whisper base` 在 CPU/INT8 模式离线转写，输出强制为简体中文；
- 基于短时频谱特征的匿名本地聚类，会议内显示为“发言人 1/2/…”。它不是身份验证或跨会议声纹识别；
- 自动提取关键词、要点、决策与待办候选，并保存完整时间轴；
- SQLite 保存会议元数据，音频保存在设备本地卷中；
- REST API：`/api/health`、`/api/meetings`、`/api/meetings/<id>`。

## 设备端部署

设备应使用 x86_64 Linux 小主机（建议至少 8 GB 内存、20 GB 空闲空间）并连接会议室 Wi-Fi。首次使用会下载模型；之后可离线运行。

```bash
git clone https://github.com/kaotao00/voice-to-text.git
cd voice-to-text
docker compose -f docker-compose.yml -f docker-compose.device.yml up -d --build
```

在同一 Wi-Fi 下打开 `http://设备IP:8090`。Docker 数据卷 `meeting_data` 保存录音与会议记录，升级容器不会删除这些数据。

## 公网服务器与 GitHub Pages

同一个 Docker 服务可部署在服务器 `IP:8090` 作为演示/远程访问入口：

```bash
docker compose up -d --build
```

服务器本身通常不具备会议室麦克风，因而仅适合查看记录与演示；会议室实际采集场景应让硬件终端使用包含 `docker-compose.device.yml` 的命令运行服务。

`pages/` 是 GitHub Pages 产品介绍页。GitHub Pages 是静态 HTTPS 页面，不能安全地直接访问局域网 HTTP 设备接口；录音与会议详情应从设备 IP 打开的本地页面使用。

## 隐私与限制

会议音频属于敏感数据。部署公网前必须在反向代理层配置 HTTPS、账号认证和访问控制。当前首版的发言人区分为匿名聚类，适合整理发言轮次，准确率会受麦克风摆位、会议室混响和多人重叠说话影响。
