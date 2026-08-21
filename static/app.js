const $ = (selector) => document.querySelector(selector);
let activeMeeting, seconds = 0, clock;

function pad(value) { return String(value).padStart(2, "0"); }
function formatTime(value) { value = Math.floor(value || 0); return `${pad(Math.floor(value / 60))}:${pad(value % 60)}`; }
function setState(text) { $("#record-state").textContent = text; }

async function startRecording() {
  const created = await fetch("/api/meetings", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title: $("#meeting-title").value})});
  activeMeeting = await created.json();
  const response = await fetch(`/api/meetings/${activeMeeting.id}/device-recording/start`, {method:"POST"});
  if (!response.ok) throw new Error((await response.json()).error || "设备麦克风启动失败");
  seconds = 0; clock = setInterval(() => $("#timer").textContent = formatTime(++seconds), 1000);
  $("#record-button").textContent = "结束并生成纪要"; $("#record-button").classList.add("recording");
  setState("会议室设备正在录音。音频不会上传到云端。");
}

async function stopRecording() {
  clearInterval(clock); setState("设备录音已结束，正在本地转写与整理…");
  const response = await fetch(`/api/meetings/${activeMeeting.id}/device-recording/stop`, {method:"POST"});
  if (!response.ok) throw new Error((await response.json()).error || "设备录音停止失败");
  $("#record-button").textContent = "开始会议录音"; $("#record-button").classList.remove("recording"); $("#timer").textContent = "00:00";
  await loadMeetings(); pollMeeting(activeMeeting.id);
}

async function toggleRecording() {
  try { if (!activeMeeting || !$("#record-button").classList.contains("recording")) await startRecording(); else await stopRecording(); }
  catch (error) { setState(`操作失败：${error.message}`); }
}

async function loadMeetings() {
  const meetings = await (await fetch("/api/meetings")).json(), list = $("#meeting-list"); list.innerHTML = "";
  meetings.forEach(meeting => { const node = $("#meeting-template").content.firstElementChild.cloneNode(true);
    node.querySelector("strong").textContent = meeting.title; node.querySelector("span").textContent = new Date(meeting.created_at).toLocaleString();
    node.querySelector("em").textContent = ({new:"等待录音",recording:"录音中",queued:"等待分析",processing:"正在整理",ready:"纪要已生成",failed:"处理失败"})[meeting.status];
    node.onclick = () => showMeeting(meeting.id); list.append(node);
  });
}

async function pollMeeting(id) {
  const data = await (await fetch(`/api/meetings/${id}`)).json();
  if (data.status === "ready" || data.status === "failed") { setState(data.status === "ready" ? "会议纪要已生成。" : "处理失败，请查看会议详情。"); showMeeting(id); loadMeetings(); return; }
  setTimeout(() => pollMeeting(id), 3000);
}
function list(items) { return `<ul>${items.map(item => `<li>${item}</li>`).join("")}</ul>`; }
async function showMeeting(id) {
  const meeting = await (await fetch(`/api/meetings/${id}`)).json(), detail = $("#detail");
  if (meeting.status !== "ready") { detail.className = "detail empty"; detail.innerHTML = `<div><h2>${meeting.title}</h2><p>${meeting.status === "failed" ? `处理失败：${meeting.error}` : "正在使用本地 CPU 模型整理会议，请稍候…"}</p></div>`; return; }
  const m = meeting.minutes;
  detail.className = "detail"; detail.innerHTML = `<h2>${meeting.title}</h2><p class="meta">${new Date(meeting.created_at).toLocaleString()} · ${formatTime(meeting.duration_seconds)} · 本地处理</p><audio controls src="/api/meetings/${meeting.id}/audio"></audio><p>${m.summary}</p><div class="tags">${m.keywords.map(tag => `<span>${tag}</span>`).join("")}</div><div class="minutes-grid"><section class="block"><h4>会议要点</h4>${list(m.highlights)}</section><section class="block"><h4>决策事项</h4>${list(m.decisions)}</section><section class="block"><h4>待办跟进</h4>${list(m.actions)}</section><section class="block"><h4>发言分布</h4>${list(Object.entries(m.speaker_stats).map(([name,count]) => `${name}：${count} 段`))}</section></div><section class="transcript"><h3>完整发言记录</h3>${meeting.utterances.map(item => `<div class="utterance"><b>${item.speaker}</b><time>${formatTime(item.start_seconds)}–${formatTime(item.end_seconds)}</time><div>${item.text}</div></div>`).join("")}</section>`;
}

$("#record-button").onclick = toggleRecording; $("#refresh").onclick = loadMeetings;
fetch("/api/health").then(r => r.json()).then(data => $("#health").textContent = data.microphone ? `设备就绪 · ${data.model}` : "设备在线 · 未检测到麦克风").catch(() => $("#health").textContent = "设备离线");
loadMeetings();
