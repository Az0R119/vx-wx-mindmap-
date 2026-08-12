/* 微信消息总结 · 网页版核心逻辑 */
/* 纯前端：解压 zip（fflate）→ 解析微信导出 → 规则引擎 → 渲染思维导图。 */

const PROVIDERS = {
  deepseek: { base: "https://api.deepseek.com", model: "deepseek-chat", vision: false },
  qwen:     { base: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus", vision: true },
  zhipu:    { base: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash", vision: true },
  moonshot: { base: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k", vision: false },
  openai:   { base: "https://api.openai.com/v1", model: "gpt-4o-mini", vision: true },
  doubao:   { base: "https://ark.cn-beijing.volces.com/api/compatible", model: "doubao-seed-2-1-pro-260628", vision: true },
  ollama:   { base: "http://localhost:11434/v1", model: "qwen2.5:7b", vision: false },
};

const $ = id => document.getElementById(id);
let chatData = null; // 解析出的消息列表

/* ---------- 拖拽 / 选择 ---------- */
const dz = $("dropzone");
dz.addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", e => handleFile(e.target.files[0]));
["dragover","dragenter"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", e => handleFile(e.dataTransfer.files[0]));

async function handleFile(file) {
  if (!file || !file.name.toLowerCase().endsWith(".zip")) { setStatus("请选择 .zip 文件", true); return; }
  setStatus("解压中…");
  try {
    const buf = new Uint8Array(await file.arrayBuffer());
    const unz = fflate.unzipSync(buf);
    chatData = parseExport(unz);
    if (!chatData.length) throw new Error("zip 里没解析到会话");
    setStatus(`✅ 解析到 ${chatData.length} 条消息，可以生成了`);
    $("genBtn").disabled = false;
  } catch (e) { setStatus("❌ 解析失败：" + e.message, true); }
}

/* ---------- 解析微信导出 zip ---------- */
function parseExport(unz) {
  const msgs = [];
  const fileNames = Object.keys(unz);
  // 找 conversations 下的 page-*.js（旧格式）或 messages.html（新版单文件）
  const pages = fileNames.filter(n => /conversations\/.*\/(pages\/page-[\d]+\.js|messages\.html)/.test(n));
  const metaFiles = fileNames.filter(n => /conversations\/.*\/meta\.json/.test(n));
  let chatName = "微信群";
  if (metaFiles.length) {
    try {
      const meta = JSON.parse(new TextDecoder().decode(unz[metaFiles[0]]));
      chatName = meta.displayName || meta.name || chatName;
    } catch (e) {}
  }
  for (const p of pages) {
    const text = new TextDecoder().decode(unz[p]);
    // 解析消息行：wce-msg-row-received/send，含 data-wce-create-time、sender、content
    extractMessages(text, msgs);
  }
  return msgs;
}

function extractMessages(pageText, msgs) {
  // HTML 实体转义
  const unesc = s => s.replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"')
    .replace(/&#39;/g,"'").replace(/&amp;/g,"&").replace(/\\"/g,'"').replace(/\\\\/g,'\\');
  // 解码网页内的双转义
  const text = unesc(pageText);
  // 匹配每条消息行 (received/sent)，正文在 msg-bubble
  const rowRe = /<div class="[^"]*wce-msg-row-(received|sent)[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/g;
  let m;
  let count = 0;
  while ((m = rowRe.exec(text)) !== null && count < 20000) {
    const block = m[0];
    const direction = m[1];
    const timeM = /data-wce-create-time="(\d+)"/.exec(block);
    const dateM = /data-wce-date="([^"]*)"/.exec(block);
    // 昵称：text-[11px] text-gray-500 mb-1 后面
    const nickM = /text-\[11px\][^>]*text-left">([^<]*)</.exec(block);
    let sender = nickM ? nickM[1].trim() : (direction === "sent" ? "(自己)" : "");
    // 正文：msg-bubble 里的文本, 或媒体
    let body = "";
    const bubbleM = /msg-bubble[^>]*>([\s\S]*?)<\/div>/.exec(block);
    if (bubbleM) body = bubbleM[1].replace(/<[^>]+>/g," ").replace(/\s+/g," ").trim();
    else {
      const mediaM = /alt="(表情|图片|视频|链接)"/.exec(block);
      if (mediaM) body = "[" + mediaM[1] + "]";
      else {
        const linkM = /href="([^"]+)"/.exec(block);
        if (linkM) body = linkM[1];
      }
    }
    if (body && sender) {
      msgs.push({ sender, time: timeM ? +timeM[1] : 0, date: dateM ? dateM[1] : "", body });
      count++;
    }
  }
}

/* ---------- 规则引擎 ---------- */
function computeStats(msgs) {
  const total = msgs.length;
  const senderCnt = {};
  msgs.forEach(x => { senderCnt[x.sender] = (senderCnt[x.sender]||0)+1; });
  const senders = Object.keys(senderCnt);
  // 日期跨度
  const dates = new Set(msgs.map(x => x.date).filter(Boolean));
  // 时间分布(小时)
  const hours = new Array(24).fill(0);
  msgs.forEach(x => { if (x.time) { const d = new Date(x.time*1000); hours[d.getHours()]++; } });
  return { total, senders: senders.length, dates: dates.size, hours };
}

function detectProjects(msgs, top=20) {
  const urlRe = /https?:\/\/[^\s]+/g;
  const proj = {};
  msgs.forEach(x => {
    const urls = x.body.match(urlRe);
    if (urls) urls.forEach(u => {
      u = u.replace(/[,，。;；)]+$/,"");
      if (!proj[u]) proj[u] = { url:u, authors:{}, times:0, samples:[] };
      proj[u].times++; proj[u].authors[x.sender]=(proj[u].authors[x.sender]||0)+1;
      if (proj[u].samples.length<2) proj[u].samples.push(x.body.slice(0,50));
    });
  });
  return Object.values(proj)
    .map(p => {
      const author = Object.keys(p.authors).reduce((a,b)=>p.authors[a]>=p.authors[b]?a:b, Object.keys(p.authors)[0]||"");
      const slug = (p.url.match(/https?:\/\/([^.\/]+\.)*(.\w+)/)||[])[0]||"";
      const nameMatch = /(https?:\/\/)?([^. \n]+?)(?:\.netlify\.app|\.github\.io|\.site)/.exec(p.url);
      return { url:p.url, author, times:p.times, name: (nameMatch?nameMatch[2]:"工具"), sample:p.samples[0]||"" };
    })
    .sort((a,b)=>b.times-a.times)
    .slice(0,top);
}

