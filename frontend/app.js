const TARGET_RATE = 16000;
const OPENAI_KEY_STORAGE = "hua_tfsu_openai_api_key";
const TERMS_STORAGE = "hua_tfsu_terms";
const CORPUS_STORAGE = "hua_tfsu_corpus";
const NOTES_STORAGE = "hua_tfsu_notes";
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const state = {
  socket: null,
  recognition: null,
  audioContext: null,
  analyser: null,
  source: null,
  stream: null,
  processor: null,
  transcript: [],
  translation: [],
  meterData: new Float32Array(512),
  lastPair: null,
  drawing: false,
};

const el = {
  status: document.getElementById("status"),
  viewTitle: document.getElementById("viewTitle"),
  tabs: document.querySelectorAll(".tab"),
  views: document.querySelectorAll(".view"),
  direction: document.getElementById("direction"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  apiKeyBtn: document.getElementById("apiKeyBtn"),
  exportBtn: document.getElementById("exportBtn"),
  transcript: document.getElementById("transcript"),
  translation: document.getElementById("translation"),
  history: document.getElementById("history"),
  latency: document.getElementById("latency"),
  sourceLabel: document.getElementById("sourceLabel"),
  targetLabel: document.getElementById("targetLabel"),
  sendLastToCorpusBtn: document.getElementById("sendLastToCorpusBtn"),
  termSource: document.getElementById("termSource"),
  termTarget: document.getElementById("termTarget"),
  addTermBtn: document.getElementById("addTermBtn"),
  extractTermsBtn: document.getElementById("extractTermsBtn"),
  termExtractText: document.getElementById("termExtractText"),
  termsList: document.getElementById("termsList"),
  termsCount: document.getElementById("termsCount"),
  corpusSource: document.getElementById("corpusSource"),
  corpusTarget: document.getElementById("corpusTarget"),
  addCorpusBtn: document.getElementById("addCorpusBtn"),
  corpusSearch: document.getElementById("corpusSearch"),
  corpusList: document.getElementById("corpusList"),
  corpusCount: document.getElementById("corpusCount"),
  notesCanvas: document.getElementById("notesCanvas"),
  penColor: document.getElementById("penColor"),
  penWidth: document.getElementById("penWidth"),
  clearNotesBtn: document.getElementById("clearNotesBtn"),
  saveNotesBtn: document.getElementById("saveNotesBtn"),
  downloadNotesBtn: document.getElementById("downloadNotesBtn"),
  meter: document.getElementById("meter"),
};

const labels = {
  "en-zh": ["English", "中文"],
  "zh-en": ["中文", "English"],
};

const viewTitles = {
  captions: "实时字幕",
  terms: "术语库",
  corpus: "双语语料库",
  notes: "手写笔记",
};

const recognitionLanguage = {
  "en-zh": "en-US",
  "zh-en": "zh-CN",
};

function setStatus(text) {
  el.status.textContent = text;
}

function setView(name) {
  el.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.view === name));
  el.views.forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  el.viewTitle.textContent = viewTitles[name];
  if (name === "notes") restoreNotes();
}

function updateLabels() {
  const [src, tgt] = labels[el.direction.value];
  el.sourceLabel.textContent = src;
  el.targetLabel.textContent = tgt;
}

function translationHeaders() {
  const headers = { "Content-Type": "application/json" };
  const apiKey = localStorage.getItem(OPENAI_KEY_STORAGE);
  if (apiKey) headers["X-OpenAI-API-Key"] = apiKey;
  return headers;
}

