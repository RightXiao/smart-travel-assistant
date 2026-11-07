/* ============================================================
 * api.js — 后端 API 客户端（零依赖）
 *
 * 职责：
 *  - 统一 fetch 封装：超时中断、错误归一化（TAError）、可选 Bearer 鉴权、
 *    可配置 API 地址（默认同源，与 FastAPI 静态托管在同一服务时无需配置）；
 *  - 响应契约对齐后端：成功 200 {"status":"ok",...}；上游失败 502；
 *    地名无法定位 400；请求体校验失败 422；未授权 401；
 *  - SSE 流式对话（POST /chat/stream）逐事件回调。
 *
 * 所有请求/响应均为 JSON（除 SSE 流）。
 * ============================================================ */
(function (global) {
  "use strict";

  var LS_BASE_KEY = "ta.api.base";
  var LS_TOKEN_KEY = "ta.api.token";

  /** 归一化错误对象：kind ∈ client(400/401/422) | upstream(5xx) | network | timeout */
  function TAError(kind, message, opts) {
    opts = opts || {};
    this.kind = kind;
    this.message = message;
    this.status = opts.status || 0;
    this.requestId = opts.requestId || "";
    this.detail = opts.detail || "";
  }
  TAError.prototype.toString = function () {
    return this.message;
  };

  function getBase() {
    return (localStorage.getItem(LS_BASE_KEY) || "").replace(/\/+$/, "");
  }
  function setBase(base) {
    if (base) localStorage.setItem(LS_BASE_KEY, base.replace(/\/+$/, ""));
    else localStorage.removeItem(LS_BASE_KEY);
  }
  function getToken() {
    return localStorage.getItem(LS_TOKEN_KEY) || "";
  }
  function setToken(token) {
    if (token) localStorage.setItem(LS_TOKEN_KEY, token);
    else localStorage.removeItem(LS_TOKEN_KEY);
  }

  /** 构造完整 URL（base + path） */
  function buildUrl(path) {
    return getBase() + path;
  }

  /** 通用请求头 */
  function buildHeaders(extra) {
    var headers = { "Content-Type": "application/json" };
    var token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    return Object.assign(headers, extra || {});
  }

  /** 把 fetch 响应转成 TAError（按后端错误契约归类） */
  async function toError(response) {
    var status = response.status;
    var requestId = response.headers.get("X-Request-ID") || "";
    var message = "";
    var detail = "";
    try {
      var body = await response.json();
      message = (body && (body.message || body.detail)) || "";
      if (body && body.detail && typeof body.detail !== "string") {
        // FastAPI 422 校验错误：detail 为数组，提炼首个字段错误
        var first = body.detail[0];
        detail = first && first.msg ? first.msg : JSON.stringify(body.detail);
        message = message || "请求参数未通过校验";
      } else {
        detail = typeof body === "string" ? body : "";
      }
    } catch (_) {
      /* 非 JSON 响应体，保留状态码信息 */
    }

    var kind;
    var fallback;
    if (status === 400) {
      kind = "client";
      fallback = "目的地或地点名称无法定位，试试换一种写法（如「杭州」「西安市」）。";
    } else if (status === 401) {
      kind = "client";
      fallback = "服务端已开启鉴权，请在右上角「连接设置」中填写 Bearer Token。";
    } else if (status === 422) {
      kind = "client";
      fallback = "请求参数不完整或有误，请检查表单后重试。";
    } else if (status >= 500) {
      kind = "upstream";
      fallback = "旅行数据服务暂时不可用，请稍后重试。";
    } else {
      kind = "client";
      fallback = "请求失败（HTTP " + status + "）。";
    }
    return new TAError(kind, message || fallback, {
      status: status,
      requestId: requestId,
      detail: detail,
    });
  }

  /**
   * 通用 JSON 请求。
   * @param {string} path 接口路径（以 / 开头）
   * @param {{method?:string, body?:Object, timeoutMs?:number, signal?:AbortSignal}} opts
   * @returns {Promise<Object>} 解析后的 JSON（成功响应）
   * @throws {TAError}
   */
  async function request(path, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 30000;
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort(new DOMException("timeout", "TimeoutError"));
    }, timeoutMs);
    // 允许调用方级联中断（如切换页面时取消进行中的请求）
    if (opts.signal) {
      if (opts.signal.aborted) controller.abort(opts.signal.reason);
      else opts.signal.addEventListener("abort", function () {
        controller.abort(opts.signal.reason);
      }, { once: true });
    }

    var resp;
    try {
      resp = await fetch(buildUrl(path), {
        method: opts.method || "GET",
        headers: buildHeaders(),
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      if (err && (err.name === "AbortError" || err.name === "TimeoutError")) {
        throw new TAError(opts.signal && opts.signal.aborted ? "aborted" : "timeout",
          opts.signal && opts.signal.aborted ? "请求已取消" : "请求超时，请检查网络后重试。");
      }
      throw new TAError("network", "网络连接失败，请确认服务已启动并可访问。");
    } finally {
      clearTimeout(timer);
    }

    if (!resp.ok) throw await toError(resp);

    try {
      return await resp.json();
    } catch (_) {
      throw new TAError("upstream", "服务返回了无法解析的数据。", {
        status: resp.status,
        requestId: resp.headers.get("X-Request-ID") || "",
      });
    }
  }

  /* ---------------- 业务接口封装 ---------------- */

  /** 当前多厂商 LLM 接入配置：GET /config/llm（密钥脱敏 + 厂商预设） */
  function fetchLlmConfig(signal) {
    return request("/config/llm", { signal: signal });
  }

  /** 结构化行程规划：POST /plan（管线耗时较长，默认 5 分钟超时） */
  function fetchPlan(message, sessionId, signal) {
    return request("/plan", {
      method: "POST",
      body: { message: message, session_id: sessionId },
      timeoutMs: 300000,
      signal: signal,
    });
  }

  /** 实时天气：GET /weather/{city} → {weather: string, dressing_advice: string} */
  function fetchWeather(city, signal) {
    return request("/weather/" + encodeURIComponent(city), { signal: signal });
  }

  /** 热门景点：GET /spots/{city} → data 为 POI 数组 */
  function fetchSpots(city, pageSize, signal) {
    return request(
      "/spots/" + encodeURIComponent(city) + "?page_size=" + (pageSize || 6),
      { signal: signal }
    );
  }

  /** 特色美食：GET /food/{city} → data 为 POI 数组（含评分/人均） */
  function fetchFood(city, pageSize, signal) {
    return request(
      "/food/" + encodeURIComponent(city) + "?page_size=" + (pageSize || 6),
      { signal: signal }
    );
  }

  /** 住宿（可按档位）：GET /hotels/{city} */
  function fetchHotels(city, budget, pageSize, signal) {
    var qs = budget ? "?budget=" + encodeURIComponent(budget) + "&" : "?";
    return request(
      "/hotels/" + encodeURIComponent(city) + qs + "page_size=" + (pageSize || 6),
      { signal: signal }
    );
  }

  /** 多景点路线：POST /route/multi-spot → data 为格式化文本 */
  function fetchMultiSpotRoute(spots, city, mode, signal) {
    return request("/route/multi-spot", {
      method: "POST",
      body: { spots: spots, city: city || "", mode: mode, optimize_order: false },
      timeoutMs: 60000,
      signal: signal,
    });
  }

  /**
   * 流式对话：POST /chat/stream（SSE）。
   * @param {string} message 用户消息
   * @param {Array<{role,content}>} chatHistory 页面内历史（匿名模式）
   * @param {(event:Object)=>void} onEvent 事件回调：
   *        {type:"tool_start",name} | {type:"token",content}
   *        | {type:"final",content} | {type:"error",message}
   * @param {AbortSignal} [signal] 中断信号
   * @throws {TAError} 连接失败时抛出
   */
  async function streamChat(message, chatHistory, onEvent, signal) {
    var resp;
    try {
      resp = await fetch(buildUrl("/chat/stream"), {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify({ message: message, chat_history: chatHistory || [] }),
        signal: signal,
      });
    } catch (err) {
      if (err && err.name === "AbortError") throw new TAError("aborted", "请求已取消");
      throw new TAError("network", "网络连接失败，请确认服务已启动并可访问。");
    }
    if (!resp.ok) throw await toError(resp);

    // 手工解析 SSE：以空行分隔事件，行格式 data: <json>
    var reader = resp.body.getReader();
    var decoder = new TextDecoder("utf-8");
    var buffer = "";
    try {
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });

        var idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          var frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          frame.split("\n").forEach(function (line) {
            if (line.indexOf("data:") !== 0) return;
            var payload = line.slice(5).trim();
            if (!payload) return;
            if (payload === "[DONE]") return;
            try {
              onEvent(JSON.parse(payload));
            } catch (_) {
              /* 跳过无法解析的事件帧，避免整流中断 */
            }
          });
        }
      }
    } catch (err) {
      if (!(err && err.name === "AbortError")) {
        throw new TAError("network", "连接中断，请重试。");
      }
      throw err;
    }
  }

  global.TAApi = {
    TAError: TAError,
    request: request,
    fetchLlmConfig: fetchLlmConfig,
    fetchPlan: fetchPlan,
    fetchWeather: fetchWeather,
    fetchSpots: fetchSpots,
    fetchFood: fetchFood,
    fetchHotels: fetchHotels,
    fetchMultiSpotRoute: fetchMultiSpotRoute,
    streamChat: streamChat,
    getBase: getBase,
    setBase: setBase,
    getToken: getToken,
    setToken: setToken,
  };
})(window);