function wordFreq(msgs, top=24) {
  const stop = new Set(("的 了 是 我 你 他 她 它 我们 你们 他们 这个 那个 一个 什么 怎么 为什么 没有 不是 就是 可以 因为 所以 但是 如果 知道 觉得 大家 一下 真的 现在 已经 还有 或者 然后 自己 大概 应该 可能 时候 东西 这样 那样".split(" ")));
  const freq = {};
  msgs.forEach(x => {
    const words = x.body.match(/[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}/g) || [];
    words.forEach(w => { w=w.toLowerCase(); if(!stop.has(w)) freq[w]=(freq[w]||0)+1; });
  });
  return Object.entries(freq).map(([word,count])=>({word,count})).sort((a,b)=>b.count-a.count).slice(0,top);
}

async function callAI(messages, key, base, model) {
  const r = await fetch(base.replace(/\/+$/,"")+"/chat/completions", {
    method:"POST", headers:{"Content-Type":"application/json","Authorization":"Bearer "+key},
    body: JSON.stringify({model, messages, temperature:0.3})
  });
  if (!r.ok) throw new Error("HTTP "+r.status+" "+ (await r.text()).slice(0,150));
  const d = await r.json();
  return d.choices?.[0]?.message?.content || "";
}

/* ---------- 生成 ---------- */
$("genBtn").addEventListener("click", generate);
async function generate() {
  if (!chatData) return;
  setStatus("生成中…");
  const theme = $("themeSel").value;
  const aiOn = $("aiOn").checked;
  const key = $("apiKey").value.trim();
  const pkey = $("providerSel").value;
  const p = PROVIDERS[pkey]||{};
  const base = pkey==="custom" ? $("customBase").value.trim() : p.base;
  const model = pkey==="custom" ? $("customModel").value.trim() : p.model;

  const stats = computeStats(chatData);
  const projects = detectProjects(chatData);
  const wc = wordFreq(chatData);

  let aiSections = "";   // AI 动态板块渲染结果(HTML)
  let aiEssence = "";
  if (aiOn) {
    if (!key || !base) { setStatus("启用 AI 需填 key", true); return; }
    const userHint = (($("userHint")||{}).value||"").trim();
    try {
      // ---------- Step1: 让 AI 判定这个群该有哪些板块(专属板块方案) ----------
      setStatus("AI 判断群类型…");
      let plan = { sections: [] };
      try {
        const sample = chatData.slice(-80).map(x=>x.sender+": "+x.body.slice(0,50)).join("\n");
        const planPrompt = "请判断这个微信群属于什么类型(家庭/同学/工作/兴趣/项目/学习/其他)，列出最适合本群的4~6个板块方案，严格JSON返回：{「群类型」:str, 「sections」:[{icon,title,focus}] }。"
          + (userHint ? " 用户提示：这是【"+userHint+"】群，板块请优先贴这个方向。" : " 用户未指定类型，请根据聊天内容自行判断。")
          + "\n聊天记录片段：\n"+sample;
        const planRaw = await callAI([{role:"user",content:planPrompt}], key, base, model);
        const pm = planRaw.match(/\{[^]*\}/);
        if (pm) { try { plan = JSON.parse(pm[0]) || {sections:[]}; } catch(e){} }
      } catch(e) { plan = { sections: [] }; }

      // ---------- Step2: 用板块方案正式出图 ----------
      setStatus("AI 生成思维导图…");
      const tr = chatData.slice(0,300).map(x=>x.sender+": "+x.body.slice(0,60)).join("\n");
      const sectionsList = (plan.sections||[]).map(s=>`${s.icon||"•"} ${s.title||""}${s.focus?"（重点："+s.focus+"）":""}`).join("\n");
      const structPrompt = "你是微信群聊总结助手。这是聊天记录，请按下方要求返回严格JSON："
        + '{"title":"一句话概括","sections":[{"icon":"emoji","title":"板块名","subs":[{"title":"小标题","points":[{"text":"要点","level":1("红")/2("橙")/3("蓝"),"tag":"中文短词"}]}]}]}'
        + " 板块要严格按下面清单来(4~6个，不要自己加)，每条要点配贴合内容的emoji，内容要充实不编造。\n"
        + (sectionsList ? "【板块清单】\n"+sectionsList+"\n" : "")
        + (userHint ? "【用户方向】"+userHint+"\n" : "")
        + "聊天记录：\n"+tr;
      const out = await callAI([{role:"user",content:structPrompt}], key, base, model);
      const sm = out.match(/\{[^]*\}/);
      if (sm) {
        try {
          const struct = JSON.parse(sm[0]);
          aiSections = renderAiSections(struct.sections||[]);
        } catch(e) {}
      }
      // 提炼3条精华(额外)
      const essPrompt = "这段群聊，提炼3条最值得关注的结论，每条一句话，编号1.2.3.。\n"+tr;
      try { aiEssence = await callAI([{role:"user",content:essPrompt}], key, base, model); } catch(e){}
    } catch(e){ aiEssence = "AI 失败："+e.message+"（已用本地规则版）"; }
  }

  const html = renderMindmap(chatData, stats, projects, wc, aiSections, aiEssence, theme);
  renderToPage(html);
  setStatus("✅ 完成，以下是思维导图");
  // 出图后显示反馈框（社区闭环）
  showFeedback();
}