function loadJson(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function loadTerms() {
  const value = loadJson(TERMS_STORAGE, {});
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function saveTerms(terms) {
  localStorage.setItem(TERMS_STORAGE, JSON.stringify(terms));
}

function renderTerms() {
  const terms = loadTerms();
  const entries = Object.entries(terms);
  el.termsCount.textContent = `${entries.length} 条`;
  el.termsList.innerHTML = "";
  if (!entries.length) {
    el.termsList.innerHTML = `<div class="empty">暂无术语</div>`;
    return;
  }
  for (const [source, target] of entries) {
    const item = document.createElement("div");
    item.className = "term-row";
    item.innerHTML = `<span></span><strong></strong><button type="button">删除</button>`;
    item.querySelector("span").textContent = source;
    item.querySelector("strong").textContent = target;
    item.querySelector("button").addEventListener("click", () => removeTerm(source));
    el.termsList.appendChild(item);
  }
}

function addTerm(sourceValue, targetValue) {
  const source = (sourceValue ?? el.termSource.value).trim();
  const target = (targetValue ?? el.termTarget.value).trim();
  if (!source || !target) {
    setStatus("请输入原文术语和指定译法");
    return;
  }
  const terms = loadTerms();
  terms[source] = target;
  saveTerms(terms);
  el.termSource.value = "";
  el.termTarget.value = "";
  renderTerms();
  setStatus(`术语已添加：${source} -> ${target}`);
}

function removeTerm(source) {
  const terms = loadTerms();
  delete terms[source];
  saveTerms(terms);
  renderTerms();
  setStatus(`术语已删除：${source}`);
}

async function extractTerms() {
  const corpusText = loadCorpus().map((item) => `${item.source}\n${item.target}`).join("\n");
  const captionText = [...state.transcript, ...state.translation].join("\n");
  const text = [el.termExtractText.value.trim(), captionText, corpusText].filter(Boolean).join("\n\n");
  if (!text) {
    setStatus("请先粘贴材料，或生成字幕/语料后再抓取术语");
    return;
  }
  setStatus("正在抓取术语");
  const response = await fetch("/api/extract-terms", {
    method: "POST",
    headers: translationHeaders(),
    body: JSON.stringify({ direction: el.direction.value, text, existing_terms: loadTerms() }),
  });
  if (!response.ok) {
    setStatus(`术语抓取失败：${response.status}`);
    return;
  }
  const data = await response.json();
  saveTerms(data.terms || {});
  renderTerms();
  setStatus("术语抓取完成");
}

function loadCorpus() {
  const value = loadJson(CORPUS_STORAGE, []);
  return Array.isArray(value) ? value : [];
}

function saveCorpus(items) {
  localStorage.setItem(CORPUS_STORAGE, JSON.stringify(items));
}

function addCorpus(sourceValue, targetValue) {
  const source = (sourceValue ?? el.corpusSource.value).trim();
  const target = (targetValue ?? el.corpusTarget.value).trim();
  if (!source || !target) {
    setStatus("请输入原文和译文");
    return;
  }
  const corpus = loadCorpus();
  corpus.unshift({ id: Date.now(), source, target, created_at: new Date().toISOString() });
  saveCorpus(corpus);
  el.corpusSource.value = "";
  el.corpusTarget.value = "";
  renderCorpus();
  setStatus("语料已添加");
}

function removeCorpus(id) {
  saveCorpus(loadCorpus().filter((item) => item.id !== id));
  renderCorpus();
  setStatus("语料已删除");
}

function renderCorpus() {
  const query = el.corpusSearch.value.trim().toLowerCase();
  const corpus = loadCorpus();
  const filtered = corpus.filter((item) => {
    const text = `${item.source} ${item.target}`.toLowerCase();
    return !query || text.includes(query);
  });
  el.corpusCount.textContent = `${corpus.length} 条`;
  el.corpusList.innerHTML = "";
  if (!filtered.length) {
    el.corpusList.innerHTML = `<div class="empty">暂无语料</div>`;
    return;
  }
  for (const item of filtered) {
    const row = document.createElement("div");
    row.className = "corpus-row";
    row.innerHTML = `<p class="corpus-src"></p><p class="corpus-tgt"></p><button type="button">删除</button>`;
    row.querySelector(".corpus-src").textContent = item.source;
    row.querySelector(".corpus-tgt").textContent = item.target;
    row.querySelector("button").addEventListener("click", () => removeCorpus(item.id));
    el.corpusList.appendChild(row);
  }
}

function sendLastToCorpus() {
  if (!state.lastPair) {
    setStatus("暂无可存入语料库的字幕");
    return;
  }
  addCorpus(state.lastPair.transcript, state.lastPair.translation);
  setView("corpus");
}

async function configureApiKey() {
  const current = localStorage.getItem(OPENAI_KEY_STORAGE) || "";
  const input = window.prompt("请输入 OpenAI API Key。留空并确认将清除当前 Key。", current);
  if (input === null) return;

  const apiKey = input.trim();
  if (!apiKey) {
    localStorage.removeItem(OPENAI_KEY_STORAGE);
    setStatus("API Key 已清除，使用公共翻译兜底");
    return;
  }

  localStorage.setItem(OPENAI_KEY_STORAGE, apiKey);
  setStatus("API Key 已保存，正在测试");
  try {
    const response = await fetch("/api/translate", {
      method: "POST",
      headers: translationHeaders(),
      body: JSON.stringify({ direction: "en-zh", text: "Hello world", terms: loadTerms() }),
    });
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    setStatus(`API Key 测试通过：${data.translation}`);
  } catch (error) {
    setStatus(`API Key 已保存，但测试失败：${error.message}`);
  }
}

async function start() {
  updateLabels();
  state.transcript = [];
  state.translation = [];
  state.lastPair = null;
  el.history.innerHTML = "";
  el.transcript.textContent = "";
  el.translation.textContent = "";
  el.latency.textContent = "延迟 -";

  await startMeter();
  if (SpeechRecognition) startBrowserRecognition();
  else await startServerRecognition();

  el.startBtn.disabled = true;
  el.stopBtn.disabled = false;
  el.direction.disabled = true;
}

async function startMeter() {
  state.stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
  });
  state.audioContext = new AudioContext();
  state.source = state.audioContext.createMediaStreamSource(state.stream);
  state.analyser = state.audioContext.createAnalyser();
  state.analyser.fftSize = 1024;
  state.source.connect(state.analyser);
}

