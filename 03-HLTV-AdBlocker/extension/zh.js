/*
 * HLTV-AdBlocker · 中文化辅助（优化版 v1.2.0）
 *
 * 只做三件事：
 *   1. 给 HLTV 新闻标题加一条灰色小字参考翻译
 *   2. 给新闻/比赛评论加一条灰色小字参考翻译
 *   3. 给常见战队、选手补灰色中文别称
 *
 * 翻译走 MyMemory 的公开接口，只发送需要翻译的标题/评论文本。
 *
 * 与原版相比只改了实现：
 *   - 38 个名字的正则只编译一次（原版每个文本节点都要重编译一遍 + 排序两次）；
 *   - 同一个文本的并发翻译请求合并成一次；
 *   - MyMemory 日额度用完后自动停手，不再反复请求；
 *   - 自己插入节点时先断开/跳过观察器，避免自己触发自己再扫一遍。
 */
(function () {
    "use strict";

    if (window.__hltvZhLoaded) {
        return;
    }
    window.__hltvZhLoaded = true;

    var DEBUG = false;
    function log() {
        if (!DEBUG) {
            return;
        }
        try {
            console.debug.apply(console, ["[hltv-zh]"].concat(Array.prototype.slice.call(arguments)));
        } catch (e) {
            // ignore
        }
    }

    var TEAM_NICKS = {
        "Vitality": "小蜜蜂",
        "Spirit": "绿龙",
        "Falcons": "猎鹰",
        "FaZe": "银河战舰",
        "Lynn Vision": "LVG",
        "BETBOOM": "BB",
        "BetBoom": "BB",
        "BetBoom Team": "BB",
        "Astralis": "A队",
        "FURIA": "黑豹",
        "MOUZ": "老鼠",
        "TYLOO": "天禄",
        "Liquid": "液体"
    };

    var PLAYER_NICKS = {
        "teses": "龙哥",
        "karrigan": "大表哥",
        "magixx": "马西西",
        "zont1x": "宗主",
        "z4kr": "三叶",
        "c4llm3su3": "三叶",
        "kyousuke": "京介",
        "sunpayus": "太阳神",
        "chopper": "大超",
        "s1mple": "森破",
        "m0nesy": "小孩",
        "niko": "尼公子",
        "twistzz": "总监",
        "yekindar": "狂哥",
        "cadian": "点子哥",
        "dev1ce": "阿汤哥",
        "dupreeh": "阿杜",
        "magisk": "魔男",
        "xyp9x": "九爷",
        "apex": "豆豆",
        "zywoo": "载物",
        "rain": "雨神",
        "elige": "鸡哥",
        "coldzera": "冷神",
        "fallen": "教父",
        "hunter-": "表哥",
        "olofmeister": "奥拉夫"
    };

    // 这些词是 CS 圈术语、赛事名或无需翻译的队名，机翻前先换成占位符，翻完再还原。
    var KEEP_TERMS = [
        ["Lynn Vision", "LVG"],
        ["BetBoom Team", "BB"],
        ["BETBOOM", "BB"],
        ["BetBoom", "BB"],
        ["Wildcard", "Wildcard"],
        ["Major", "Major"],
        ["device", "device"],
        ["FUT", "FUT"],
        ["MIBR", "MIBR"],
        ["IEM", "IEM"],
        ["ESL", "ESL"],
        ["BLAST", "BLAST"],
        ["PGL", "PGL"],
        ["HLTV", "HLTV"],
        ["CS2", "CS2"],
        ["CS:GO", "CS:GO"],
        ["MVP", "MVP"],
        ["EVP", "EVP"],
        ["Top 20", "Top 20"],
        ["VRS", "VRS"],
        ["LAN", "LAN"],
        ["Rating", "Rating"],
        ["KAST", "KAST"],
        ["ADR", "ADR"],
        ["Bo3", "Bo3"],
        ["Stage 1", "Stage 1"],
        ["Stage 2", "Stage 2"],
        ["Stage 3", "Stage 3"],
        ["Stage 4", "Stage 4"]
    ];

    var STYLE_CLASS = "hltv-zh-translation";
    var NICK_CLASS = "hltv-zh-nick";
    var CACHE_KEY = "hltv_zh_cache_v2";
    var API = "https://api.mymemory.translated.net/get";
    // 选填：填上自己的邮箱，MyMemory 的匿名额度会从 5000 字符/天 提到 50000 字符/天
    var API_EMAIL = "";

    // 这些区域不加别称/翻译（新闻链接、评论区自己会走翻译流程）
    var TEXT_SKIP = [
        ".hltv-zh-translation",
        ".forum-middle",
        ".thread-message-text",
        ".comment-body",
        ".comment-content",
        ".comment-text",
        ".comment-message",
        "script",
        "style",
        "textarea",
        "input",
        "option",
        "select",
        "button",
        'a[href*="/news/"]',
        ".newstext"
    ].join(",");

    var queue = [];
    var running = 0;
    var scanTimer = 0;
    var cache = {};
    var inflight = Object.create(null);
    var quotaExhausted = false;
    var writing = false;

    try {
        cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}") || {};
    } catch (e) {
        cache = {};
    }

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    // 把一张“名字 -> 别称”表编译成一条正则，只做一次；替代原版每个节点重编译 38 条正则
    function buildNameMatcher(table, caseInsensitive) {
        var keys = Object.keys(table).sort(function (a, b) {
            return b.length - a.length;
        });
        var map = Object.create(null);
        keys.forEach(function (key) {
            map[caseInsensitive ? key.toLowerCase() : key] = table[key];
        });
        var body = "(^|[^A-Za-z0-9_])(?:" + keys.map(escapeRegExp).join("|") + ")(?=[^A-Za-z0-9_]|$)";
        return {
            re: new RegExp(body, caseInsensitive ? "gi" : "g"),
            findRe: new RegExp(body, caseInsensitive ? "i" : ""),
            map: map,
            ci: !!caseInsensitive
        };
    }

    var TEAM_MATCHER = buildNameMatcher(TEAM_NICKS, false);
    var PLAYER_MATCHER = buildNameMatcher(PLAYER_NICKS, true);

    var KEEP_RE = (function () {
        var keys = KEEP_TERMS.map(function (entry) {
            return entry[0];
        }).sort(function (a, b) {
            return b.length - a.length;
        });
        return new RegExp(
            "(^|[^A-Za-z0-9_])(?:" + keys.map(escapeRegExp).join("|") + ")(?=[^A-Za-z0-9_]|$)",
            "g"
        );
    })();

    var KEEP_MAP = (function () {
        var map = Object.create(null);
        KEEP_TERMS.forEach(function (entry) {
            map[entry[0]] = entry[1];
        });
        return map;
    })();

    function matcherNickname(text, matcher) {
        var match = matcher.findRe.exec(text);
        if (!match) {
            return "";
        }
        var name = match[0].slice(match[1].length);
        return matcher.map[matcher.ci ? name.toLowerCase() : name] || "";
    }

    function applyNameMatcher(text, matcher) {
        return text.replace(matcher.re, function (match, prefix) {
            var name = match.slice(prefix.length);
            var nick = matcher.map[matcher.ci ? name.toLowerCase() : name];
            return nick ? prefix + nick : match;
        });
    }

    function isChinese(text) {
        var han = (text.match(/[\u4e00-\u9fff]/g) || []).length;
        return han > Math.max(2, text.length * 0.12);
    }

    function localizeNames(text) {
        return applyNameMatcher(applyNameMatcher(text, TEAM_MATCHER), PLAYER_MATCHER);
    }

    function protectTerms(text) {
        var values = [];
        var out = text.replace(KEEP_RE, function (match, prefix) {
            var term = match.slice(prefix.length);
            var token = "ZXQTERM" + values.length + "QXZ";
            values.push([token, KEEP_MAP[term]]);
            return prefix + token;
        });
        return { text: out, values: values };
    }

    function restoreTerms(text, values) {
        values.forEach(function (entry) {
            text = text.split(entry[0]).join(entry[1]);
        });
        return text;
    }

    function cleanTranslatedText(text) {
        text = localizeNames(text);
        // 占位符没被 API 保留时的兜底；必须先处理“外卡...”再统一“战队”
        text = text.replace(/外卡战队|外卡球队|外卡队|外卡/g, "Wildcard");
        text = text.replace(/少校|特锦赛/g, "Major");
        text = text.replace(/林恩视觉|林恩视野/g, "LVG");
        text = text.replace(/贝特布姆/gi, "BB");
        // 阶段名统一下来，避免“第一阶段”和“第2阶段”混用
        text = text.replace(/第\s*1\s*阶段|第一阶段/g, "Stage 1");
        text = text.replace(/第\s*2\s*阶段|第二阶段/g, "Stage 2");
        text = text.replace(/第\s*3\s*阶段|第三阶段/g, "Stage 3");
        text = text.replace(/第\s*4\s*阶段|第四阶段/g, "Stage 4");
        // 机翻偶尔会用错战队称呼；CS 圈统一叫战队
        text = text.replace(/球队/g, "战队");
        return text;
    }

    // 常见的 CS 固定句式和术语，机翻很容易把 plant 译成“工厂”、shot 译成“镜头”。
    function translateKnownPhrase(text) {
        if (/^\s*(nice try|nt)[.!]*\s*$/i.test(text)) {
            return "尽力了";
        }
        var match = text.match(/^(.+?)\s+denies the plant with a crucial shot\.?$/i);
        if (match) {
            return match[1].trim() + "用关键一枪阻止了下包";
        }
        match = text.match(/^(.+?)\s+denies the plant\.?$/i);
        if (match) {
            return match[1].trim() + "阻止了下包";
        }
        match = text.match(/^(.+?)\s+defuses the bomb\.?$/i);
        if (match) {
            return match[1].trim() + "拆除了炸弹";
        }
        match = text.match(/^Frustration for (.+?) after (\d+-\d+) exit\.?$/i);
        if (match) {
            return "以" + match[2] + "出局后，" + match[1].trim() + "感到沮丧";
        }
        match = text.match(/^(.+?)\s+qualif(?:y|ies) for (Stage \d+) over (.+?)\.?$/i);
        if (match) {
            return match[1].trim() + "战胜" + match[3].trim() + "，晋级" + match[2];
        }
        match = text.match(/^(.+?)\s+qualif(?:y|ies) for (Stage \d+)\.?$/i);
        if (match) {
            return match[1].trim() + "晋级" + match[2];
        }
        match = text.match(/^(.+?)\s+advance(?:s)? to (Stage \d+)\.?$/i);
        if (match) {
            return match[1].trim() + "晋级" + match[2];
        }
        match = text.match(/^(.+?)\s+eliminate (.+?) from (.+?)\.?$/i);
        if (match) {
            return match[1].trim() + "将" + match[2].trim() + "淘汰出" + match[3].trim();
        }
        match = text.match(/^(.+?)\s+bench(?:es)? (.+?)\.?$/i);
        if (match) {
            return match[1].trim() + "将" + match[2].trim() + "放上替补席";
        }
        match = text.match(/^(.+?)\s+dispatch(?:es)? (.+?) to make (Stage \d+)\.?$/i);
        if (match) {
            return match[1].trim() + "战胜" + match[2].trim() + "，晋级" + match[3];
        }
        match = text.match(/^(.+?)\s+outlast(?:s)? (.+?) to progress to (Stage \d+)\.?$/i);
        if (match) {
            return match[1].trim() + "战胜" + match[2].trim() + "，晋级" + match[3];
        }
        return "";
    }

    function decodeEntities(text) {
        var area = document.createElement("textarea");
        area.innerHTML = text;
        return area.value;
    }

    function splitText(text, maxLength) {
        var rest = text.trim();
        var parts = [];
        while (rest.length > maxLength) {
            var cut = rest.lastIndexOf(". ", maxLength);
            if (cut < maxLength * 0.4) {
                cut = rest.lastIndexOf(" ", maxLength);
            }
            if (cut < maxLength * 0.4) {
                cut = maxLength;
            }
            parts.push(rest.slice(0, cut + 1).trim());
            rest = rest.slice(cut + 1).trim();
        }
        if (rest) {
            parts.push(rest);
        }
        return parts;
    }

    function saveCache() {
        try {
            var keys = Object.keys(cache);
            if (keys.length > 400) {
                keys.slice(0, keys.length - 400).forEach(function (key) {
                    delete cache[key];
                });
            }
            localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
        } catch (e) {
            // ignore
        }
    }

    function delay(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    async function translateText(text) {
        var source = text.trim();
        if (!source || isChinese(source)) {
            return source;
        }
        var key = "t:" + source;
        if (Object.prototype.hasOwnProperty.call(cache, key)) {
            return cache[key];
        }
        if (quotaExhausted) {
            throw new Error("translation quota exhausted");
        }

        var known = translateKnownPhrase(source);
        if (known) {
            var knownResult = cleanTranslatedText(known);
            cache[key] = knownResult;
            saveCache();
            return knownResult;
        }

        var translated = [];
        var protectedText = protectTerms(source);
        var protectedChunks = splitText(protectedText.text, 450);
        for (var i = 0; i < protectedChunks.length; i++) {
            var url = API + "?q=" + encodeURIComponent(protectedChunks[i]) +
                "&langpair=" + encodeURIComponent("en|zh-CN");
            if (API_EMAIL) {
                url += "&de=" + encodeURIComponent(API_EMAIL);
            }
            var response = await fetch(url, {
                method: "GET",
                signal: AbortSignal.timeout(12000),
                credentials: "omit"
            });
            if (!response.ok) {
                throw new Error("translation http " + response.status);
            }
            var payload = await response.json();
            var value = payload && payload.responseData && payload.responseData.translatedText;
            if (!value || /MYMEMORY WARNING|QUERY LENGTH LIMIT|INVALID/i.test(value)) {
                if (/MYMEMORY WARNING/i.test(value || "")) {
                    quotaExhausted = true;
                    log("MyMemory 今日免费额度已用完，本次会话不再请求翻译");
                }
                throw new Error("translation unavailable");
            }
            translated.push(decodeEntities(value));
            if (protectedChunks.length > 1) {
                await delay(120);
            }
        }
        var result = cleanTranslatedText(
            restoreTerms(translated.join(" ").trim(), protectedText.values)
        );
        cache[key] = result;
        saveCache();
        return result;
    }

    function settle(key, value) {
        var waiters = inflight[key] || [];
        delete inflight[key];
        for (var i = 0; i < waiters.length; i++) {
            try {
                waiters[i](value);
            } catch (e) {
                log("translation callback", e);
            }
        }
    }

    function pump() {
        while (running < 2 && queue.length) {
            var job = queue.shift();
            running += 1;
            translateText(job.text).then(function (value) {
                settle(job.key, value || "");
            }).catch(function (error) {
                log("translate failed", error);
                settle(job.key, "");
            }).finally(function () {
                running -= 1;
                pump();
            });
        }
    }

    function enqueue(text, done) {
        var key = "t:" + text.trim();
        if (Object.prototype.hasOwnProperty.call(cache, key)) {
            done(cache[key]);
            return;
        }
        // 同一段英文同时出现在多处时只发一次请求
        if (inflight[key]) {
            inflight[key].push(done);
            return;
        }
        inflight[key] = [done];
        queue.push({ key: key, text: text });
        pump();
    }

    function addTranslationAfter(element, text, prefix) {
        if (!element || !text || element.getAttribute("data-hltv-zh") === "1") {
            return;
        }
        element.setAttribute("data-hltv-zh", "1");
        var line = document.createElement("div");
        line.className = STYLE_CLASS;
        line.textContent = prefix ? "参考翻译：翻译中…" : "翻译中…";
        element.insertAdjacentElement("afterend", line);
        enqueue(text, function (value) {
            if (!value) {
                line.remove();
                return;
            }
            line.textContent = (prefix ? "参考翻译：" : "") + value;
        });
    }

    function scanNews() {
        document.querySelectorAll('a[href*="/news/"]').forEach(function (anchor) {
            if (anchor.getAttribute("data-hltv-zh-news") === "1") {
                return;
            }
            if (anchor.closest("nav, header, footer, .footer")) {
                return;
            }
            var title = anchor.matches(".newstext") ? anchor :
                anchor.querySelector(".newstext, h2, h3, .news-header, .news-title");
            if (!title) {
                return;
            }
            var text = (title.textContent || "").replace(/\s+/g, " ").trim();
            if (text.length < 8 || isChinese(text)) {
                return;
            }
            anchor.setAttribute("data-hltv-zh-news", "1");
            addTranslationAfter(anchor, text, false);
        });
    }

    function scanComments() {
        var selectors = [
            ".forum-middle",
            ".thread-message-text",
            ".comment-body",
            ".comment-content",
            ".comment-text",
            ".comment-message"
        ];
        var seen = new Set();
        selectors.forEach(function (selector) {
            document.querySelectorAll(selector).forEach(function (element) {
                if (seen.has(element) || element.getAttribute("data-hltv-zh-comment") === "1") {
                    return;
                }
                if (element.closest("." + STYLE_CLASS) || element.querySelector(".thread-message-text")) {
                    return;
                }
                var text = (element.textContent || "").trim();
                if (text.length < 8 || isChinese(text)) {
                    return;
                }
                // 登录提示不是评论，不要给它加参考翻译
                if (/Login or register|登录或注册|add your comment to the discussion/i.test(text)) {
                    return;
                }
                seen.add(element);
                element.setAttribute("data-hltv-zh-comment", "1");
                addTranslationAfter(element, text, true);
            });
        });
    }

    function addNick(element, nickname) {
        if (!element || !nickname || element.querySelector("." + NICK_CLASS) ||
            element.closest("." + STYLE_CLASS) || element.closest(".forum-middle") ||
            element.getAttribute("data-hltv-zh-nick") === "1") {
            return;
        }
        element.setAttribute("data-hltv-zh-nick", "1");
        var span = document.createElement("span");
        span.className = NICK_CLASS;
        span.textContent = "（" + nickname + "）";
        element.appendChild(span);
    }

    function decorateNameText() {
        try {
            if (!document.body) {
                return;
            }
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            var node = walker.nextNode();
            while (node) {
                var text = node.nodeValue ? node.nodeValue.trim() : "";
                if (text && text.length <= 80) {
                    var parent = node.parentElement;
                    if (parent && !parent.closest(TEXT_SKIP)) {
                        var nickname = matcherNickname(text, PLAYER_MATCHER) ||
                            matcherNickname(text, TEAM_MATCHER);
                        if (nickname) {
                            addNick(parent, nickname);
                        }
                    }
                }
                node = walker.nextNode();
            }
        } catch (e) {
            log("decorateNameText", e);
        }
    }

    function decorateNames() {
        var players = new Set();
        document.querySelectorAll('.playerNickname, a[href*="/player/"]').forEach(function (el) {
            players.add(el);
        });
        players.forEach(function (el) {
            if (el.querySelector(".playerNickname") && !el.matches(".playerNickname")) {
                return;
            }
            var text = (el.textContent || "").trim();
            if (!text) {
                return;
            }
            addNick(el, matcherNickname(text, PLAYER_MATCHER));
        });

        var teams = new Set();
        document.querySelectorAll('.teamName, .team-name, a[href*="/team/"]').forEach(function (el) {
            teams.add(el);
        });
        teams.forEach(function (el) {
            if ((el.querySelector(".teamName, .team-name")) &&
                !el.matches(".teamName, .team-name")) {
                return;
            }
            var text = (el.textContent || "").trim();
            if (!text) {
                return;
            }
            addNick(el, matcherNickname(text, TEAM_MATCHER));
        });
    }

    function scanInner() {
        decorateNames();
        decorateNameText();
        scanNews();
        scanComments();
    }

    function scan() {
        // 扫描期间自己插入的节点不要反过来触发新一轮扫描
        writing = true;
        try {
            scanInner();
        } finally {
            window.setTimeout(function () {
                writing = false;
            }, 0);
        }
    }

    function scheduleScan() {
        if (scanTimer) {
            return;
        }
        scanTimer = window.setTimeout(function () {
            scanTimer = 0;
            scan();
        }, 500);
    }

    var observer = null;
    function onMutations() {
        if (writing) {
            return;
        }
        scheduleScan();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", scan, { once: true });
    } else {
        scan();
    }

    try {
        observer = new MutationObserver(onMutations);
        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    } catch (e) {
        log("observer", e);
    }
    window.addEventListener("load", scheduleScan, { once: true });

    // 评论/新闻是异步加载的，前 30 秒再兜底扫几次
    var ticks = 0;
    var timer = window.setInterval(function () {
        scan();
        ticks += 1;
        if (ticks >= 15) {
            window.clearInterval(timer);
        }
    }, 2000);
})();
