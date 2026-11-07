/* ============================================================
 * mock.js — 演示模式（?mock=1）
 *
 * 拦截 window.fetch，按后端真实契约返回构造数据，用于：
 *  - 无 API Key 环境下演示完整界面与交互流程；
 *  - 人工验收各类页面状态（加载 / 空 / 错误 / 成功）。
 *
 * 演示专用错误触发词：
 *  - 目的地/城市含「不存在」→ 400（地名无法定位）
 *  - 目的地/城市含「故障」  → 502（上游服务失败）
 *  - 景点名含「不存在」    → 多景点路线 400（RouteResolutionError 契约）
 * 页头会显示「演示数据」徽标（由 app.js 控制）。
 * ============================================================ */
(function (global) {
  "use strict";

  var params = new URLSearchParams(location.search);
  if (params.get("mock") !== "1") return; // 非演示模式不拦截
  global.__TA_MOCK__ = true;

  var enc = new TextEncoder("utf-8");
  function sleep(ms) {
    return new Promise(function (r) {
      setTimeout(r, ms);
    });
  }
  function jsonResp(body, status, delay) {
    return sleep(delay == null ? 350 : delay).then(function () {
      return new Response(JSON.stringify(body), {
        status: status || 200,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "mock" + Math.random().toString(16).slice(2, 10),
        },
      });
    });
  }
  function errResp(status, message, delay) {
    return jsonResp({ status: "error", message: message }, status, delay);
  }

  /* ---------------- 构造数据 ---------------- */

  function poi(name, address, rating, cost) {
    var ext = {};
    if (rating) ext.rating = rating;
    if (cost) ext.cost = cost;
    return {
      name: name,
      address: address,
      location: "120.15,30.27",
      biz_ext: ext,
    };
  }

  var SPOTS = [
    poi("西湖风景名胜区", "杭州市西湖区龙井路1号", "4.9", ""),
    poi("灵隐寺", "杭州市西湖区法云弄1号", "4.8", "45"),
    poi("西溪国家湿地公园", "杭州市西湖区天目山路518号", "4.7", "80"),
    poi("雷峰塔", "杭州市西湖区南山路15号", "4.6", "40"),
    poi("河坊街", "杭州市上城区河坊街", "4.5", ""),
    poi("京杭大运河·杭州景区", "杭州市拱墅区运河文化广场", "4.6", ""),
  ];

  var FOODS = [
    poi("外婆家（湖滨银泰店）", "杭州市上城区延安路湖滨银泰in77", "4.7", "75"),
    poi("知味观·味庄", "杭州市西湖区杨公堤10-12号", "4.6", "130"),
    poi("新白鹿餐厅（西湖银泰店）", "杭州市上城区南山路西湖银泰城", "4.5", "68"),
    poi("绿茶餐厅（龙井路店）", "杭州市西湖区龙井路83号", "4.5", "82"),
    poi("奎元馆（解放路总店）", "杭州市上城区解放路154号", "4.4", "35"),
    poi("南宋御街小吃街", "杭州市上城区南宋御街", "4.3", "45"),
  ];

  var HOTELS = [
    poi("杭州西湖索菲亚大酒店", "杭州市上城区中山中路336号", "4.7", "520"),
    poi("杭州君悦酒店", "杭州市上城区湖滨路28号", "4.8", "1180"),
    poi("全季酒店（西湖店）", "杭州市西湖区南山路101号", "4.6", "380"),
    poi("如家精选酒店（河坊街店）", "杭州市上城区河坊街38号", "4.4", "210"),
  ];

  var WEATHER_TEXT =
    "🌤️ 实时天气：\n📍 城市：杭州\n🌡️ 天气：多云\n🌡️ 温度：22℃\n" +
    "💨 风向：东风\n💨 风力：3级\n💧 湿度：62%\n🕐 发布时间：10:30";
  var DRESSING_TEXT = "温度适宜，建议穿薄外套、长袖衬衫或卫衣，舒适出行；午后微热可减一层。";

  var PLAN = {
    plan: {
      destination: "杭州",
      days: 3,
      day_plans: [
        {
          day: 1,
          title: "湖滨经典线",
          spots: ["西湖风景名胜区", "苏堤", "雷峰塔"],
          estimated_cost: 320,
        },
        {
          day: 2,
          title: "禅意山水线",
          spots: ["灵隐寺", "西溪国家湿地公园", "河坊街"],
          estimated_cost: 350,
        },
        {
          day: 3,
          title: "运河慢行线",
          spots: ["京杭大运河·杭州景区", "南宋御街", "西湖文化广场"],
          estimated_cost: 280,
        },
      ],
      hotel_preference: "建议住在西湖周边（湖滨/南山路一带）的舒适型酒店，步行可达湖畔，去各景点都方便。",
      hotel_est_cost_total: 900,
      food_recommendations: ["西湖醋鱼", "东坡肉", "龙井虾仁", "片儿川", "定胜糕"],
      total_estimated_cost: 1850,
      general_tips:
        "1. 西湖景区周末车流大，建议地铁+步行出行；\n2. 灵隐寺需先到飞来峰景区购票，早间人流较少；\n3. 热门餐厅建议错峰用餐（11:00 前或 13:00 后）；\n4. 部分场馆周一闭馆，出行前请核实。",
    },
    verification: {
      ok: true,
      issues: [],
      warnings: ["第 2 天行程较满，可视体力情况精简 1 个景点。"],
      over_budget: false,
    },
    schedule: [
      { day: 1, spots: ["西湖风景名胜区", "苏堤", "雷峰塔"], est_distance_km: 6.8 },
      { day: 2, spots: ["灵隐寺", "西溪国家湿地公园", "河坊街"], est_distance_km: 14.2 },
      { day: 3, spots: ["京杭大运河·杭州景区", "南宋御街", "西湖文化广场"], est_distance_km: 5.1 },
    ],
    params: { destination: "杭州", days: 3, budget: 2000 },
    budget_floor: { hotel_total: 0, food_total: 450, transit_total: 65.3, tickets_total: 0, total: 515.3 },
  };

  var MULTI_SPOT_TEXT =
    "\n🗺️ 多景点路线规划（驾车）：\n📍 共 3 个景点\n⏱️ 总耗时：约 42 分钟\n🛣️ 总距离：16.4 公里\n\n📋 各段路线：\n" +
    "  1. 西湖风景名胜区 → 苏堤 | 6分钟 | 2.1公里\n" +
    "  2. 苏堤 → 雷峰塔 | 9分钟 | 3.4公里";

  var CHAT_REPLY =
    "好的，帮你梳理一下 👇\n\n**行程节奏建议**\n- 第 1 天安排西湖沿线，步行为主，傍晚看雷峰塔日落\n- 第 2 天上午灵隐寺（人少清净），下午西溪湿地坐船\n- 第 3 天运河慢行 + 采购伴手礼\n\n**预算上**，按你的 2000 元总预算，扣除住宿约 900 元后，每天 300 元左右可以吃得不错：早餐片儿川，正餐安排一次外婆家或知味观。\n\n需要我调整某一天的安排，或者换个节奏（更悠闲/更紧凑）吗？";

  /* ---------------- fetch 拦截 ---------------- */

  var originalFetch = global.fetch.bind(global);

  function sseResponse(events, perFrameMs) {
    var stream = new ReadableStream({
      start: function (controller) {
        var i = 0;
        function next() {
          if (i >= events.length) {
            controller.enqueue(enc.encode("data: [DONE]\n\n"));
            controller.close();
            return;
          }
          controller.enqueue(enc.encode("data: " + JSON.stringify(events[i]) + "\n\n"));
          i += 1;
          setTimeout(next, perFrameMs || 60);
        }
        setTimeout(next, 300);
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "X-Request-ID": "mock-stream" },
    });
  }

  global.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input.url;
    var method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    var body = {};
    try {
      body = init && init.body ? JSON.parse(init.body) : {};
    } catch (_) {
      /* body 非 JSON 时按空处理 */
    }

    // 静态资源与外部请求不拦截
    if (url.indexOf("/web/") !== -1 || url.indexOf("http") === 0) {
      return originalFetch(input, init);
    }

    var cityMatch = url.match(/^\/(weather|spots|food|hotels)\/([^/?]+)/);
    if (cityMatch) {
      var city = decodeURIComponent(cityMatch[2]);
      if (city.indexOf("故障") !== -1) return errResp(502, "上游服务暂时不可用");
      if (city.indexOf("不存在") !== -1) return errResp(502, "无法查询信息");

      var kind = cityMatch[1];
      if (kind === "weather") {
        return jsonResp({
          status: "ok",
          data: { weather: WEATHER_TEXT, dressing_advice: DRESSING_TEXT },
        });
      }
      var list =
        kind === "spots" ? SPOTS : kind === "food" ? FOODS : HOTELS;
      return jsonResp({ status: "ok", count: list.length, data: list }, 200, 650);
    }

    if (url === "/plan" && method === "POST") {
      var dest = (body.message || "") + (body.destination || "");
      if (dest.indexOf("故障") !== -1) return errResp(502, "行程规划失败，请稍后重试或调整需求描述");
      if (dest.indexOf("不存在") !== -1) {
        return errResp(502, "行程规划失败，请稍后重试或调整需求描述");
      }
      // 模拟真实管线耗时，让进度页有完整展示过程
      return jsonResp({ status: "ok", data: PLAN }, 200, 5200);
    }

    if (url === "/route/multi-spot" && method === "POST") {
      var spots = body.spots || [];
      if (spots.some(function (s) { return (s || "").indexOf("不存在") !== -1; })) {
        return errResp(400, "以下景点无法定位，请提供更明确的名称：不存在景点");
      }
      if (spots.length < 2) return errResp(400, "至少需要2个景点才能规划路线");
      return jsonResp({ status: "ok", data: MULTI_SPOT_TEXT }, 200, 900);
    }

    if (url === "/chat/stream" && method === "POST") {
      var events = [
        { type: "tool_start", name: "查询实时天气" },
        { type: "tool_start", name: "搜索当地美食" },
      ];
      // 按 6 字一组切块，模拟 token 流式输出
      for (var i = 0; i < CHAT_REPLY.length; i += 6) {
        events.push({ type: "token", content: CHAT_REPLY.slice(i, i + 6) });
      }
      events.push({ type: "final", content: CHAT_REPLY });
      return Promise.resolve(sseResponse(events, 24));
    }

    if (url === "/chat" && method === "POST") {
      return jsonResp({ status: "ok", response: CHAT_REPLY }, 200, 800);
    }

    if (url === "/config/llm" && method === "GET") {
      return jsonResp({
        status: "ok",
        data: {
          provider: "zhipuai",
          model: "glm-5.1",
          base_url: "https://open.bigmodel.cn/api/paas/v4/",
          api_key: "abcd****wxyz",
          presets: {
            zhipuai: { base_url: "https://open.bigmodel.cn/api/paas/v4/", default_model: "glm-5.1" },
            deepseek: { base_url: "https://api.deepseek.com/v1", default_model: "deepseek-chat" },
            qwen: { base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus" },
            moonshot: { base_url: "https://api.moonshot.cn/v1", default_model: "moonshot-v1-8k" },
            openai: { base_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini" },
            ollama: { base_url: "http://localhost:11434/v1", default_model: "qwen2.5:7b" },
            custom: { base_url: "", default_model: "" },
          },
        },
      });
    }

    return errResp(404, "演示模式未模拟该接口：" + url);
  };
})(window);
