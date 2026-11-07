/* ============================================================
 * app.js — 界面主逻辑（零依赖 SPA）
 *
 * 页面层级（hash 路由）：
 *   #/              首页：需求定制表单 + 灵感速览
 *   #/generating    定制中：管线进度动画 + 错误态
 *   #/result        定制结果：行程总览 + 偏好回显 + 预算
 *   #/day/:n        行程详情：单日时间线 + 真实路线查询
 *   #/inspiration   首页锚点：滚动到灵感速览区
 *
 * 全局浮层：AI 助手侧滑抽屉（SSE 流式）、连接设置、Toast。
 * 状态持久化：localStorage 保存表单草稿 / 最近一次行程 / 会话 ID。
 * ============================================================ */
(function (global) {
  "use strict";

  var Api = global.TAApi;

  /* ============================================================
   * 工具函数
   * ============================================================ */

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtMoney(n) {
    var v = Number(n) || 0;
    return v % 1 === 0
      ? v.toLocaleString("zh-CN")
      : v.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  }

  /** Toast 轻提示（type: ok | err | info） */
  function toast(text, type) {
    var region = $("#toast-region");
    var el = document.createElement("div");
    el.className = "toast " + (type || "info");
    var icon = type === "ok" ? "i-check-circle" : type === "err" ? "i-alert-circle" : "i-info";
    el.innerHTML = '<svg class="icon"><use href="#' + icon + '"/></svg><span></span>';
    el.lastElementChild.textContent = text;
    region.appendChild(el);
    setTimeout(function () {
      el.classList.add("leaving");
      setTimeout(function () {
        el.remove();
      }, 260);
    }, 2800);
  }

  /** 复制文本（clipboard API + execCommand 兜底） */
  function copyText(text, okMsg) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        toast(okMsg || "已复制", "ok");
      } catch (_) {
        toast("复制失败，请手动选择文本", "err");
      }
      ta.remove();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          toast(okMsg || "已复制", "ok");
        },
        fallback
      );
    } else {
      fallback();
    }
  }

  /** 下载文本文件 */
  function downloadText(filename, text) {
    var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(function () {
      URL.revokeObjectURL(a.href);
    }, 1000);
  }

  /** 极简 Markdown 渲染（加粗 / 列表 / 标题 / 行内代码），先转义再处理 */
  function renderMarkdown(src) {
    var lines = String(src || "").split("\n");
    var html = [];
    var inList = false;
    function closeList() {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
    }
    function inline(s) {
      return escapeHtml(s)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    }
    lines.forEach(function (raw) {
      var line = raw.trimEnd();
      if (/^#{1,4}\s+/.test(line)) {
        closeList();
        html.push("<h4>" + inline(line.replace(/^#{1,4}\s+/, "")) + "</h4>");
      } else if (/^\s*[-*]\s+/.test(line)) {
        if (!inList) {
          html.push("<ul>");
          inList = true;
        }
        html.push("<li>" + inline(line.replace(/^\s*[-*]\s+/, "")) + "</li>");
      } else if (line.trim() === "") {
        closeList();
      } else {
        closeList();
        html.push("<p>" + inline(line) + "</p>");
      }
    });
    closeList();
    return html.join("");
  }

  /* ============================================================
   * 全局状态
   * ============================================================ */

  var LS_KEYS = { draft: "ta.draft", plan: "ta.plan", session: "ta.session" };

  function uuid() {
    return "web-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  var COMPANIONS = [
    { value: "couple", label: "情侣出行" },
    { value: "alone", label: "独自出行" },
    { value: "family", label: "家庭亲子" },
    { value: "friends", label: "朋友结伴" },
    { value: "team", label: "团队出行" },
  ];
  var PACES = [
    { value: "standard", label: "标准节奏" },
    { value: "easy", label: "悠闲慢游" },
    { value: "tight", label: "紧凑打卡" },
  ];
  var INTERESTS = [
    "自然风光", "历史文化", "美食探店", "文艺打卡", "亲子友好",
    "夜生活", "购物血拼", "户外徒步", "海滨度假", "小众秘境",
  ];
  var HOT_CITIES = ["杭州", "北京", "成都", "西安", "上海", "三亚", "重庆", "厦门"];

  function defaultDraft() {
    return {
      destination: "",
      departDate: "",
      returnDate: "",
      days: 3,
      budget: 3000,
      companions: "couple",
      pace: "standard",
      interests: [],
      note: "",
    };
  }

  var store = {
    sessionId: localStorage.getItem(LS_KEYS.session) || uuid(),
    draft: defaultDraft(),
    plan: null, // 最近一次成功定制的 { data, message }
    gen: { running: false, abort: null, timers: [], elapsedTimer: null },
    insp: { city: "", tab: "weather", data: null, loading: false, error: null },
    chat: { open: false, messages: [], streaming: false, abort: null },
  };
  try {
    localStorage.setItem(LS_KEYS.session, store.sessionId);
    var savedDraft = JSON.parse(localStorage.getItem(LS_KEYS.draft) || "null");
    if (savedDraft) store.draft = Object.assign(defaultDraft(), savedDraft);
    var savedPlan = JSON.parse(localStorage.getItem(LS_KEYS.plan) || "null");
    if (savedPlan && savedPlan.data && savedPlan.data.plan) store.plan = savedPlan;
  } catch (_) {
    /* 本地存储不可用时按全新会话处理 */
  }

  function saveDraft() {
    try {
      localStorage.setItem(LS_KEYS.draft, JSON.stringify(store.draft));
    } catch (_) { /* 忽略持久化失败 */ }
  }
  function savePlan() {
    try {
      localStorage.setItem(LS_KEYS.plan, JSON.stringify(store.plan));
    } catch (_) { /* 忽略持久化失败 */ }
  }

  /* ============================================================
   * 需求表单 → 自然语言需求描述（供 /plan 管线抽取参数）
   * ============================================================ */

  function companionLabel(v) {
    for (var i = 0; i < COMPANIONS.length; i++) {
      if (COMPANIONS[i].value === v) return COMPANIONS[i].label;
    }
    return "";
  }
  function paceLabel(v) {
    for (var i = 0; i < PACES.length; i++) {
      if (PACES[i].value === v) return PACES[i].label;
    }
    return "";
  }

  function compileMessage(d) {
    var parts = ["我想去" + d.destination + "旅游" + d.days + "天"];
    if (d.budget > 0) parts.push("总预算" + d.budget + "元");
    var prefs = [];
    var comp = companionLabel(d.companions);
    if (comp) prefs.push(comp);
    var pace = paceLabel(d.pace);
    if (pace) prefs.push(pace);
    if (d.interests.length) prefs.push("喜欢" + d.interests.join("、"));
    if (prefs.length) parts.push(prefs.join("，"));
    if (d.note && d.note.trim()) parts.push("补充要求：" + d.note.trim());
    return parts.join("，") + "。请帮我定制一份逐日旅行攻略。";
  }

  /** 出发/返回日期 → 天数（返回日期必须不早于出发日期） */
  function daysFromDates(d) {
    if (!d.departDate || !d.returnDate) return null;
    var a = new Date(d.departDate + "T00:00:00");
    var b = new Date(d.returnDate + "T00:00:00");
    if (isNaN(a.getTime()) || isNaN(b.getTime()) || b < a) return null;
    return Math.round((b - a) / 86400000) + 1;
  }

  function validateDraft(d) {
    var errors = {};
    if (!d.destination.trim()) errors.destination = "请填写目的地，例如：杭州";
    if (d.days < 1 || d.days > 15) errors.days = "行程天数需在 1~15 天之间";
    if (d.departDate && d.returnDate && daysFromDates(d) === null) {
      errors.returnDate = "返程日期不能早于出发日期";
    }
    if (d.budget < 0) errors.budget = "预算不能为负数";
    return errors;
  }

  /* ============================================================
   * 路由
   * ============================================================ */

  function currentRoute() {
    var h = location.hash.replace(/^#/, "");
    if (!h || h === "/") return { name: "home" };
    var m;
    if ((m = h.match(/^\/day\/(\d+)$/))) return { name: "day", day: parseInt(m[1], 10) };
    if (h === "/generating") return { name: "generating" };
    if (h === "/result") return { name: "result" };
    if (h === "/inspiration") return { name: "inspiration" };
    return { name: "home" };
  }

  /** 离开定制中页面时，取消进行中的请求与计时器 */
  function cancelGeneration() {
    var g = store.gen;
    g.timers.forEach(clearTimeout);
    g.timers = [];
    if (g.elapsedTimer) {
      clearInterval(g.elapsedTimer);
      g.elapsedTimer = null;
    }
    if (g.abort) {
      g.abort.abort();
      g.abort = null;
    }
    g.running = false;
  }

  function router() {
    cancelGeneration();
    var route = currentRoute();
    var view = $("#view");

    // 导航高亮
    $all(".nav-link").forEach(function (a) {
      var key = a.getAttribute("data-nav");
      var active =
        (key === "home" && ["home", "generating", "result", "day"].indexOf(route.name) !== -1) ||
        (key === "inspiration" && route.name === "inspiration");
      a.classList.toggle("active", !!active);
    });

    switch (route.name) {
      case "generating":
        renderGenerating(view);
        break;
      case "result":
        renderResult(view);
        break;
      case "day":
        renderDay(view, route.day);
        break;
      case "inspiration":
        renderHome(view);
        scrollToInspiration();
        break;
      default:
        renderHome(view);
    }
    // 移动端切页后回到顶部
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function scrollToInspiration() {
    var target = $("#inspiration");
    if (target) {
      setTimeout(function () {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 60);
    }
  }

  /* ============================================================
   * 视图：首页（需求定制 + 灵感速览）
   * ============================================================ */

  function renderHome(root) {
    var d = store.draft;
    var interestChips = INTERESTS.map(function (name) {
      var on = d.interests.indexOf(name) !== -1;
      return (
        '<button type="button" class="chip' + (on ? " active" : "") + '" data-interest="' +
        escapeHtml(name) + '" aria-pressed="' + on + '">' + escapeHtml(name) + "</button>"
      );
    }).join("");
    var cityChips = HOT_CITIES.map(function (c) {
      return (
        '<button type="button" class="chip' + (d.destination === c ? " active" : "") +
        '" data-city="' + escapeHtml(c) + '">' + escapeHtml(c) + "</button>"
      );
    }).join("");
    var companionBtns = COMPANIONS.map(function (c) {
      return (
        '<button type="button" class="seg-btn' + (d.companions === c.value ? " active" : "") +
        '" data-companion="' + c.value + '">' + c.label + "</button>"
      );
    }).join("");
    var paceBtns = PACES.map(function (p) {
      return (
        '<button type="button" class="seg-btn' + (d.pace === p.value ? " active" : "") +
        '" data-pace="' + p.value + '">' + p.label + "</button>"
      );
    }).join("");

    root.innerHTML =
      '<section class="hero">' +
        '<div class="hero-eyebrow"><svg class="icon"><use href="#i-sparkle"/></svg>AI 攻略定制</div>' +
        '<h1 class="hero-title">说出你的旅行想法，<br />换回一份<em>可执行的逐日攻略</em></h1>' +
        '<p class="hero-sub">填写目的地、天数与偏好，助手会检索真实景点、按地理位置规划路线、拆解预算，' +
        '并逐项校验后交给你 —— 全程约半分钟。</p>' +
        '<div class="hero-cta-row">' +
          '<a href="#planner-form" class="btn btn-lg btn-hero-light" id="start-btn">开始定制攻略' +
            '<svg class="icon"><use href="#i-arrow-right"/></svg></a>' +
          '<a href="#/inspiration" class="btn btn-lg btn-hero-ghost">先找点灵感</a>' +
        '</div>' +
        '<div class="hero-stats">' +
          '<span class="hero-stat"><svg class="icon"><use href="#i-pin"/></svg>高德真实景点数据</span>' +
          '<span class="hero-stat"><svg class="icon"><use href="#i-route"/></svg>地理就近排程</span>' +
          '<span class="hero-stat"><svg class="icon"><use href="#i-shield"/></svg>预算与景点逐项校验</span>' +
        '</div>' +
      '</section>' +

      '<section class="planner-card" id="planner-form">' +
        '<div class="planner-head">' +
          '<div class="planner-head-icon"><svg class="icon"><use href="#i-edit"/></svg></div>' +
          '<div><h2>定制我的旅行攻略</h2><p>带 <span style="color:var(--c-danger)">*</span> 为必填，其余均可留空</p></div>' +
        '</div>' +
        '<div class="planner-body">' +
          '<div class="form-grid">' +
            '<div class="field span-2">' +
              '<span class="field-label"><svg class="icon"><use href="#i-pin"/></svg>目的地 <i style="color:var(--c-danger);font-style:normal">*</i></span>' +
              '<input id="f-destination" class="input" type="text" maxlength="40" placeholder="想去的城市，如：杭州" value="' + escapeHtml(d.destination) + '" />' +
              '<div class="chips-row" style="margin-top:10px">' + cityChips + '</div>' +
              '<div class="field-error" id="err-destination"><svg class="icon"><use href="#i-alert-circle"/></svg><span></span></div>' +
            '</div>' +

            '<div class="field">' +
              '<span class="field-label"><svg class="icon"><use href="#i-calendar"/></svg>出行日期 <span class="optional">选填，可自动算天数</span></span>' +
              '<div class="date-days-row">' +
                '<div class="date-field"><input id="f-depart" class="input" type="date" value="' + escapeHtml(d.departDate) + '" /></div>' +
                '<div class="date-field"><input id="f-return" class="input" type="date" value="' + escapeHtml(d.returnDate) + '" /></div>' +
              '</div>' +
              '<div class="field-error" id="err-return"><svg class="icon"><use href="#i-alert-circle"/></svg><span></span></div>' +
            '</div>' +

            '<div class="field days-block">' +
              '<span class="field-label"><svg class="icon"><use href="#i-clock"/></svg>行程天数</span>' +
              '<div class="stepper">' +
                '<button type="button" class="stepper-btn" id="days-minus" aria-label="减少一天">−</button>' +
                '<div class="stepper-num num" id="days-num">' + d.days + '<small>天（1~15）</small></div>' +
                '<button type="button" class="stepper-btn" id="days-plus" aria-label="增加一天">＋</button>' +
              '</div>' +
              '<div class="field-error" id="err-days"><svg class="icon"><use href="#i-alert-circle"/></svg><span></span></div>' +
            '</div>' +

            '<div class="field">' +
              '<span class="field-label"><svg class="icon"><use href="#i-wallet"/></svg>总预算（元） <span class="optional">选填</span></span>' +
              '<input id="f-budget" class="input num" type="number" min="0" step="100" placeholder="不限预算请留空" value="' + (d.budget > 0 ? d.budget : "") + '" />' +
              '<div class="chips-row" style="margin-top:10px">' +
                '<button type="button" class="chip" data-budget="1500">¥1500</button>' +
                '<button type="button" class="chip" data-budget="3000">¥3000</button>' +
                '<button type="button" class="chip" data-budget="5000">¥5000</button>' +
                '<button type="button" class="chip" data-budget="8000">¥8000</button>' +
                '<button type="button" class="chip" data-budget="0">不限</button>' +
              '</div>' +
              '<div class="field-error" id="err-budget"><svg class="icon"><use href="#i-alert-circle"/></svg><span></span></div>' +
            '</div>' +

            '<div class="field">' +
              '<span class="field-label"><svg class="icon"><use href="#i-users"/></svg>和谁一起</span>' +
              '<div class="seg">' + companionBtns + '</div>' +
            '</div>' +

            '<div class="field">' +
              '<span class="field-label"><svg class="icon"><use href="#i-zap"/></svg>出行节奏</span>' +
              '<div class="seg">' + paceBtns + '</div>' +
            '</div>' +

            '<div class="field span-2">' +
              '<span class="field-label"><svg class="icon"><use href="#i-star"/></svg>兴趣偏好 <span class="optional">可多选，帮助推荐更合口味</span></span>' +
              '<div class="chips-row">' + interestChips + '</div>' +
            '</div>' +

            '<div class="field span-2">' +
              '<span class="field-label"><svg class="icon"><use href="#i-edit"/></svg>补充说明 <span class="optional">选填</span></span>' +
              '<textarea id="f-note" class="textarea" maxlength="500" placeholder="任何想告诉助手的事，如：第一次去、带老人小孩、想看日落、不吃辣…">' + escapeHtml(d.note) + '</textarea>' +
            '</div>' +
          '</div>' +

          '<div class="form-actions">' +
            '<button type="button" class="btn btn-primary btn-lg" id="generate-btn">' +
              '<svg class="icon"><use href="#i-sparkle"/></svg>生成我的专属攻略</button>' +
            '<span class="form-note">生成过程约需 20~90 秒，期间会检索真实景点数据</span>' +
          '</div>' +
        '</div>' +
      '</section>' +

      '<section class="insp-section" id="inspiration">' +
        '<div class="sec-head"><h2>灵感速览</h2><span class="sec-more">查一查再决定去哪儿</span></div>' +
        '<p class="sec-sub">实时天气、热门景点、特色美食 —— 数据来自高德地图，输入城市即刻查看。</p>' +
        '<div class="insp-card">' +
          '<div class="insp-controls">' +
            '<div class="seg" id="insp-tabs">' +
              '<button type="button" class="seg-btn' + (store.insp.tab === "weather" ? " active" : "") + '" data-tab="weather">实时天气</button>' +
              '<button type="button" class="seg-btn' + (store.insp.tab === "spots" ? " active" : "") + '" data-tab="spots">热门景点</button>' +
              '<button type="button" class="seg-btn' + (store.insp.tab === "food" ? " active" : "") + '" data-tab="food">特色美食</button>' +
            '</div>' +
            '<input id="insp-city" class="input" type="text" maxlength="40" placeholder="城市名，如：成都" value="' + escapeHtml(store.insp.city) + '" />' +
            '<button type="button" class="btn btn-secondary" id="insp-search"><svg class="icon"><use href="#i-search"/></svg>查一查</button>' +
          '</div>' +
          '<div class="insp-result" id="insp-result"></div>' +
        '</div>' +
      '</section>';

    bindHome(root);
    bindInspiration(root);
    renderInspResult();
  }

  function bindHome(root) {
    // Hero CTA：平滑滚动到表单
    var startBtn = $("#start-btn", root);
    if (startBtn) {
      startBtn.addEventListener("click", function (e) {
        e.preventDefault();
        $("#planner-form").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }

    var draft = store.draft;

    // 目的地输入 + 热门城市
    var destInput = $("#f-destination", root);
    destInput.addEventListener("input", function () {
      draft.destination = destInput.value;
      clearFieldError("#err-destination", destInput);
      // 同步热门城市选中态
      $all("[data-city]", root).forEach(function (chip) {
        chip.classList.toggle("active", chip.getAttribute("data-city") === draft.destination.trim());
      });
      saveDraft();
    });
    $all("[data-city]", root).forEach(function (chip) {
      chip.addEventListener("click", function () {
        draft.destination = chip.getAttribute("data-city");
        destInput.value = draft.destination;
        $all("[data-city]", root).forEach(function (c) {
          c.classList.toggle("active", c === chip);
        });
        clearFieldError("#err-destination", destInput);
        saveDraft();
      });
    });

    // 日期 → 自动算天数
    var departInput = $("#f-depart", root);
    var returnInput = $("#f-return", root);
    var today = new Date().toISOString().slice(0, 10);
    departInput.min = today;
    returnInput.min = today;
    function onDateChange() {
      draft.departDate = departInput.value;
      draft.returnDate = returnInput.value;
      clearFieldError("#err-return", returnInput);
      var n = daysFromDates(draft);
      if (n !== null) {
        draft.days = Math.min(n, 15);
        updateDaysNum();
      }
      saveDraft();
    }
    departInput.addEventListener("change", onDateChange);
    returnInput.addEventListener("change", onDateChange);

    // 天数步进
    function updateDaysNum() {
      $("#days-num", root).innerHTML = draft.days + "<small>天（1~15）</small>";
      $("#days-minus", root).disabled = draft.days <= 1;
      $("#days-plus", root).disabled = draft.days >= 15;
    }
    $("#days-minus", root).addEventListener("click", function () {
      if (draft.days > 1) {
        draft.days -= 1;
        updateDaysNum();
        saveDraft();
      }
    });
    $("#days-plus", root).addEventListener("click", function () {
      if (draft.days < 15) {
        draft.days += 1;
        updateDaysNum();
        saveDraft();
      }
    });
    updateDaysNum();

    // 预算
    var budgetInput = $("#f-budget", root);
    budgetInput.addEventListener("input", function () {
      var v = parseInt(budgetInput.value, 10);
      draft.budget = isNaN(v) ? 0 : Math.max(v, 0);
      clearFieldError("#err-budget", budgetInput);
      $all("[data-budget]", root).forEach(function (chip) {
        chip.classList.toggle("active", Number(chip.getAttribute("data-budget")) === draft.budget);
      });
      saveDraft();
    });
    $all("[data-budget]", root).forEach(function (chip) {
      chip.addEventListener("click", function () {
        var v = Number(chip.getAttribute("data-budget"));
        draft.budget = v;
        budgetInput.value = v === 0 ? "" : v;
        $all("[data-budget]", root).forEach(function (c) {
          c.classList.toggle("active", c === chip);
        });
        saveDraft();
      });
    });
    // 恢复预算选中态（含「不限」= 0）
    $all("[data-budget]", root).forEach(function (chip) {
      chip.classList.toggle("active", Number(chip.getAttribute("data-budget")) === draft.budget);
    });

    // 同行人 / 节奏
    $all("[data-companion]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        draft.companions = btn.getAttribute("data-companion");
        $all("[data-companion]", root).forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        saveDraft();
      });
    });
    $all("[data-pace]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        draft.pace = btn.getAttribute("data-pace");
        $all("[data-pace]", root).forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        saveDraft();
      });
    });

    // 兴趣偏好多选
    $all("[data-interest]", root).forEach(function (chip) {
      chip.addEventListener("click", function () {
        var name = chip.getAttribute("data-interest");
        var idx = draft.interests.indexOf(name);
        if (idx === -1) draft.interests.push(name);
        else draft.interests.splice(idx, 1);
        chip.classList.toggle("active", idx === -1);
        chip.setAttribute("aria-pressed", idx === -1 ? "true" : "false");
        saveDraft();
      });
    });

    // 补充说明
    var noteInput = $("#f-note", root);
    noteInput.addEventListener("input", function () {
      draft.note = noteInput.value;
      saveDraft();
    });

    // 提交
    $("#generate-btn", root).addEventListener("click", submitPlanRequest);
  }

  /* ============================================================
   * 首页：灵感速览（天气 / 景点 / 美食 即时查询）
   * ============================================================ */

  function bindInspiration(root) {
    $all("#insp-tabs .seg-btn", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        store.insp.tab = btn.getAttribute("data-tab");
        $all("#insp-tabs .seg-btn", root).forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        renderInspResult();
      });
    });

    var cityInput = $("#insp-city", root);
    var searchBtn = $("#insp-search", root);

    function doSearch() {
      var city = cityInput.value.trim();
      if (!city) {
        toast("先输入城市名，再查一查", "err");
        cityInput.focus();
        return;
      }
      store.insp.city = city;
      fetchInsp(city, store.insp.tab);
    }

    searchBtn.addEventListener("click", doSearch);
    cityInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        doSearch();
      }
    });
  }

  var inspAbort = null;

  /** 按城市 + 标签发起查询；结果以 city|tab 为键缓存，切标签不重复请求 */
  function fetchInsp(city, tab) {
    if (inspAbort) inspAbort.abort();
    inspAbort = new AbortController();
    store.insp.loading = true;
    store.insp.error = null;
    renderInspResult();

    var p;
    if (tab === "weather") {
      p = Api.fetchWeather(city, inspAbort.signal).then(function (r) {
        var d = r.data || {};
        return { weather: d.weather || "暂无天气信息", dressing: d.dressing_advice || "" };
      });
    } else if (tab === "spots") {
      p = Api.fetchSpots(city, 6, inspAbort.signal).then(function (r) {
        return { pois: r.data || [], count: r.count || 0 };
      });
    } else {
      p = Api.fetchFood(city, 6, inspAbort.signal).then(function (r) {
        return { pois: r.data || [], count: r.count || 0 };
      });
    }

    p.then(
      function (data) {
        store.insp.loading = false;
        store.insp.results = store.insp.results || {};
        store.insp.results[city + "|" + tab] = data;
        renderInspResult();
      },
      function (err) {
        if (err && err.kind === "aborted") return; // 被新查询取代，无需提示
        store.insp.loading = false;
        store.insp.error = err;
        renderInspResult();
      }
    );
  }

  function poiCard(p, kind) {
    var biz = p.biz_ext || {};
    var badges = "";
    if (biz.rating) {
      badges += '<span class="rating-badge">★ ' + escapeHtml(biz.rating) + "</span>";
    }
    if (biz.cost) {
      badges += '<span class="price-badge">¥' + escapeHtml(biz.cost) + (kind === "food" ? " 人均" : " 起") + "</span>";
    }
    return (
      '<div class="poi-card">' +
        '<div class="poi-name"><svg class="icon"><use href="#' + (kind === "food" ? "i-food" : "i-pin") + '"/></svg>' +
          escapeHtml(p.name || "未知地点") + "</div>" +
        '<div class="poi-addr">' + escapeHtml(p.address || "地址暂缺") + "</div>" +
        (badges ? '<div class="poi-meta">' + badges + "</div>" : "") +
      "</div>"
    );
  }

  function renderInspResult() {
    var box = $("#insp-result");
    if (!box) return;
    var st = store.insp;

    // 加载中：骨架屏
    if (st.loading) {
      box.innerHTML =
        '<div class="poi-grid" style="margin-top:4px">' +
          '<div class="skeleton-card" style="padding:14px 16px"><div class="skeleton-line w60"></div><div class="skeleton-line w80" style="margin-bottom:0"></div></div>' +
          '<div class="skeleton-card" style="padding:14px 16px"><div class="skeleton-line w80"></div><div class="skeleton-line w60" style="margin-bottom:0"></div></div>' +
          '<div class="skeleton-card" style="padding:14px 16px"><div class="skeleton-line w40"></div><div class="skeleton-line w80" style="margin-bottom:0"></div></div>' +
        "</div>";
      return;
    }

    // 查询失败：错误态 + 重试
    if (st.error) {
      var errDesc =
        st.error.status === 502
          ? "旅行数据服务暂时没有响应，稍后再试通常就能恢复。"
          : st.error.message || "查询失败，请检查网络后重试。";
      box.innerHTML =
        '<div class="state-block compact error">' +
          '<div class="state-emoji">📡</div>' +
          '<h3 class="state-title">查询失败</h3>' +
          '<p class="state-desc">' + escapeHtml(errDesc) + "</p>" +
          (st.error.requestId ? '<div class="err-detail">追踪 ID：' + escapeHtml(st.error.requestId) + "</div>" : "") +
          '<div class="state-actions"><button type="button" class="btn btn-secondary" id="insp-retry">' +
            '<svg class="icon"><use href="#i-refresh"/></svg>重试</button></div>' +
        "</div>";
      $("#insp-retry", box).addEventListener("click", function () {
        fetchInsp(st.city, st.tab);
      });
      return;
    }

    var cached = st.results && st.results[st.city + "|" + st.tab];

    // 未查询：空态引导
    if (!st.city || !cached) {
      box.innerHTML =
        '<div class="state-block compact">' +
          '<div class="state-emoji">🧭</div>' +
          '<h3 class="state-title">先从一座城市开始</h3>' +
          '<p class="state-desc">输入城市名，看看那里的实时天气、热门景点和特色美食，再决定要不要去。</p>' +
        "</div>";
      return;
    }

    if (st.tab === "weather") {
      box.innerHTML =
        '<div class="weather-box">' +
          '<div class="pre-text">' + escapeHtml(cached.weather) + "</div>" +
          (cached.dressing
            ? '<div class="dressing-box"><strong>穿搭建议：</strong>' + escapeHtml(cached.dressing) + "</div>"
            : "") +
        "</div>";
      return;
    }

    // 景点 / 美食
    if (!cached.pois.length) {
      box.innerHTML =
        '<div class="state-block compact">' +
          '<div class="state-emoji">🍂</div>' +
          '<h3 class="state-title">没有查到相关结果</h3>' +
          '<p class="state-desc">换一座城市或换个写法试试，比如「西安」或「西安市」。</p>' +
        "</div>";
      return;
    }
    box.innerHTML =
      '<div class="poi-grid">' +
        cached.pois.map(function (p) { return poiCard(p, st.tab); }).join("") +
      "</div>";
  }

  function clearFieldError(errSel, input) {
    var err = $(errSel);
    if (err) err.classList.remove("show");
    if (input) input.classList.remove("invalid");
  }
  function showFieldError(errSel, input, message) {
    var err = $(errSel);
    if (err) {
      err.classList.add("show");
      $("span", err).textContent = message;
    }
    if (input) input.classList.add("invalid");
  }

  function submitPlanRequest() {
    var root = $("#view");
    var d = store.draft;
    d.destination = ($("#f-destination", root).value || "").trim();
    d.note = ($("#f-note", root).value || "");

    var errors = validateDraft(d);
    if (errors.destination) {
      showFieldError("#err-destination", $("#f-destination", root), errors.destination);
    }
    if (errors.returnDate) {
      showFieldError("#err-return", $("#f-return", root), errors.returnDate);
    }
    if (errors.budget) {
      showFieldError("#err-budget", $("#f-budget", root), errors.budget);
    }
    if (Object.keys(errors).length) {
      toast("请先完善表单中标红的内容", "err");
      return;
    }
    saveDraft();

    var message = compileMessage(d);
    store.gen.pendingMessage = message;
    store.gen.running = false; // 由 generating 视图接管并真正发起请求
    location.hash = "#/generating";
  }

  /* ============================================================
   * 视图：定制中（管线进度 + 错误态）
   * ============================================================ */

  var GEN_STEPS = [
    { icon: "i-edit", title: "解析旅行需求", desc: "提取目的地、天数与预算" },
    { icon: "i-pin", title: "检索真实景点", desc: "从高德地图获取景点池" },
    { icon: "i-route", title: "规划就近路线", desc: "按地理位置逐日排程" },
    { icon: "i-food", title: "调研餐饮住宿", desc: "查询美食与住宿参考" },
    { icon: "i-sparkle", title: "生成行程草稿", desc: "逐日安排与费用估算" },
    { icon: "i-shield", title: "校验行程质量", desc: "预算算术与景点核对" },
  ];
  // 各阶段推进时刻（秒）：最后两步持有到请求返回，匹配真实管线耗时特征
  var GEN_STEP_TIMES = [0, 1200, 2400, 3600, 4800, 6000];

  function renderGenerating(root) {
    var g = store.gen;
    // 直接进入本页但没有任何需求输入时，引导回表单
    if (!g.pendingMessage && !store.draft.destination.trim()) {
      location.hash = "#/";
      return;
    }
    var message = g.pendingMessage || compileMessage(store.draft);

    root.innerHTML =
      '<div class="gen-wrap">' +
        '<div class="gen-card" id="gen-card">' +
          '<div class="gen-orbit">' +
            '<div class="gen-orbit-ring"></div>' +
            '<div class="gen-orbit-core"><svg class="icon"><use href="#i-compass"/></svg></div>' +
          '</div>' +
          '<h1 class="gen-title">正在为你定制攻略…</h1>' +
          '<p class="gen-sub">' + escapeHtml(truncate(message, 46)) + '</p>' +
          '<p class="gen-elapsed num" id="gen-elapsed">已用时 0 秒 · 通常需要 20~90 秒</p>' +
          '<div class="gen-steps" id="gen-steps">' + genStepsHtml(-1) + '</div>' +
        '</div>' +
      '</div>';

    if (!g.running) startPlanGeneration(message);
  }

  function genStepsHtml(activeIdx) {
    return GEN_STEPS.map(function (s, i) {
      var state = i < activeIdx ? "done" : i === activeIdx ? "active" : "";
      return (
        '<div class="gen-step ' + state + '" data-step="' + i + '">' +
          '<div class="gen-step-icon"><svg class="icon"><use href="#' + s.icon + '"/></svg></div>' +
          '<div><div class="gen-step-title">' + s.title + '</div>' +
          '<div class="gen-step-desc">' + s.desc + '</div></div>' +
          '<span class="gen-step-tick"><svg class="icon"><use href="#i-check-circle"/></svg></span>' +
        '</div>'
      );
    }).join("");
  }

  function truncate(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function setGenStep(idx) {
    var steps = $all("#gen-steps .gen-step");
    steps.forEach(function (el, i) {
      el.classList.toggle("done", i < idx);
      el.classList.toggle("active", i === idx);
    });
  }

  function startPlanGeneration(message) {
    var g = store.gen;
    g.running = true;
    g.pendingMessage = message;
    g.abort = new AbortController();
    var startedAt = Date.now();
    var finished = false;

    // 计时器
    g.elapsedTimer = setInterval(function () {
      var el = $("#gen-elapsed");
      if (el) el.textContent = "已用时 " + Math.round((Date.now() - startedAt) / 1000) + " 秒 · 通常需要 20~90 秒";
    }, 1000);

    // 阶段推进动画：全部推进后停留在最后一步，等待真实响应
    GEN_STEP_TIMES.forEach(function (t, i) {
      g.timers.push(setTimeout(function () {
        if (!finished) setGenStep(i);
      }, t));
    });

    Api.fetchPlan(message, store.sessionId, g.abort.signal).then(
      function (resp) {
        finished = true;
        cancelGenerationTimersOnly();
        setGenStep(GEN_STEPS.length); // 全部点亮
        store.plan = { data: resp.data, message: message, createdAt: Date.now() };
        savePlan();
        setTimeout(function () {
          location.hash = "#/result";
        }, 450);
      },
      function (err) {
        finished = true;
        cancelGenerationTimersOnly();
        if (err && err.kind === "aborted") return; // 用户离开页面，静默
        g.running = false;
        g.abort = null;
        renderGenError(err);
      }
    );
  }

  /** 仅清计时器，不改 running 状态（成功路径使用） */
  function cancelGenerationTimersOnly() {
    var g = store.gen;
    g.timers.forEach(clearTimeout);
    g.timers = [];
    if (g.elapsedTimer) {
      clearInterval(g.elapsedTimer);
      g.elapsedTimer = null;
    }
  }

  /** 定制失败：按错误类型渲染差异化错误态 */
  function renderGenError(err) {
    var card = $("#gen-card");
    if (!card) return;
    var title;
    var desc;
    var actions = "";

    if (err.kind === "timeout") {
      title = "定制时间比预期长";
      desc = "等待响应超时了。可能是网络波动或服务繁忙，稍等片刻重试通常就能成功。";
    } else if (err.kind === "network") {
      title = "无法连接服务";
      desc = "请确认后端服务已启动（uvicorn src.api.main:app），并检查连接设置。";
      actions += '<button type="button" class="btn btn-secondary" id="gen-open-settings">检查连接设置</button>';
    } else if (err.kind === "upstream") {
      title = "服务暂时不可用";
      desc = "行程数据服务（高德 / 模型服务）暂时没有响应，请稍后重试，或先调整一下需求描述。";
    } else {
      // client：400 / 422 / 401 等
      title = err.status === 401 ? "需要鉴权" : "需求暂时无法处理";
      desc = err.message || "请检查需求描述后重试。";
    }

    actions +=
      '<button type="button" class="btn btn-primary" id="gen-retry">' +
      '<svg class="icon"><use href="#i-refresh"/></svg>重试</button>' +
      '<button type="button" class="btn btn-secondary" id="gen-back">返回修改需求</button>';

    card.innerHTML =
      '<div class="state-emoji">🌧️</div>' +
      '<h1 class="state-title">' + escapeHtml(title) + '</h1>' +
      '<p class="state-desc">' + escapeHtml(desc) + '</p>' +
      (err.requestId ? '<div class="err-detail">追踪 ID：' + escapeHtml(err.requestId) + '</div>' : "") +
      '<div class="state-actions">' + actions + '</div>';

    $("#gen-retry").addEventListener("click", function () {
      store.gen.running = false;
      renderGenerating($("#view"));
    });
    $("#gen-back").addEventListener("click", function () {
      location.hash = "#/";
    });
    var settingsBtn = $("#gen-open-settings");
    if (settingsBtn) {
      settingsBtn.addEventListener("click", function () {
        openSettings();
      });
    }
  }

  /* ============================================================
   * 视图：定制结果（总览）
   * ============================================================ */

  function renderResult(root) {
    if (!store.plan) {
      root.innerHTML =
        '<div class="state-block">' +
          '<div class="state-emoji">🗺️</div>' +
          '<h1 class="state-title">还没有定制结果</h1>' +
          '<p class="state-desc">填写目的地和偏好，助手会为你生成一份可执行的逐日攻略。</p>' +
          '<div class="state-actions">' +
            '<a class="btn btn-primary" href="#/">去定制攻略</a>' +
          '</div>' +
        '</div>';
      return;
    }

    var data = store.plan.data;
    var plan = data.plan || {};
    var ver = data.verification || {};
    var schedule = data.schedule || [];
    var params = data.params || {};
    var floor = data.budget_floor || {};
    var draft = store.draft;

    var days = plan.days || (plan.day_plans || []).length || 1;
    var total = plan.total_estimated_cost || 0;
    var budget = params.budget || 0;
    var dest = plan.destination || params.destination || "目的地";
    var distTotal = schedule.reduce(function (s, d) {
      return s + (Number(d.est_distance_km) || 0);
    }, 0);

    // --- 校验徽章与提示 ---
    var issueCount = (ver.issues || []).length;
    var warnCount = (ver.warnings || []).length;
    var badge = ver.ok
      ? '<span class="verify-badge ok"><svg class="icon"><use href="#i-shield"/></svg>已通过质量校验</span>'
      : '<span class="verify-badge warn"><svg class="icon"><use href="#i-alert-triangle"/></svg>有 ' + (issueCount + warnCount) + ' 条校验提示</span>';

    // --- 预算进度条 ---
    var budgetHtml;
    if (budget > 0) {
      var pct = Math.min((total / budget) * 100, 100);
      var over = total > budget;
      budgetHtml =
        '<div class="budget-track"><div class="budget-fill' + (over ? " over" : "") + '" style="width:' + Math.max(pct, 4).toFixed(1) + '%"></div></div>' +
        '<div class="budget-nums"><span>估算 <strong class="num">¥' + fmtMoney(total) + '</strong></span>' +
        (over
          ? '<span class="over-note">超出预算 ¥' + fmtMoney(total - budget) + '，可调整天数或偏好</span>'
          : '<span>预算 ¥' + fmtMoney(budget) + ' · 还余 ¥' + fmtMoney(budget - total) + '</span>') +
        '</div>';
    } else {
      budgetHtml =
        '<div class="budget-nums" style="margin-top:0"><span>估算总额</span><span><strong class="num">¥' + fmtMoney(total) + '</strong>（未设预算上限）</span></div>';
    }

    // --- 费用拆分（确定性下限 + 住宿估算） ---
    var splitItems = [
      { key: "住宿（估算）", value: Number(plan.hotel_est_cost_total) || 0, color: "#1f7fa8" },
      { key: "餐饮（下限）", value: Number(floor.food_total) || 0, color: "#0e9384" },
      { key: "市内交通（估算）", value: Number(floor.transit_total) || 0, color: "#ffc53d" },
      { key: "门票等（如含）", value: Number(floor.tickets_total) || 0, color: "#ff7a59" },
    ];
    var splitSum = splitItems.reduce(function (s, it) { return s + it.value; }, 0);
    var splitBar = splitItems
      .filter(function (it) { return it.value > 0; })
      .map(function (it) {
        var w = splitSum > 0 ? (it.value / splitSum) * 100 : 0;
        return '<div class="split-seg" style="width:' + w.toFixed(1) + '%;background:' + it.color + '"></div>';
      })
      .join("");
    var splitLegend = splitItems
      .filter(function (it) { return it.value > 0; })
      .map(function (it) {
        return '<span class="legend-item"><span class="legend-dot" style="background:' + it.color + '"></span>' +
          it.key + ' <strong class="num">¥' + fmtMoney(it.value) + '</strong></span>';
      })
      .join("");

    // --- 偏好回显 ---
    function prefRow(label, body) {
      return '<div class="pref-row"><span class="pref-row-label">' + label + '</span><div class="pref-row-body">' + body + '</div></div>';
    }
    var interestsHtml = draft.interests.length
      ? draft.interests.map(function (i) { return '<span class="tag">' + escapeHtml(i) + "</span>"; }).join("")
      : '<span class="tag plain">未选择</span>';
    var prefHtml =
      prefRow("目的地", '<span class="tag">' + escapeHtml(dest) + "</span>") +
      prefRow("出行天数", '<span class="tag num">' + days + " 天</span>") +
      prefRow("预算", budget > 0 ? '<span class="tag num">¥' + fmtMoney(budget) + "</span>" : '<span class="tag plain">不限</span>') +
      prefRow("同行人", '<span class="tag plain">' + escapeHtml(companionLabel(draft.companions) || "未选择") + "</span>") +
      prefRow("节奏", '<span class="tag plain">' + escapeHtml(paceLabel(draft.pace) || "标准节奏") + "</span>") +
      prefRow("兴趣", interestsHtml) +
      (draft.note && draft.note.trim()
        ? prefRow("补充", '<span style="font-size:13px;color:var(--c-ink-2);line-height:1.7">' + escapeHtml(draft.note.trim()) + "</span>")
        : "");

    // --- 逐日卡片 ---
    var scheduleByDay = {};
    schedule.forEach(function (d) {
      scheduleByDay[d.day] = d;
    });
    var dayCards = (plan.day_plans || []).map(function (dp) {
      var sched = scheduleByDay[dp.day] || {};
      var spots = (sched.spots && sched.spots.length ? sched.spots : dp.spots) || [];
      var spotsHtml = spots.length
        ? spots.map(function (s) {
            return '<span class="spot-chip"><svg class="icon"><use href="#i-pin"/></svg>' + escapeHtml(s) + "</span>";
          }).join("")
        : '<span class="tag plain">当日安排以整体建议为准</span>';
      return (
        '<button type="button" class="day-card" data-day="' + dp.day + '">' +
          '<div class="day-card-top">' +
            '<div class="day-badge"><small>DAY</small>' + dp.day + '</div>' +
            '<div><div class="day-title">' + escapeHtml(dp.title || "第 " + dp.day + " 天") + '</div>' +
            '<div class="day-title-sub">点击查看逐点详情与真实路线</div></div>' +
            '<span class="day-card-go"><svg class="icon"><use href="#i-chevron-right"/></svg></span>' +
          '</div>' +
          '<div class="day-spots">' + spotsHtml + '</div>' +
          '<div class="day-meta">' +
            '<span><svg class="icon"><use href="#i-wallet"/></svg>当日预算约 ¥<b class="num">' + fmtMoney(dp.estimated_cost) + "</b></span>" +
            (sched.est_distance_km
              ? '<span><svg class="icon"><use href="#i-route"/></svg>移动约 <b class="num">' + sched.est_distance_km + '</b> 公里</span>'
              : "") +
            '<span><svg class="icon"><use href="#i-pin"/></svg>' + spots.length + " 个点位</span>" +
          '</div>' +
        '</button>'
      );
    }).join("");

    // --- 美食 / 贴士 ---
    var foodHtml = (plan.food_recommendations || []).length
      ? '<ul class="plain-list">' +
        plan.food_recommendations.map(function (f, i) {
          return '<li><span class="li-idx num">' + (i + 1) + "</span><span>" + escapeHtml(f) + "</span></li>";
        }).join("") + "</ul>"
      : '<p style="font-size:13.5px;color:var(--c-ink-3)">本次定制暂未返回美食推荐，可在结果页左下角问助手补一份。</p>';

    var tipsLines = String(plan.general_tips || "")
      .split(/\n+/)
      .filter(function (l) { return l.trim(); });
    var tipsHtml = tipsLines.length
      ? '<div class="tips-box">' + tipsLines.map(function (l) {
          return "<p style='margin:2px 0'>" + escapeHtml(l.trim()) + "</p>";
        }).join("") + "</div>"
      : '<p style="font-size:13.5px;color:var(--c-ink-3)">暂无特别提示，出行前建议再核对景点开放时间。</p>';

    // --- 校验提示卡 ---
    var warnHtml = "";
    if (issueCount || warnCount || ver.over_budget) {
      var warnLines = (ver.issues || []).concat(ver.warnings || []);
      if (ver.over_budget) {
        warnLines.unshift("行程估算超出你设定的预算，请酌情精简天数或选择更经济的档位。");
      }
      warnHtml =
        '<div class="warn-card"><strong><svg class="icon" style="width:14px;height:14px;vertical-align:-2px"><use href="#i-alert-triangle"/></svg> 校验提示</strong>' +
        '<ul>' + warnLines.map(function (w) { return "<li>" + escapeHtml(w) + "</li>"; }).join("") + "</ul></div>";
    }

    var planDate = store.plan.createdAt
      ? new Date(store.plan.createdAt).toLocaleDateString("zh-CN", { month: "long", day: "numeric" })
      : "";

    root.innerHTML =
      '<div class="crumbs"><a href="#/">定制攻略</a><svg class="icon"><use href="#i-chevron-right"/></svg><span>定制结果</span></div>' +

      '<section class="res-hero">' +
        '<div class="res-hero-top">' +
          '<div class="res-hero-main">' +
            '<span class="res-eyebrow">专属行程 · ' + escapeHtml(planDate) + '生成</span>' +
            '<h1 class="res-dest">' + escapeHtml(dest) + " " + days + '日攻略</h1>' +
            '<p class="res-dest-sub">基于真实景点数据排程，按地理位置就近串联，费用已逐项校验</p>' +
            '<div class="res-chips">' +
              '<span class="res-chip"><svg class="icon"><use href="#i-calendar"/></svg>' + days + " 天" + Math.max(days - 1, 0) + ' 晚</span>' +
              '<span class="res-chip"><svg class="icon"><use href="#i-wallet"/></svg>估算 ¥' + fmtMoney(total) + "</span>" +
              (budget > 0
                ? '<span class="res-chip"><svg class="icon"><use href="#i-flag"/></svg>目标预算 ¥' + fmtMoney(budget) + "</span>"
                : '<span class="res-chip"><svg class="icon"><use href="#i-flag"/></svg>预算不限</span>') +
              (distTotal
                ? '<span class="res-chip"><svg class="icon"><use href="#i-route"/></svg>市内移动约 ' + distTotal.toFixed(1) + ' 公里</span>'
                : "") +
            '</div>' +
          '</div>' +
          '<div>' + badge + '</div>' +
        '</div>' +
        '<div class="res-actions">' +
          '<button type="button" class="btn btn-hero-light btn-sm" id="copy-plan" style="padding:9px 18px">' +
            '<svg class="icon"><use href="#i-copy"/></svg>复制攻略全文</button>' +
          '<button type="button" class="btn btn-hero-ghost btn-sm" id="download-plan" style="padding:9px 18px">' +
            '<svg class="icon"><use href="#i-download"/></svg>下载行程单</button>' +
          '<button type="button" class="btn btn-hero-ghost btn-sm" id="replan-btn" style="padding:9px 18px">' +
            '<svg class="icon"><use href="#i-refresh"/></svg>调整偏好重新定制</button>' +
        '</div>' +
      '</section>' +

      (warnHtml ? '<div style="margin-top:16px">' + warnHtml + "</div>" : "") +

      '<div class="res-grid">' +
        '<div class="res-main">' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-calendar"/></svg>逐日安排<span class="title-extra">点击某天查看详情</span></h2>' +
            '<div class="day-list">' + dayCards + '</div>' +
          '</section>' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-food"/></svg>美食推荐</h2>' + foodHtml + '</section>' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-info"/></svg>实用贴士</h2>' + tipsHtml + '</section>' +
        '</div>' +

        '<aside class="res-side">' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-star"/></svg>你的偏好</h2>' + prefHtml +
            '<div style="margin-top:14px"><button type="button" class="btn btn-secondary btn-sm" id="edit-pref">' +
            '<svg class="icon"><use href="#i-edit"/></svg>调整偏好</button></div>' +
          '</section>' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-wallet"/></svg>费用拆分</h2>' + budgetHtml +
            (splitBar ? '<div class="split-bar">' + splitBar + '</div><div class="split-legend">' + splitLegend + "</div>" : "") +
            '<p class="field-hint">餐饮与市内交通为确定性估算下限，住宿来自行程估算；与总额的细微差异以总估算为准。</p>' +
          '</section>' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-home"/></svg>住宿建议</h2>' +
            (plan.hotel_preference
              ? '<p style="font-size:13.5px;color:var(--c-ink-2);line-height:1.8">' + escapeHtml(plan.hotel_preference) + "</p>"
              : '<p style="font-size:13.5px;color:var(--c-ink-3)">暂无住宿建议</p>') +
            (plan.hotel_est_cost_total
              ? '<p style="margin-top:10px;font-size:13px"><span class="price-badge num">住宿估算 ¥' + fmtMoney(plan.hotel_est_cost_total) + "</span></p>"
              : "") +
          '</section>' +
        '</aside>' +
      '</div>';

    bindResult(root);
  }

  function bindResult(root) {
    $all(".day-card", root).forEach(function (card) {
      card.addEventListener("click", function () {
        location.hash = "#/day/" + card.getAttribute("data-day");
      });
    });

    $("#copy-plan", root).addEventListener("click", function () {
      copyText(buildPlanText(store.plan), "攻略全文已复制，去分享吧");
    });
    $("#download-plan", root).addEventListener("click", function () {
      var dest = store.plan.data.plan.destination || "行程";
      downloadText("行程单-" + dest + ".txt", buildPlanText(store.plan));
      toast("行程单已开始下载", "ok");
    });
    $("#replan-btn", root).addEventListener("click", function () {
      location.hash = "#/";
    });
    $("#edit-pref", root).addEventListener("click", function () {
      location.hash = "#/";
      setTimeout(function () {
        var form = $("#planner-form");
        if (form) form.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 80);
    });
  }

  /** 把结构化行程导出为可读的纯文本攻略 */
  function buildPlanText(entry) {
    var data = entry.data;
    var plan = data.plan || {};
    var schedule = data.schedule || [];
    var scheduleByDay = {};
    schedule.forEach(function (d) { scheduleByDay[d.day] = d; });
    var lines = [];
    lines.push("📍 " + plan.destination + " " + plan.days + "日行程单");
    lines.push("（由智能旅行助手生成 · 费用为估算，请以实际为准）");
    lines.push("");
    (plan.day_plans || []).forEach(function (dp) {
      var sched = scheduleByDay[dp.day] || {};
      var spots = (sched.spots && sched.spots.length ? sched.spots : dp.spots) || [];
      lines.push("— 第 " + dp.day + " 天 · " + (dp.title || ""));
      lines.push("   景点：" + spots.join(" → "));
      lines.push("   当日预算：约 ¥" + (dp.estimated_cost || 0));
      if (sched.est_distance_km) lines.push("   市内移动：约 " + sched.est_distance_km + " 公里");
      lines.push("");
    });
    if ((plan.food_recommendations || []).length) {
      lines.push("🍜 美食推荐：" + plan.food_recommendations.join("、"));
    }
    if (plan.hotel_preference) {
      lines.push("🏨 住宿建议：" + plan.hotel_preference);
      if (plan.hotel_est_cost_total) lines.push("   住宿估算：¥" + plan.hotel_est_cost_total);
    }
    if (plan.general_tips) {
      lines.push("💡 实用贴士：");
      String(plan.general_tips).split(/\n+/).forEach(function (l) {
        if (l.trim()) lines.push("   " + l.trim());
      });
    }
    lines.push("💰 总预算估算：¥" + (plan.total_estimated_cost || 0));
    return lines.join("\n");
  }

  /* ============================================================
   * 视图：行程详情（单日时间线 + 真实路线）
   * ============================================================ */

  function renderDay(root, dayNum) {
    if (!store.plan) {
      location.hash = "#/result";
      return;
    }
    var data = store.plan.data;
    var plan = data.plan || {};
    var dp = (plan.day_plans || []).filter(function (d) { return d.day === dayNum; })[0];
    if (!dp) {
      root.innerHTML =
        '<div class="state-block">' +
          '<div class="state-emoji">🧭</div>' +
          '<h1 class="state-title">没有第 ' + dayNum + ' 天的安排</h1>' +
          '<p class="state-desc">这份行程共 ' + ((plan.day_plans || []).length || 1) + " 天，回到总览选择要查看的日期吧。</p>" +
          '<div class="state-actions"><a class="btn btn-primary" href="#/result">返回总览</a></div>' +
        '</div>';
      return;
    }

    var scheduleByDay = {};
    (data.schedule || []).forEach(function (d) { scheduleByDay[d.day] = d; });
    var sched = scheduleByDay[dayNum] || {};
    var spots = (sched.spots && sched.spots.length ? sched.spots : dp.spots) || [];
    var dest = plan.destination || "目的地";

    var positionNotes = ["建议上午出发，留足游览时间", "行程中段，注意体力分配", "接近傍晚，安排轻松些", "适合收尾与散步", "当天最后一段，慢慢逛"];
    var timeline = spots
      .map(function (s, i) {
        var note = i === 0 ? "建议上午出发，留足游览时间" : positionNotes[Math.min(i, positionNotes.length - 1)];
        var isLast = i === spots.length - 1;
        return (
          '<div class="tl-item' + (isLast ? " finish" : "") + '">' +
            '<div class="tl-node num">' + (i + 1) + '</div>' +
            '<div class="tl-card">' +
              '<div class="tl-name">' + escapeHtml(s) + '</div>' +
              '<div class="tl-note">' + note + "</div>" +
              (i === 0 && sched.est_distance_km
                ? '<span class="tl-order-note"><svg class="icon"><use href="#i-route"/></svg>当日全程约 ' + sched.est_distance_km + ' 公里，顺序已按地理位置就近优化</span>'
                : "") +
            '</div>' +
          '</div>'
        );
      })
      .join("");

    root.innerHTML =
      '<div class="crumbs"><a href="#/">定制攻略</a><svg class="icon"><use href="#i-chevron-right"/></svg>' +
        '<a href="#/result">定制结果</a><svg class="icon"><use href="#i-chevron-right"/></svg><span>第 ' + dayNum + ' 天</span></div>' +

        '<div class="detail-head">' +
          '<div class="day-badge"><small>DAY</small>' + dayNum + '</div>' +
          '<div><h1>' + escapeHtml(dp.title || "第 " + dayNum + " 天") + '</h1>' +
          '<span class="sub">' + escapeHtml(dest) + ' · 共 ' + spots.length + ' 个点位</span></div>' +
        '</div>' +

        '<div class="stat-chips">' +
          '<span class="stat-chip"><svg class="icon"><use href="#i-wallet"/></svg>当日预算约 <strong class="num">¥' + fmtMoney(dp.estimated_cost) + "</strong></span>" +
          (sched.est_distance_km
            ? '<span class="stat-chip"><svg class="icon"><use href="#i-route"/></svg>移动距离约 <strong class="num">' + sched.est_distance_km + "</strong> 公里</span>"
            : "") +
          '<span class="stat-chip"><svg class="icon"><use href="#i-clock"/></svg>建议时长 <strong>全天</strong></span>' +
        '</div>' +

        '<div class="detail-grid">' +
          '<section class="card">' +
            '<h2 class="card-title"><svg class="icon"><use href="#i-pin"/></svg>游览顺序</h2>' +
            '<div class="timeline">' + (timeline || '<p style="color:var(--c-ink-3);font-size:13.5px">当日暂无具体点位，建议在总览页重新定制。</p>') + '</div>' +
          '</section>' +
          '<aside class="res-side">' +
            '<section class="card">' +
              '<h2 class="card-title"><svg class="icon"><use href="#i-route"/></svg>景点间路线</h2>' +
              '<p style="font-size:13px;color:var(--c-ink-2);margin-bottom:12px">查询当日景点之间的真实驾车 / 公交路线与耗时。</p>' +
              '<div class="route-mode-row">' +
                '<div class="seg" id="route-mode">' +
                  '<button type="button" class="seg-btn active" data-mode="driving">驾车</button>' +
                  '<button type="button" class="seg-btn" data-mode="transit">公交</button>' +
                '</div>' +
                '<button type="button" class="btn btn-primary btn-sm" id="route-search" ' + (spots.length < 2 ? "disabled" : "") + '>查询路线</button>' +
              '</div>' +
              (spots.length < 2 ? '<p class="field-hint">当日点位不足 2 个，无需查询路线。</p>' : "") +
              '<div id="route-result"></div>' +
            '</section>' +
            '<section class="card">' +
              '<h2 class="card-title"><svg class="icon"><use href="#i-sparkle"/></svg>对这天不满意？</h2>' +
              '<p style="font-size:13px;color:var(--c-ink-2);line-height:1.8">让助手帮你调整节奏、换景点或推荐当天餐厅。</p>' +
              '<div style="margin-top:12px"><button type="button" class="btn btn-secondary btn-sm" id="ask-day">' +
              '<svg class="icon"><use href="#i-message"/></svg>问问 AI 助手</button></div>' +
            '</section>' +
          '</aside>' +
        '</div>';

    bindDay(root, dayNum, spots, dest);
  }

  function bindDay(root, dayNum, spots, dest) {
    var mode = "driving";
    $all("#route-mode .seg-btn", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        mode = btn.getAttribute("data-mode");
        $all("#route-mode .seg-btn", root).forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
      });
    });

    var searchBtn = $("#route-search", root);
    var resultBox = $("#route-result", root);
    searchBtn.addEventListener("click", function () {
      searchBtn.classList.add("loading");
      searchBtn.disabled = true;
      resultBox.innerHTML =
        '<div class="route-result"><div class="skeleton-line w80"></div><div class="skeleton-line w60"></div><div class="skeleton-line w40" style="margin-bottom:0"></div></div>';

      Api.fetchMultiSpotRoute(spots, dest, mode).then(
        function (resp) {
          searchBtn.classList.remove("loading");
          searchBtn.disabled = false;
          resultBox.innerHTML =
            '<div class="route-result"><div class="pre-text">' + escapeHtml(resp.data || "暂无路线信息") + "</div></div>";
        },
        function (err) {
          searchBtn.classList.remove("loading");
          searchBtn.disabled = false;
          var msg =
            err.kind === "client" && err.status === 400
              ? "部分景点名称无法定位，暂时查不到路线；可回到结果页调整偏好后重新定制。"
              : err.kind === "timeout"
              ? "路线查询超时，请再试一次。"
              : "路线服务暂时不可用，请稍后再试。";
          resultBox.innerHTML =
            '<div class="warn-card" style="margin-top:12px"><strong>路线查询失败</strong><ul><li>' +
            escapeHtml(msg) + "</li>" +
            (err.requestId ? "<li>追踪 ID：" + escapeHtml(err.requestId) + "</li>" : "") +
            "</ul></div>";
        }
      );
    });

    $("#ask-day", root).addEventListener("click", function () {
      openChat("帮我优化第 " + dayNum + " 天的安排，或者推荐这天的餐厅。");
    });
  }

  /* ============================================================
   * AI 助手抽屉（SSE 流式对话）
   * ============================================================ */

  var CHAT_GREETING =
    "你好呀！我是你的旅行助手 🌍\n\n行程定制中遇到任何疑问都可以问我，比如调整某天的安排、推荐餐厅，或聊聊目的地的注意事项。";

  function chatSuggestionChips() {
    var list = ["带父母去杭州怎么玩？", "成都有什么必吃美食？", "预算5000能去三亚几天？"];
    if (store.plan) {
      list.unshift("帮我看看这份行程还要注意什么？");
    }
    return list;
  }

  function openChat(prefill) {
    store.chat.open = true;
    var drawer = $("#chat-drawer");
    drawer.hidden = false;

    var box = $("#chat-messages");
    if (!box.childElementCount) {
      store.chat.messages = [{ role: "assistant", content: CHAT_GREETING }];
      renderChatMessages();
    }
    renderChatSuggestions();

    var input = $("#chat-input");
    if (prefill) input.value = prefill;
    setTimeout(function () {
      input.focus();
      box.scrollTop = box.scrollHeight;
    }, 60);
  }

  function closeChat() {
    store.chat.open = false;
    $("#chat-drawer").hidden = true;
    if (store.chat.abort) {
      store.chat.abort.abort();
      store.chat.abort = null;
    }
    store.chat.streaming = false;
  }

  function renderChatSuggestions() {
    var wrap = $("#chat-suggestions");
    if (store.chat.streaming) {
      wrap.innerHTML = "";
      return;
    }
    wrap.innerHTML = chatSuggestionChips()
      .map(function (s) {
        return '<button type="button" class="sug-chip">' + escapeHtml(s) + "</button>";
      })
      .join("");
    $all(".sug-chip", wrap).forEach(function (chip) {
      chip.addEventListener("click", function () {
        $("#chat-input").value = chip.textContent;
        sendChat();
      });
    });
  }

  function renderChatMessages() {
    var box = $("#chat-messages");
    box.innerHTML = store.chat.messages
      .map(function (m) {
        if (m.role === "user") {
          return (
            '<div class="msg-row me"><div class="msg-avatar">我</div>' +
            '<div class="msg-bubble">' + escapeHtml(m.content) + "</div></div>"
          );
        }
        if (m.role === "error") {
          return (
            '<div class="msg-row err"><div class="msg-avatar"><svg class="icon"><use href="#i-alert-circle"/></svg></div>' +
            '<div class="msg-bubble">' + escapeHtml(m.content) + "</div></div>"
          );
        }
        return (
          '<div class="msg-row bot"><div class="msg-avatar"><svg class="icon"><use href="#i-sparkle"/></svg></div>' +
          '<div class="msg-bubble">' + renderMarkdown(m.content) + "</div></div>"
        );
      })
      .join("");
    box.scrollTop = box.scrollHeight;
  }

  function sendChat() {
    var input = $("#chat-input");
    var text = input.value.trim();
    if (!text || store.chat.streaming) return;
    input.value = "";

    store.chat.messages.push({ role: "user", content: text });
    renderChatMessages();
    renderChatSuggestions();

    // 占位：工具进度条 + 流式气泡
    var box = $("#chat-messages");
    var liveRow = document.createElement("div");
    liveRow.className = "msg-row bot";
    liveRow.innerHTML =
      '<div class="msg-avatar"><svg class="icon"><use href="#i-sparkle"/></svg></div>' +
      '<div style="display:grid;gap:8px;justify-items:start">' +
        '<span class="tool-pill" id="chat-tool"><span class="dot"></span><span>正在思考…</span></span>' +
        '<div class="msg-bubble stream-caret" id="chat-live"></div>' +
      '</div>';
    box.appendChild(liveRow);
    box.scrollTop = box.scrollHeight;

    store.chat.streaming = true;
    var sendBtn = $("#chat-send");
    sendBtn.disabled = true;
    store.chat.abort = new AbortController();

    var acc = "";
    var done = false;
    var history = store.chat.messages
      .filter(function (m) { return m.role === "user" || m.role === "assistant"; })
      .slice(1) // 去掉开场白
      .slice(0, -1) // 去掉刚发出的这条
      .slice(-8)
      .map(function (m) { return { role: m.role, content: m.content }; });

    function finish(errText) {
      if (done) return; // 防止 error 事件与流结束双重收尾
      done = true;
      store.chat.streaming = false;
      sendBtn.disabled = false;
      store.chat.abort = null;
      var finalText = errText || acc || "抱歉，这次没有生成回复，请换个说法再试试。";
      if (errText) {
        store.chat.messages.push({ role: "error", content: errText });
      } else {
        store.chat.messages.push({ role: "assistant", content: finalText });
      }
      renderChatMessages();
      renderChatSuggestions();
    }

    function onEvent(ev) {
      var toolPill = $("#chat-tool");
      var live = $("#chat-live");
      if (ev.type === "tool_start" && toolPill) {
        $("span:last-child", toolPill).textContent = "正在调用工具：" + (ev.name || "");
      } else if (ev.type === "token" && live) {
        acc += ev.content || "";
        live.innerHTML = renderMarkdown(acc);
        box.scrollTop = box.scrollHeight;
      } else if (ev.type === "final") {
        acc = ev.content || acc;
      } else if (ev.type === "error") {
        finish((ev.message || "流式响应中断") + "，请重试。");
      }
    }

    Api.streamChat(text, history, onEvent, store.chat.abort.signal).then(
      function () {
        finish(null);
      },
      function (err) {
        if (err && err.kind === "aborted") {
          if (acc) finish(null);
          return;
        }
        var msg = err && err.message ? err.message : "连接失败，请稍后重试。";
        if (err && err.kind === "network") msg = "网络连接失败，请确认服务已启动。";
        finish(msg);
      }
    );
  }

  /* ============================================================
   * 模型接入展示（多厂商，GET /config/llm，密钥脱敏）
   * ============================================================ */

  var PROVIDER_LABELS = {
    zhipuai: "智谱 AI",
    deepseek: "DeepSeek",
    qwen: "通义千问",
    moonshot: "Kimi（月之暗面）",
    openai: "OpenAI",
    ollama: "Ollama（本地）",
    custom: "自建服务",
  };

  function renderLlmConfig(cfg) {
    var label = PROVIDER_LABELS[cfg.provider] || cfg.provider;
    var badgeText = $("#model-badge-text");
    if (badgeText) badgeText.textContent = label + " · " + cfg.model;
    var footer = $("#footer-model");
    if (footer) footer.textContent = label + " " + cfg.model;
    var providerEl = $("#llm-provider");
    if (providerEl) providerEl.textContent = label + "（" + cfg.provider + "）";
    var modelEl = $("#llm-model");
    if (modelEl) modelEl.textContent = cfg.model;
    var urlEl = $("#llm-base-url");
    if (urlEl) urlEl.textContent = cfg.base_url || "—";
    var keyEl = $("#llm-key");
    if (keyEl) keyEl.textContent = cfg.api_key;

    var list = $("#llm-preset-list");
    if (list) {
      list.innerHTML = "";
      Object.keys(cfg.presets || {}).forEach(function (name) {
        var p = cfg.presets[name];
        var chip = document.createElement("span");
        chip.className = "llm-chip" + (name === cfg.provider ? " llm-chip-active" : "");
        chip.textContent =
          (PROVIDER_LABELS[name] || name) + (p.default_model ? " · " + p.default_model : "");
        chip.title = p.base_url || "自建 OpenAI 兼容端点";
        list.appendChild(chip);
      });
    }
  }

  function loadLlmConfig() {
    Api.fetchLlmConfig()
      .then(function (resp) {
        if (resp && resp.status === "ok") renderLlmConfig(resp.data);
      })
      .catch(function () {
        // 配置接口不可用（如服务未升级）时静默降级，不打断页面
        var badgeText = $("#model-badge-text");
        if (badgeText) badgeText.textContent = "模型配置不可用";
      });
  }

  /* ============================================================
   * 连接设置弹层
   * ============================================================ */

  function openSettings() {
    $("#settings-base").value = Api.getBase();
    $("#settings-token").value = Api.getToken();
    loadLlmConfig();
    $("#settings-overlay").hidden = false;
    setTimeout(function () {
      $("#settings-base").focus();
    }, 60);
  }
  function closeSettings() {
    $("#settings-overlay").hidden = true;
  }

  /* ============================================================
   * 全局绑定与启动
   * ============================================================ */

  function bindGlobal() {
    $("#chat-fab").addEventListener("click", function () {
      if (store.chat.open) closeChat();
      else openChat();
    });
    $("#chat-close").addEventListener("click", closeChat);
    $("#chat-form").addEventListener("submit", function (e) {
      e.preventDefault();
      sendChat();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if (store.chat.open) closeChat();
        if (!$("#settings-overlay").hidden) closeSettings();
      }
    });

    $("#settings-btn").addEventListener("click", openSettings);
    $("#settings-close").addEventListener("click", closeSettings);
    $("#settings-overlay").addEventListener("click", function (e) {
      if (e.target === $("#settings-overlay")) closeSettings();
    });
    $("#settings-save").addEventListener("click", function () {
      Api.setBase($("#settings-base").value.trim());
      Api.setToken($("#settings-token").value.trim());
      closeSettings();
      toast("连接设置已保存", "ok");
    });

    window.addEventListener("hashchange", router);
  }

  function init() {
    var badge = $("#mock-badge");
    if (global.__TA_MOCK__ && badge) badge.hidden = false;
    bindGlobal();
    router();
    loadLlmConfig();
  }

  init();
})(window);
