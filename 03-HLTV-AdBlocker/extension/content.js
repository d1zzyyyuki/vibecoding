/*
 * HLTV-AdBlocker · 反立即捡钱插件 —— 内容脚本（优化版 v1.2.0）
 *
 * 行为与原版一致，改的是执行方式：
 *   1. 70 多条选择器合并成一个字符串，每次只调一次 querySelectorAll；
 *   2. MutationObserver 只在“新增节点”上做增量清理，不再每个 DOM 变化都全文档扫一遍；
 *   3. 文本/浮层启发式扫描降频，先用 textContent 做廉价预筛，再取 computedStyle；
 *   4. 跳过 zh.js 注入的“参考翻译”节点，避免把“领取/首充”这类中文误判成广告；
 *   5. 水印只加在顶层框架，iframe 里不再重复出现。
 *
 * 赔率区域（.betting / .odds / .match-bet / .bookmaker / table）仍然是保护区域。
 */
(function () {
    "use strict";

    if (window.__hltvAdBlockerLoaded) {
        return;
    }
    window.__hltvAdBlockerLoaded = true;

    var DEBUG = false;
    function log() {
        if (!DEBUG) {
            return;
        }
        try {
            console.debug.apply(console, ["[hltv-adb]"].concat(Array.prototype.slice.call(arguments)));
        } catch (e) {
            // ignore
        }
    }

    var isTopFrame = true;
    try {
        isTopFrame = window.top === window;
    } catch (e) {
        isTopFrame = false;
    }

    // ---------------------------------------------------------------- 选择器
    // CSS 里已经有一份静态规则；这里负责 CSS 来不及覆盖的动态节点。
    var AD_SELECTORS = [
        ".bg-sidebar.right.wide",
        ".bg-sidebar.gtSmartphone-only",
        ".bg-enabler-child.left",
        ".bg-enabler-child.right",
        ".small-logo",
        "#i1_top",
        "#i1_middle",
        "#i4_bottom",
        "#i0_forum",
        "#matchpage_1",
        ".presented-by",
        ".thunderpick-firstcol-box",
        ".ggbe-firstcol-box",
        ".xbet-widget",
        ".xbet-fourth",
        ".ggking-new",
        ".ggking-banner",
        ".etbx-fourth",
        ".buff-b",
        ".cyberbe",
        ".bitskins-col-box",
        ".vertical-box",
        ".player-of-the-week-box",
        ".featured-match-widget-container",
        ".betting-widget",
        ".betway-widget",
        ".video-ad",
        ".player-ad",
        ".ad-overlay",
        ".video-ad-overlay",
        '[class*="video-ad" i]',
        '[id*="video-ad" i]',
        '[class*="player-ad" i]',
        '[class*="ad-overlay" i]',
        '[id*="ad-overlay" i]',
        '[class*="overlay-ad" i]',
        '[class*="floating-ad" i]',
        '[class*="sticky-ad" i]',
        '[class*="ad-float" i]',
        '[class*="float-ad" i]',
        '[class*="popup-ad" i]',
        '[class*="ad-popup" i]',
        '[class*="betway" i]',
        '[class*="betting-widget" i]',
        '[class*="widget-ad" i]',
        '[class*="ad-widget" i]',
        '[class*="advert" i]',
        '[id*="gpt-ad" i]',
        '[id^="div-gpt-ad" i]',
        "[data-google-query-id]",
        "ins.adsbygoogle",
        ".adsbygoogle",
        '[data-link-tracking-page="Widget"]',
        'iframe[id^="google_ads_iframe_"]',
        'div[data-id-prefix^="aditude-placement-"]',
        '[class^="ad-"]',
        '[class*=" ad-"]',
        '[class$="-ad"]',
        '[id^="ad-"]',
        '[id$="-ad"]',
        "[data-ad]",
        "[data-ad-slot]",
        ".ad",
        ".ads",
        ".advert",
        ".advertisement",
        ".ad-container",
        ".ad-slot",
        ".banner-ad",
        ".sponsored",
        ".sponsor-box",
        ".promo-banner",
        'img[src*="/retina/nextlevel/"]',
        'img[src*="/retina2/"]',
        'img[src*="/retina/farmskins/"]',
        'img[src*="/retina/ggbet/"]',
        'img[src*="/retina/egb/"]',
        'img[src*="/retina/kinguin/"]',
        'img[src*="skinwalletnews.jpg"]'
    ].join(",");

    var PROTECTED = [
        ".betting",
        "#betting",
        ".odds",
        ".odds-table",
        ".match-bet",
        ".bookmaker",
        ".betting-table",
        "table"
    ].join(",");

    // 这些区域里的文字即使命中 AD_TEXT_RE 也不判成广告（评论、正文、翻译节点）
    var TEXT_SKIP = [
        ".hltv-zh-translation",
        "[data-hltv-zh]",
        "[data-hl-ad]",
        ".forum-middle",
        ".thread-message-text",
        ".comment-body",
        ".comment-content",
        ".comment-text",
        ".comment-message",
        ".newstext",
        "article",
        "main",
        ".contentCol",
        ".leftCol",
        ".rightCol",
        "nav",
        "header",
        "footer",
        "script",
        "style",
        "noscript",
        "textarea",
        "select",
        "option",
        "button"
    ].join(",");

    // 向上找广告容器时，遇到这些结构就停手
    // .logoCon 必须停：否则 cleanAdLinks 从顶栏的 /out2/ 广告链接往上爬，会把整条 logo 栏一起隐藏
    var CLIMB_STOP = [
        "main",
        "article",
        ".logoCon",
        ".match-page",
        ".contentCol",
        ".leftCol",
        ".rightCol",
        "#match",
        ".forum-middle",
        ".thread-message-text",
        ".comment-body",
        ".comment-content",
        ".comment-text",
        ".comment-message"
    ].join(",");

    var AD_IFRAME_RE = /(doubleclick|googlesyndication|adservice\.google|uuidksinc|rtmark|vntsm|popads|propellerads|adsterra|hilltopads|onclickads|exoclick)/i;
    var AD_TEXT_RE = /(立即捡钱|立即前往|注册即送|注册领|注册送|领取|首存|首充|充值|雷火电竞|熊猫体育|开云体育|九游娱乐|betway|1xbet|n3b\.cc|leihuo58|181ty|kaiyun|电竞平台|体育平台)/i;

    var PASS_DEBOUNCE_MS = 300;   // DOM 变化后合并执行的防抖
    var TICK_MS = 1500;           // 兜底扫描间隔
    var TICK_LIMIT = 40;          // 兜底扫描只跑前 60 秒，之后靠 DOM 变化兜底

    // ---------------------------------------------------------------- 工具
    function isProtected(el) {
        try {
            return !!(el && el.closest && el.closest(PROTECTED));
        } catch (e) {
            return false;
        }
    }

    function isInTextSkip(el) {
        try {
            return !!(el && el.closest && el.closest(TEXT_SKIP));
        } catch (e) {
            return false;
        }
    }

    function hide(el) {
        if (!el || el.nodeType !== 1 || isProtected(el)) {
            return;
        }
        if (el.getAttribute("data-hl-ad") === "1") {
            return;
        }
        el.setAttribute("data-hl-ad", "1");
        el.style.setProperty("display", "none", "important");
    }

    function hideAdContainer(el) {
        if (!el || el.nodeType !== 1 || isProtected(el) || el.closest("[data-hl-ad]")) {
            return;
        }
        var node = el;
        for (var depth = 0; depth < 4; depth++) {
            var parent = node.parentElement;
            if (!parent || parent === document.body || parent === document.documentElement) {
                break;
            }
            if (isProtected(parent) || parent.querySelector("table") || parent.matches(CLIMB_STOP)) {
                break;
            }
            var label = "";
            try {
                label = String(parent.id || "") + " " +
                    (typeof parent.className === "string" ? parent.className : "");
            } catch (e) {
                label = "";
            }
            if (/(^|[\s_-])(ad|ads|advert|banner|widget|sponsor|promo|betting)([\s_-]|$)/i.test(label)) {
                hide(parent);
                return;
            }
            var text = "";
            try {
                text = (parent.textContent || "").trim();
            } catch (e) {
                text = "";
            }
            try {
                if (text.length > 260 || parent.querySelectorAll("a").length > 5) {
                    break;
                }
            } catch (e) {
                // ignore
            }
            node = parent;
        }
        hide(node);
    }

    function cleanAdLinks(scope) {
        try {
            scope.querySelectorAll('a[href*="/out2/"]').forEach(function (a) {
                if (isProtected(a)) {
                    return;
                }
                if (a.querySelector("img") || a.textContent.trim()) {
                    hideAdContainer(a);
                }
            });
        } catch (e) {
            log("cleanAdLinks", e);
        }
    }

    function cleanLogoBox(box) {
        if (!box || isProtected(box)) {
            return;
        }
        var kids = Array.prototype.slice.call(box.children);
        for (var i = 1; i < kids.length; i++) {
            var child = kids[i];
            var looksLikeAd = false;
            try {
                // 原版这里还有 img[src*="ad"]，会把 broadcast/loading/header 之类路径也算进来，已去掉
                looksLikeAd = !!(child.matches('a[href^="/out2/"], img[src*="/retina/"]') ||
                    child.querySelector('a[href^="/out2/"], img[src*="/retina/"]'));
            } catch (e) {
                looksLikeAd = false;
            }
            if (looksLikeAd) {
                // 用 hide 代替 remove：不破坏站点自己引用着的 DOM 节点
                hide(child);
            }
        }
    }

    function cleanLogoCon(scope) {
        try {
            if (scope.querySelectorAll) {
                scope.querySelectorAll(".logoCon").forEach(cleanLogoBox);
            }
            if (scope.nodeType === 1 && scope.matches(".logoCon")) {
                cleanLogoBox(scope);
            }
        } catch (e) {
            log("cleanLogoCon", e);
        }
    }

    function cleanAdText(scope) {
        try {
            var root = scope === document ? document.body : scope;
            if (!root || !root.querySelectorAll) {
                return;
            }
            var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
            var node = walker.nextNode();
            while (node) {
                var raw = node.nodeValue;
                if (raw && raw.length < 100) {
                    var text = raw.trim();
                    if (text && AD_TEXT_RE.test(text)) {
                        var parent = node.parentElement;
                        if (parent && !isInTextSkip(parent)) {
                            hideAdContainer(parent);
                        }
                    }
                }
                node = walker.nextNode();
            }
            root.querySelectorAll("img[alt], img[src]").forEach(function (img) {
                var label = (img.getAttribute("alt") || "") + " " + (img.getAttribute("src") || "");
                if (AD_TEXT_RE.test(label) && !img.closest("[data-hl-ad]") && !isInTextSkip(img)) {
                    hideAdContainer(img);
                }
            });
        } catch (e) {
            log("cleanAdText", e);
        }
    }

    function cleanFloatingAds(scope) {
        try {
            var root = scope === document ? document.body : scope;
            if (!root || !root.querySelectorAll) {
                return;
            }
            var nodes = root.querySelectorAll("div, section, aside, span");
            for (var i = 0; i < nodes.length; i++) {
                var el = nodes[i];
                if (el.getAttribute("data-hl-ad") === "1" || isProtected(el) ||
                    el.closest("[data-hl-ad]") || isInTextSkip(el)) {
                    continue;
                }
                if (el.childElementCount > 24) {
                    continue;
                }
                var text = el.textContent || "";
                if (!text || text.length > 180) {
                    continue;
                }
                if (!AD_TEXT_RE.test(text)) {
                    continue;
                }
                var style = window.getComputedStyle(el);
                var position = style.position;
                var zIndex = parseInt(style.zIndex, 10) || 0;
                if (position !== "fixed" && position !== "absolute" && zIndex < 10) {
                    continue;
                }
                var box = el;
                for (var depth = 0; depth < 3; depth++) {
                    var parent = box.parentElement;
                    if (!parent || parent === document.body || isProtected(parent) || isInTextSkip(parent)) {
                        break;
                    }
                    var pstyle = window.getComputedStyle(parent);
                    var pz = parseInt(pstyle.zIndex, 10) || 0;
                    if ((pstyle.position === "fixed" || pstyle.position === "absolute") && pz >= zIndex) {
                        box = parent;
                    } else {
                        break;
                    }
                }
                hide(box);
            }
        } catch (e) {
            log("cleanFloatingAds", e);
        }
    }

    function cleanBodyBackground() {
        var body = document.body;
        if (!body) {
            return;
        }
        if (body.hasAttribute("data-href")) {
            body.removeAttribute("data-href");
        }
        if (body.getAttribute("data-hl-bg") === "1") {
            return;
        }
        var bg = "";
        try {
            bg = window.getComputedStyle(body).backgroundImage || "";
        } catch (e) {
            bg = "";
        }
        if (bg && bg !== "none" && bg.indexOf("url(") !== -1) {
            body.setAttribute("data-hl-bg", "1");
            body.style.setProperty("background-image", "none", "important");
        }
    }

    // ---------------------------------------------------------------- 扫描入口
    function scanSubtree(node) {
        try {
            if (node.matches(AD_SELECTORS)) {
                hide(node);
            }
            node.querySelectorAll(AD_SELECTORS).forEach(hide);
        } catch (e) {
            log("scanSubtree selectors", e);
        }
        try {
            if (node.matches("iframe[src]") && AD_IFRAME_RE.test(node.src || "")) {
                hide(node);
            }
            node.querySelectorAll("iframe[src]").forEach(function (frame) {
                if (AD_IFRAME_RE.test(frame.src || "")) {
                    hide(frame);
                }
            });
        } catch (e) {
            log("scanSubtree iframes", e);
        }
        cleanAdLinks(node);
        cleanLogoCon(node);
    }

    function cleanAll() {
        try {
            document.querySelectorAll(AD_SELECTORS).forEach(hide);
        } catch (e) {
            log("cleanAll selectors", e);
        }
        try {
            document.querySelectorAll("iframe[src]").forEach(function (frame) {
                if (AD_IFRAME_RE.test(frame.src || "")) {
                    hide(frame);
                }
            });
        } catch (e) {
            log("cleanAll iframes", e);
        }
        cleanAdLinks(document);
        cleanLogoCon(document);
        cleanAdText(document);
        cleanFloatingAds(document);
        cleanBodyBackground();
    }

    function addWatermark() {
        if (!isTopFrame || !document.body || document.getElementById("hltv-adblocker-watermark")) {
            return;
        }
        var mark = document.createElement("div");
        mark.id = "hltv-adblocker-watermark";
        mark.textContent = "by cbd";
        mark.setAttribute("aria-hidden", "true");
        document.body.appendChild(mark);
    }

    var passTimer = 0;
    function schedulePass() {
        if (passTimer) {
            return;
        }
        passTimer = window.setTimeout(function () {
            passTimer = 0;
            cleanAdText(document);
            cleanFloatingAds(document);
            cleanBodyBackground();
        }, PASS_DEBOUNCE_MS);
    }

    function onMutations(records) {
        var added = [];
        for (var i = 0; i < records.length; i++) {
            var record = records[i];
            if (!record.addedNodes || !record.addedNodes.length) {
                continue;
            }
            for (var j = 0; j < record.addedNodes.length; j++) {
                var node = record.addedNodes[j];
                if (node.nodeType === 1) {
                    added.push(node);
                }
            }
        }
        if (!added.length) {
            return;
        }
        // 一次性插进来一大片时，整页扫一遍比逐个子树扫更划算
        if (added.length > 80) {
            cleanAll();
            return;
        }
        for (var k = 0; k < added.length; k++) {
            scanSubtree(added[k]);
        }
        schedulePass();
    }

    function start() {
        cleanAll();
        try {
            if (window.MutationObserver && document.documentElement) {
                new MutationObserver(onMutations).observe(document.documentElement, {
                    childList: true,
                    subtree: true
                });
            }
        } catch (e) {
            log("observer", e);
        }

        // 首屏之后再补扫几次，覆盖“DOMContentLoaded 之后才注入”的广告
        [600, 2000, 5000, 12000].forEach(function (ms) {
            window.setTimeout(cleanAll, ms);
        });

        var ticks = 0;
        var timer = window.setInterval(function () {
            ticks += 1;
            cleanBodyBackground();
            if (ticks % 2 === 0) {
                cleanAdText(document);
                cleanFloatingAds(document);
            }
            if (ticks >= TICK_LIMIT) {
                window.clearInterval(timer);
            }
        }, TICK_MS);

        ["play", "playing", "pause", "loadedmetadata", "seeked"].forEach(function (eventName) {
            document.addEventListener(eventName, schedulePass, true);
        });

        window.addEventListener("load", cleanAll, { once: true });
    }

    // document_start 时先用 CSS 兜底，JS 能清多少清多少；body 就绪后再挂观察器
    if (document.readyState === "loading") {
        cleanAll();
        document.addEventListener("DOMContentLoaded", function () {
            addWatermark();
            start();
        }, { once: true });
    } else {
        addWatermark();
        start();
    }
})();