/* ---------- 反馈闭环 ---------- */
const FBBACKEND = "https://wxmindmap.1464768276.workers.dev";
let fbMood = "";
function showFeedback() {
  const box = $("feedbackBox");
  if (box) box.style.display = "block";
  fbMood = "";
  $("fbReason").value = "";
  $("fbOk").style.display = "none";
}
document.addEventListener("click", e => {
  const btn = e.target.closest(".fb-btn");
  if (!btn) return;
  fbMood = btn.dataset.mood;
  document.querySelectorAll(".fb-btn").forEach(b => b.style.borderColor = b === btn ? "#a78bfa" : "#2a3a5a");
});
$("fbSend").addEventListener("click", async () => {
  const reason = $("fbReason").value.trim();
  if (!fbMood) { $("fbOk").textContent = "请先选 👍 或 👎"; $("fbOk").style.display = "block"; return; }
  // localStorage 记偏好（L2）
  try {
    const prefs = JSON.parse(localStorage.getItem("wm_prefs") || "{}");
    const hintEl = document.getElementById("userHint");
    prefs.lastGroup = (hintEl && hintEl.value) || prefs.lastGroup || "";
    localStorage.setItem("wm_prefs", JSON.stringify(prefs));
  } catch(e) {}
  // 匿名上传（不含聊天内容）
  try {
    await fetch(FBBACKEND.replace(/\/+$/, "") + "/feedback", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood: fbMood, reason: reason, groupType: "", version: "0.2.0" })
    });
    $("fbOk").textContent = "🙏 谢谢你让工具更好用！";
  } catch(e) {
    $("fbOk").textContent = "（反馈发送失败，不影响使用）";
  }
  $("fbOk").style.display = "block";
  setTimeout(() => { const box = $("feedbackBox"); if (box) box.style.display = "none"; }, 2500);
});

