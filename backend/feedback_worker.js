// wx-mindmap 反馈后端（Cloudflare Worker）
// 提供两个接口：
//   POST /feedback     收一份匿名反馈（不含聊天内容）
//   GET  /improvements 吐社区改进点（所有用户生成时拉取，注入 prompt）
// 数据存 Cloudflare KV；全自动，无需维护。

// ============ 部署需知 ============
// 1. Cloudflare 控制台 → Workers & Pages → 创建 Worker
// 2. 把本文件内容粘贴进 Worker 编辑器
// 3. 左侧 "设置" → "绑定" → 添加 KV namespace（新建一个，名字如 WM_FEEDBACK_KV）
// 4. 绑定变量名填：WM_FEEDBACK_KV（代码里就是用这个读取）
// 5. 保存并部署 → 得到 https://<你的项目名>.<子域>.workers.dev
// 6. 把那个 URL 记下来，填到 exe/网页的"反馈后端点"配置里
// =============================================

// CORS：允许网页版和 exe 跨域调用
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 预检
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // ---- 收反馈 ----
    if (path === "/feedback" && request.method === "POST") {
      try {
        const body = await request.json();
        // 只收匿名字段，绝不收聊天内容
        const record = {
          ts: Date.now(),
          mood: String(body.mood || "").slice(0, 10),      // "like" | "dislike"
          reason: String(body.reason || "").slice(0, 300), // 一句话原因
          groupType: String(body.groupType || "").slice(0, 30), // 群类型(可选)
          version: String(body.version || "").slice(0, 20),
        };
        // 存一条，key 用时间戳保证不覆盖
        await env.WM_FEEDBACK_KV.put("fb_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6), JSON.stringify(record));
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json", ...CORS } });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: String(e) }), { status: 400, headers: { "Content-Type": "application/json", ...CORS } });
      }
    }

    // ---- 吐社区改进点 ----
    if (path === "/improvements" && request.method === "GET") {
      try {
        // 聚合所有反馈（分页遍历 KV）
        const list = await env.WM_FEEDBACK_KV.list({ limit: 1000 });
        const records = [];
        for (const k of list.keys) {
          const v = await env.WM_FEEDBACK_KV.get(k.name);
          if (v) { try { records.push(JSON.parse(v)); } catch (_) {} }
        }
        // 统计
        const stats = summarize(records);
        return new Response(JSON.stringify(stats), { status: 200, headers: { "Content-Type": "application/json", ...CORS } });
      } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: String(e) }), { status: 500, headers: { "Content-Type": "application/json", ...CORS } });
      }
    }

    // 健康检查 / 说明
    if (path === "/") {
      return new Response("wx-mindmap feedback backend. POST /feedback, GET /improvements", { status: 200, headers: CORS });
    }

    return new Response("Not Found", { status: 404, headers: CORS });
  },
};

// 改进点关键词桶：把各种说法归到同一个"改进指令"上。
// 顺序敏感：先匹配更具体的。命中就停。
const BUCKETS = [
  ["板块太多太杂", /(板块|栏目).*(多|杂|乱|精简)|太多板块/],
  ["要点太长", /(太长|啰嗦|冗长|废话|精简|简短|简短点|别写那么长)/],
  ["标签/重要度没用", /(标签|重要度|颜色|红|橙|蓝|标记)/],
  ["内容不准确/编造", /(编造|瞎说|不准|错了|幻觉|不对|误)/],
  ["缺重点/没抓住关键", /(没抓住|漏|重点|关键)/],
  ["词云/排版问题", /(词云|排版|乱糟糟|丑陋|难看|样式)/],
  ["项目识别缺失", /(项目|工具|作品).*(缺|漏|没找|没识)/],
  ["速度慢/卡", /(慢|卡|转圈|超时)/],
];

function bucketOf(reason) {
  const s = String(reason || "");
  for (const [name, re] of BUCKETS) if (re.test(s)) return name;
  return null; // 归不进桶的丢弃——宁可少，不要一堆同义噪音
}

// 把反馈汇总成"社区改进点"（可直接塞进 prompt）
function summarize(records) {
  const total = records.length;
  const likes = records.filter(r => r.mood === "like").length;
  const dislikes = records.filter(r => r.mood === "dislike").length;

  const counts = {}, examples = {};
  for (const r of records) {
    if (r.mood !== "dislike" || !r.reason) continue;
    const k = bucketOf(r.reason);
    if (!k) continue;
    counts[k] = (counts[k] || 0) + 1;
    // 留最长的原文当示例（信息量最大）
    if (!examples[k] || r.reason.length > examples[k].length) examples[k] = r.reason;
  }

  const types = {};
  for (const r of records) if (r.groupType) types[r.groupType] = (types[r.groupType] || 0) + 1;
  const topTypes = Object.entries(types).sort((a, b) => b[1] - a[1]).slice(0, 3).map(x => x[0]);

  return {
    total,
    likes,
    dislikes,
    topGroupTypes: topTypes,
    improvementPoints: Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([keyword, count]) => ({ keyword, count, example: examples[keyword] || "" })),
  };
}