function startBrowserRecognition() {
  state.recognition = new SpeechRecognition();
  state.recognition.lang = recognitionLanguage[el.direction.value];
  state.recognition.continuous = true;
  state.recognition.interimResults = true;
  state.recognition.maxAlternatives = 1;
  state.recognition.onstart = () => setStatus("正在听写");
  state.recognition.onerror = (event) => setStatus(`听写错误：${event.error}`);
  state.recognition.onend = () => {
    if (el.stopBtn.disabled) return;
    try {
      state.recognition.start();
    } catch {
      setStatus("听写已暂停");
    }
  };
  state.recognition.onresult = onSpeechResult;
  state.recognition.start();
}

async function onSpeechResult(event) {
  let interim = "";
  for (let i = event.resultIndex; i < event.results.length; i += 1) {
    const text = event.results[i][0].transcript.trim();
    if (!text) continue;
    if (event.results[i].isFinal) await acceptTranscript(text);
    else interim += `${text} `;
  }
  const latest = state.transcript.slice(-2).join(" ");
  el.transcript.textContent = [latest, interim.trim()].filter(Boolean).join(" ");
}

async function acceptTranscript(text) {
  const started = performance.now();
  state.transcript.push(text);
  el.transcript.textContent = state.transcript.slice(-3).join(" ");
  setStatus("正在翻译");

  const response = await fetch("/api/translate", {
    method: "POST",
    headers: translationHeaders(),
    body: JSON.stringify({ direction: el.direction.value, text, terms: loadTerms() }),
  });
  if (!response.ok) throw new Error(`翻译失败：${await response.text()}`);
  const data = await response.json();
  data.latency_ms = Number(data.latency_ms || Math.round(performance.now() - started));
  state.translation.push(data.translation);
  state.lastPair = data;
  el.translation.textContent = state.translation.slice(-3).join(" ");
  el.latency.textContent = `延迟 ${data.latency_ms} ms`;
  appendHistory(data);
  setStatus("正在听写");
}

function socketUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/subtitle`;
}

async function startServerRecognition() {
  state.socket = new WebSocket(socketUrl());
  state.socket.binaryType = "arraybuffer";
  state.socket.onmessage = onSocketMessage;
  state.socket.onclose = stopAudioOnly;
  await waitForOpen(state.socket);
  state.socket.send(JSON.stringify({ direction: el.direction.value, sample_rate: TARGET_RATE, terms: loadTerms() }));

  const processor = state.audioContext.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    const downsampled = downsample(input, state.audioContext.sampleRate, TARGET_RATE);
    if (state.socket?.readyState === WebSocket.OPEN) state.socket.send(downsampled.buffer);
  };
  state.source.connect(processor);
  processor.connect(state.audioContext.destination);
  state.processor = processor;
  setStatus("正在听写");
}

function waitForOpen(socket) {
  return new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
}

function downsample(input, sourceRate, targetRate) {
  if (sourceRate === targetRate) return new Float32Array(input);
  const ratio = sourceRate / targetRate;
  const length = Math.floor(input.length / ratio);
  const output = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    output[i] = sum / Math.max(1, end - start);
  }
  return output;
}

function onSocketMessage(event) {
  const data = JSON.parse(event.data);
  if (data.type === "ready") {
    setStatus(`已连接 ${data.source_language} -> ${data.target_language}`);
    return;
  }
  if (data.type !== "subtitle") return;
  state.transcript.push(data.transcript);
  state.translation.push(data.translation);
  state.lastPair = data;
  el.transcript.textContent = state.transcript.slice(-3).join(" ");
  el.translation.textContent = state.translation.slice(-3).join(" ");
  el.latency.textContent = `延迟 ${data.latency_ms ?? "-"} ms`;
  appendHistory(data);
}

function appendHistory(data) {
  const item = document.createElement("li");
  const now = new Date().toLocaleTimeString();
  item.innerHTML = `<span class="time">${now}</span><span class="src"></span><span class="tgt"></span>`;
  item.querySelector(".src").textContent = data.transcript;
  item.querySelector(".tgt").textContent = data.translation;
  el.history.prepend(item);
}

async function stop() {
  if (state.recognition) {
    state.recognition.onend = null;
    state.recognition.stop();
  }
  if (state.socket?.readyState === WebSocket.OPEN) state.socket.send("stop");
  await stopAudioOnly();
  setStatus("已停止");
}

async function stopAudioOnly() {
  if (state.processor) state.processor.disconnect();
  if (state.source) state.source.disconnect();
  if (state.analyser) state.analyser.disconnect();
  if (state.audioContext) await state.audioContext.close().catch(() => {});
  if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
  state.processor = null;
  state.source = null;
  state.analyser = null;
  state.audioContext = null;
  state.stream = null;
  state.recognition = null;
  el.startBtn.disabled = false;
  el.stopBtn.disabled = true;
  el.direction.disabled = false;
}

function exportTranscript() {
  const rows = Array.from(el.history.children).reverse().map((li) => ({
    time: li.querySelector(".time").textContent,
    transcript: li.querySelector(".src").textContent,
    translation: li.querySelector(".tgt").textContent,
  }));
  const payload = {
    subtitles: rows,
    terms: loadTerms(),
    corpus: loadCorpus(),
  };
  downloadBlob(JSON.stringify(payload, null, 2), `hua-tfsu-export-${Date.now()}.json`, "application/json");
}

function drawMeter() {
  const canvas = el.meter;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#061018";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#38f8ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  if (state.analyser) state.analyser.getFloatTimeDomainData(state.meterData);
  const mid = height / 2;
  state.meterData.forEach((value, index) => {
    const x = (index / Math.max(1, state.meterData.length - 1)) * width;
    const y = mid + value * (height * 0.42);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  requestAnimationFrame(drawMeter);
}

function notePoint(event) {
  const rect = el.notesCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * el.notesCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * el.notesCanvas.height,
  };
}

function startNote(event) {
  state.drawing = true;
  el.notesCanvas.setPointerCapture(event.pointerId);
  const ctx = el.notesCanvas.getContext("2d");
  const point = notePoint(event);
  ctx.beginPath();
  ctx.moveTo(point.x, point.y);
}

function drawNote(event) {
  if (!state.drawing) return;
  const ctx = el.notesCanvas.getContext("2d");
  const point = notePoint(event);
  ctx.strokeStyle = el.penColor.value;
  ctx.lineWidth = Number(el.penWidth.value);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineTo(point.x, point.y);
  ctx.stroke();
}

function endNote() {
  if (!state.drawing) return;
  state.drawing = false;
  saveNotes();
}

function clearNotes() {
  const ctx = el.notesCanvas.getContext("2d");
  ctx.clearRect(0, 0, el.notesCanvas.width, el.notesCanvas.height);
  localStorage.removeItem(NOTES_STORAGE);
  setStatus("笔记已清空");
}

function saveNotes() {
  localStorage.setItem(NOTES_STORAGE, el.notesCanvas.toDataURL("image/png"));
  setStatus("笔记已保存");
}

function restoreNotes() {
  const data = localStorage.getItem(NOTES_STORAGE);
  if (!data) return;
  const image = new Image();
  image.onload = () => {
    const ctx = el.notesCanvas.getContext("2d");
    ctx.clearRect(0, 0, el.notesCanvas.width, el.notesCanvas.height);
    ctx.drawImage(image, 0, 0, el.notesCanvas.width, el.notesCanvas.height);
  };
  image.src = data;
}

function downloadNotes() {
  const data = localStorage.getItem(NOTES_STORAGE) || el.notesCanvas.toDataURL("image/png");
  const link = document.createElement("a");
  link.href = data;
  link.download = `hua-tfsu-notes-${Date.now()}.png`;
  link.click();
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

el.tabs.forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
el.startBtn.addEventListener("click", () => start().catch((error) => setStatus(error.message)));
el.stopBtn.addEventListener("click", stop);
el.apiKeyBtn.addEventListener("click", configureApiKey);
el.exportBtn.addEventListener("click", exportTranscript);
el.direction.addEventListener("change", updateLabels);
el.addTermBtn.addEventListener("click", () => addTerm());
el.extractTermsBtn.addEventListener("click", () => extractTerms().catch((error) => setStatus(error.message)));
el.termTarget.addEventListener("keydown", (event) => {
  if (event.key === "Enter") addTerm();
});
el.addCorpusBtn.addEventListener("click", () => addCorpus());
el.corpusSearch.addEventListener("input", renderCorpus);
el.sendLastToCorpusBtn.addEventListener("click", sendLastToCorpus);
el.notesCanvas.addEventListener("pointerdown", startNote);
el.notesCanvas.addEventListener("pointermove", drawNote);
el.notesCanvas.addEventListener("pointerup", endNote);
el.notesCanvas.addEventListener("pointercancel", endNote);
el.clearNotesBtn.addEventListener("click", clearNotes);
el.saveNotesBtn.addEventListener("click", saveNotes);
el.downloadNotesBtn.addEventListener("click", downloadNotes);

updateLabels();
renderTerms();
renderCorpus();
restoreNotes();
drawMeter();