function renderToPage(html) {
  $("result").innerHTML = `<iframe sandbox="allow-same-origin" src="data:text/html;charset=utf-8,${encodeURIComponent(html)}"></iframe>`;
}

/* 把 AI 返回的动态板块(sections)渲染成可折叠树状 HTML。
   sections: [{icon,title,subs:[{title,points:[{text,level,tag}]}]}] */
function renderAiSections(sections) {
  if (!sections || !sections.length) return "";
  const levelColor = {1:"#ef4444",2:"#f59e0b",3:"#3b82f6"};
  return sections.map(s => {
    const icon = s.icon || "•";
    const title = esc(s.title || "板块");
    const subs = (s.subs||[]).map(sb => {
      const subTitle = sb.title ? `<div class="sub-h">${esc(sb.title)}</div>` : "";
      const pts = (sb.points||[]).filter(p=>p && p.text).map(p => {
        const lv = p.level || 3;
        const col = levelColor[lv] || "#3b82f6";
        const tag = p.tag ? `<span class="tagx" style="border-color:${col};color:${col}">${esc(p.tag)}</span>` : "";
        return `<div class="pt" style="border-left-color:${col}"><span class="lem"></span>${tag}<span class="keg">${esc(p.text)}</span></div>`;
      }).join("");
      return `<div class="sub-b">${subTitle}${pts}</div>`;
    }).join("");
    return `<div class="ai-sec"><div class="ai-sec-h"><span class="ai-sec-i">${icon}</span><b>${title}</b></div>${subs}</div>`;
  }).join("");
}

function setStatus(msg, err) { $("status").textContent = msg; $("status").style.color = err?"#fda4af":"#9fb0d8"; }

