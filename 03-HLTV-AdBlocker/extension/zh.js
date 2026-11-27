/*
 * HLTV-AdBlocker · 中文化辅助
 *
 * 只做三件事：
 *   1. 给 HLTV 新闻标题加一条灰色小字参考翻译
 *   2. 给新闻/比赛评论加一条灰色小字参考翻译
 *   3. 给常见战队、选手补灰色中文别称
 *
 * 翻译走 MyMemory 的公开接口，只发送需要翻译的标题/评论文本；
 * 不发送浏览历史、账号信息或页面其它内容。
 */
(function () {
    "use strict";

    if (window.__hltvZhLoaded) {
        return;
    }
    window.__hltvZhLoaded = true;

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
        "hunter-": "表哥"
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
        ["Bo3", "Bo3"]
    ];

    var STYLE_CLASS = "hltv-zh-translation";
    var NICK_CLASS = "hltv-zh-nick";
    var CACHE_KEY = "hltv_zh_cache_v1";
    var API = "https://api.mymemory.translated.net/get";
    var queue = [];
    var running = 0;
    var scanTimer = 0;
    var cache = {};

    try {
        cache = JSON.parse(localStorage.getItem(CACHE_KEY) || "{}") || {};
    } catch (e) {
        cache = {};
    }

    function isChinese(text) {
        var han = (text.match(/[\u4e00-\u9fff]/g) || []).length;
        return han > Math.max(2, text.length * 0.12);
    }

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function localizeNames(text) {
        var entries = [];
        Object.keys(TEAM_NICKS).forEach(function (key) {
            entries.push([key, TEAM_NICKS[key], false]);
        });
        Object.keys(PLAYER_NICKS).forEach(function (key) {
            entries.push([key, PLAYER_NICKS[key], true]);
        });
        entries.sort(function (a, b) {
            return b[0].length - a[0].length;
        });
        entries.forEach(function (entry) {
            var re = new RegExp(
                "(^|[^A-Za-z0-9_])(" + escapeRegExp(entry[0]) + ")(?=[^A-Za-z0-9_]|$)",
                entry[2] ? "gi" : "g"
            );
            text = text.replace(re, function (_m, before) {
                return before + entry[1];
            });
        });
        return text;
    }

    function protectTerms(text) {
        var values = [];
        var entries = KEEP_TERMS.slice().sort(function (a, b) {
            return b[0].length - a[0].length;
        });
        entries.forEach(function (entry, index) {
            var token = "ZXQTERM" + index + "QXZ";
            var re = new RegExp(
                "(^|[^A-Za-z0-9_])(" + escapeRegExp(entry[0]) +
                ")(?=[^A-Za-z0-9_]|$)", "g"
            );
            var before = text;
            text = text.replace(re, function (_m, prefix) {
                return prefix + token;
            });
            if (text !== before) {
                values.push([token, entry[1]]);
            }
        });
        return { text: text, values: values };
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
        // 机翻偶尔会用错战队称呼；CS 圈统一叫战队
        text = text.replace(/球队/g, "战队");
        return text;
    }

    // 常见的 CS 固定句式和术语，机翻很容易把 plant 译成“工厂”、shot 译成“镜头”。
    function translateKnownPhrase(text) {
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

    function pump() {
        while (running < 2 && queue.length) {
            var job = queue.shift();
            running += 1;
            translateText(job.text).then(function (value) {
                job.done(value);
            }).catch(function () {
                job.done("");
            }).finally(function () {
                running -= 1;
                pump();
            });
        }
    }

    function enqueue(text, done) {
        var source = text.trim();
        var key = "t:" + source;
        if (Object.prototype.hasOwnProperty.call(cache, key)) {
            done(cache[key]);
            return;
        }
        queue.push({ text: text, done: done });
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
        document.querySelectorAll("a[href*=\"/news/\"]").forEach(function (anchor) {
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
                var text = (element.innerText || "").trim();
                if (text.length < 8 || isChinese(text)) {
                    return;
                }
                seen.add(element);
                element.setAttribute("data-hltv-zh-comment", "1");
                addTranslationAfter(element, text, true);
            });
        });
    }

    function findNickname(text, table, lowerCaseKeys) {
        var probe = lowerCaseKeys ? text.toLowerCase() : text;
        var keys = Object.keys(table).sort(function (a, b) {
            return b.length - a.length;
        });
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            var needle = lowerCaseKeys ? key.toLowerCase() : key;
            var re = new RegExp("(^|[^A-Za-z0-9_])" + escapeRegExp(needle) +
                "(?=[^A-Za-z0-9_]|$)", lowerCaseKeys ? "i" : "");
            if (re.test(probe)) {
                return table[key];
            }
        }
        return "";
    }

    function addNick(element, nickname) {
        if (!element || !nickname || element.querySelector("." + NICK_CLASS) ||
            element.closest("." + STYLE_CLASS) || element.getAttribute("data-hltv-zh-nick") === "1") {
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
                var text = (node.nodeValue || "").trim();
                if (text.length > 0 && text.length <= 80) {
                    var parent = node.parentElement;
                    if (parent &&
                        !parent.closest("." + STYLE_CLASS) &&
                        !parent.closest(".thread-message-text, .comment-body, .comment-content, .comment-text, .comment-message") &&
                        !parent.closest("a[href*=\"/news/\"], .newstext") &&
                        !parent.closest("script, style, textarea, input, option")) {
                        var nickname = findNickname(text, PLAYER_NICKS, true) ||
                            findNickname(text, TEAM_NICKS, false);
                        if (nickname) {
                            addNick(parent, nickname);
                        }
                    }
                }
                node = walker.nextNode();
            }
        } catch (e) {
            // ignore
        }
    }

    function decorateNames() {
        var players = new Set();
        document.querySelectorAll(".playerNickname, a[href*=\"/player/\"]").forEach(function (el) {
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
            addNick(el, findNickname(text, PLAYER_NICKS, true));
        });

        var teams = new Set();
        document.querySelectorAll(".teamName, .team-name, a[href*=\"/team/\"]").forEach(function (el) {
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
            addNick(el, findNickname(text, TEAM_NICKS, false));
        });
    }

    function scan() {
        decorateNames();
        decorateNameText();
        scanNews();
        scanComments();
    }

    function scheduleScan() {
        if (scanTimer) {
            return;
        }
        scanTimer = window.setTimeout(function () {
            scanTimer = 0;
            scan();
        }, 350);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", scheduleScan, { once: true });
        document.addEventListener("DOMContentLoaded", function () {
            scan();
        }, { once: true });
    } else {
        scan();
    }

    try {
        new MutationObserver(scheduleScan).observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    } catch (e) {
        // ignore
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