function esc(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

/* ---------- 记住用户设置（localStorage） ---------- */
// 自定义 provider 的 base/model 记忆 key
const LS = { key:"wm_key", theme:"wm_theme", provider:"wm_provider", base:"wm_base", model:"wm_model" };
function loadPrefs() {
  try {
    if (localStorage.getItem(LS.key)) $("apiKey").value = localStorage.getItem(LS.key);
    if (localStorage.getItem(LS.theme)) $("themeSel").value = localStorage.getItem(LS.theme);
    if (localStorage.getItem(LS.provider)) $("providerSel").value = localStorage.getItem(LS.provider);
    if (localStorage.getItem(LS.base)) $("customBase").value = localStorage.getItem(LS.base);
    if (localStorage.getItem(LS.model)) $("customModel").value = localStorage.getItem(LS.model);
  } catch(e) {}
}
function savePref() {
  try {
    if ($("apiKey").value) localStorage.setItem(LS.key, $("apiKey").value);
    else localStorage.removeItem(LS.key);
    localStorage.setItem(LS.theme, $("themeSel").value);
    localStorage.setItem(LS.provider, $("providerSel").value);
    if ($("providerSel").value === "custom") {
      if ($("customBase").value) localStorage.setItem(LS.base, $("customBase").value);
      if ($("customModel").value) localStorage.setItem(LS.model, $("customModel").value);
    }
  } catch(e) {}
}
// 监听改动自动记住
["input","change"].forEach(ev => {
  $("apiKey").addEventListener(ev, savePref);
  $("themeSel").addEventListener(ev, savePref);
  $("providerSel").addEventListener(ev, e => {
    $("customRow").style.display = ($("providerSel").value === "custom") ? "flex" : "none";
    savePref();
  });
  $("customBase").addEventListener(ev, savePref);
  $("customModel").addEventListener(ev, savePref);
});
loadPrefs();
$("customRow").style.display = ($("providerSel").value === "custom") ? "flex" : "none";

/* ---------- 渲染思维导图 HTML ---------- */
function renderMindmap(msgs, stats, projects, wc, aiSections, aiEssence, theme) {
  const g = {
    dark: { bg:"#0a0e1a", card:"#101629", line:"#2a3a5a", text:"#dbe4ff", muted:"#9fb0d8", hi:"#a78bfa", med:"#22d3ee" },
    light: { bg:"#f5f7ff", card:"#ffffff", line:"#e3e8f5", text:"#1f2937", muted:"#6b7280", hi:"#7c3aed", med:"#2563eb" },
    minimal: { bg:"#ffffff", card:"#fafafa", line:"#eee", text:"#111", muted:"#888", hi:"#333", med:"#555" },
  }[theme] || {};
  const C = g;
  const themeCss = `
    body { background:${C.bg}; color:${C.text}; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; padding:20px; }
    .wrap { max-width:1000px; margin:0 auto; }
    .head { text-align:center; padding:20px; }
    .head h1 { font-size:26px; background:linear-gradient(90deg,${C.hi},${C.med}); -webkit-background-clip:text; color:transparent; }
    .stats { display:flex; gap:12px; justify-content:center; margin:14px 0 6px; flex-wrap:wrap; }
    .stats span { background:${C.card}; border:1px solid ${C.line}; padding:6px 16px; border-radius:12px; font-size:13px; }
    .section { background:${C.card}; border:1px solid ${C.line}; border-radius:14px; margin:14px 0; overflow:hidden; }
    .sec-h { padding:14px 18px; font-weight:700; cursor:pointer; display:flex; align-items:center; gap:8px; border-bottom:1px solid ${C.line}; }
    .sec-h .ar { margin-left:auto; transition:.2s; }
    .sec[open] .ar { transform:rotate(90deg); }
    .sec-b { padding:8px 18px 16px; }
    .pt { padding:7px 10px; border-radius:8px; margin:4px 0; font-size:14px; line-height:1.6; border-left:3px solid ${C.med}; }
    .pt.key { border-left-color:#ef4444; background:rgba(239,68,68,.05); }
    .pt b { color:${C.hi}; }
    .pgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; }
    .pcard { background:${C.bg}; border:1px solid ${C.line}; border-radius:10px; padding:12px; }
    .pcard h3 { font-size:14px; display:flex; align-items:center; gap:6px; }
    .pauth { background:rgba(124,58,237,.12); color:${C.hi}; font-size:11px; padding:1px 7px; border-radius:999px; }
    .plink { font-size:11px; color:${C.med}; word-break:break-all; }
    .pd { font-size:12px; color:${C.muted}; margin-top:4px; }
    .cloud { display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:6px 12px; padding:14px; min-height:150px; }
    .cv { font-weight:700; }
    .ai-sec { margin:8px 0; }
    .ai-sec-h { font-size:15px; display:flex; align-items:center; gap:6px; margin-bottom:4px; color:${C.text}; }
    .ai-sec-i { font-size:16px; }
    .sub-h { font-weight:600; color:${C.hi}; margin:8px 0 2px; font-size:14px; }
    .tagx { display:inline-block; font-size:10px; padding:0 6px; border:1px solid; border-radius:4px; margin-right:6px; font-weight:600; }
    ul { list-style:none; } .note{color:${C.muted};font-size:12px;padding:6px;}
  `;

  // 项目卡片
  const projCards = projects.map(p => `
    <div class="pcard"><h3>🚀 ${esc(p.name)} ${p.author?`<span class="pauth">${esc(p.author)}</span>`:""}</h3>
    <div class="plink">${esc(p.url)}</div>
    <div class="pd">被提及 ${p.times} 次${p.sample?` · ${esc(p.sample.slice(0,40))}`:""}</div></div>`).join("");

  // 话题：按关键词粗略分（复用 wordFreq 词当话题）
  const topics = wc.slice(0,8).map(w => `
    <li><div class="pt ${w.count>5?'key':''}">${esc(w.word)} <b>· ${w.count}次</b></div></li>`).join("");

  // 时间热区
  const maxH = Math.max(...stats.hours.filter(h=>h>0), 1);
  const hoursHtml = stats.hours.map(h => {
    const ht = h/maxH*90+2;
    return `<span style="flex:1;background:${C.hi};height:${ht}px;border-radius:3px;min-height:2px;" title="${h}条"></span>`;
  }).join("");

  const cloudHtml = wc.map((w,i) => {
    const size = 0.9 + (w.count / (wc[0]?.count||1)) * 1.6;
    return `<span class="cv" style="font-size:${size.toFixed(2)}rem;color:hsl(${(i*47+180)%360},70%,70%)">${esc(w.word)}</span>`;
  }).join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${themeCss}</style></head><body><div class="wrap">
  <div class="head"><h1>🧠 ${esc(msgs[0]?.sender||"群聊")} 群聊思维导图</h1>
    <div class="stats"><span>📝 ${stats.total} 条</span><span>👥 ${stats.senders} 位群友</span><span>📅 ${stats.dates} 天</span><span>🚀 ${projects.length} 个项目</span></div></div>

  <details class="section" open><summary class="sec-h">🚀 群友项目 <span class="ar">▸</span></summary><div class="sec-b"><div class="pgrid">${projCards||"<div class='note'>未识别到项目（没带链接的工具？）</div>"}</div></div></details>

  ${aiSections?`<details class="section" open><summary class="sec-h">🧠 AI 智能板块 <span class="ar">▸</span></summary><div class="sec-b">${aiSections}</div></details>`:""}

  ${aiEssence?`<details class="section" open><summary class="sec-h">🤖 AI 提炼 <span class="ar">▸</span></summary><div class="sec-b"><ul>${aiEssence.split("\n").filter(Boolean).map(s=>`<li><div class="pt"><span class="lem">✦</span><span class="keg">${esc(s.replace(/^\d+\./,"").trim())}</span></div></li>`).join("")}</ul></div></details>`:""}

  <details class="section" open><summary class="sec-h">🔖 群聊热门词 <span class="ar">▸</span></summary><div class="sec-b"><ul>${topics}</ul></div></details>

  <details class="section" open><summary class="sec-h">☁️ 词云 <span class="ar">▸</span></summary><div class="cloud">${cloudHtml}</div></details>

  <details class="section" open><summary class="sec-h">⏰ 各时段活跃 <span class="ar">▸</span></summary><div class="sec-b"><div style="display:flex;align-items:flex-end;gap:3px;height:90px">${hoursHtml}</div></div></details>
  </div></body></html>`;
}

