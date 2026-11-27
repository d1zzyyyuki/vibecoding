/*
 * HLTV-AdBlocker · 反立即捡钱插件
 *
 * 这个脚本只做两件事：
 *   1. 清掉 CSS 之后仍会动态插入的广告节点/背景广告；
 *   2. 清掉顶栏 logoCon 里夹带的赞助广告。
 *
 * 注意：.betting / .odds / .match-bet / .bookmaker 等赔率区域是保护区域，
 * 这里所有隐藏操作都会跳过它们，避免把 HLTV 的比赛赔率一起干掉。
 */
(function () {
    "use strict";

    if (window.__hltvAdBlockerLoaded) {
        return;
    }
    window.__hltvAdBlockerLoaded = true;

    function addWatermark() {
        if (!document.body || document.getElementById("hltv-adblocker-watermark")) {
            return;
        }
        var mark = document.createElement("div");
        mark.id = "hltv-adblocker-watermark";
        mark.textContent = "by cbd";
        mark.setAttribute("aria-hidden", "true");
        document.body.appendChild(mark);
    }

    if (document.body) {
        addWatermark();
    } else {
        document.addEventListener("DOMContentLoaded", addWatermark, { once: true });
    }

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
        "[class*=\"video-ad\" i]",
        "[id*=\"video-ad\" i]",
        "[class*=\"player-ad\" i]",
        "[class*=\"ad-overlay\" i]",
        "[id*=\"ad-overlay\" i]",
        "[class*=\"overlay-ad\" i]",
        "[class*=\"floating-ad\" i]",
        "[class*=\"sticky-ad\" i]",
        "[class*=\"ad-float\" i]",
        "[class*=\"float-ad\" i]",
        "[class*=\"popup-ad\" i]",
        "[class*=\"ad-popup\" i]",
        "[class*=\"betway\" i]",
        "[class*=\"betting-widget\" i]",
        "[class*=\"widget-ad\" i]",
        "[class*=\"ad-widget\" i]",
        "[class*=\"advert\" i]",
        "[id*=\"gpt-ad\" i]",
        "[id^=\"div-gpt-ad\" i]",
        "[data-google-query-id]",
        "ins.adsbygoogle",
        ".adsbygoogle",
        "[data-link-tracking-page=\"Widget\"]",
        "iframe[id^=\"google_ads_iframe_\"]",
        "div[data-id-prefix^=\"aditude-placement-\"]",
        "[class^=\"ad-\"]",
        "[class*=\" ad-\"]",
        "[class$=\"-ad\"]",
        "[id^=\"ad-\"]",
        "[id$=\"-ad\"]",
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
        "img[src*=\"/retina/nextlevel/\"]",
        "img[src*=\"/retina2/\"]",
        "img[src*=\"/retina/farmskins/\"]",
        "img[src*=\"/retina/ggbet/\"]",
        "img[src*=\"/retina/egb/\"]",
        "img[src*=\"/retina/kinguin/\"]",
        "img[src*=\"skinwalletnews.jpg\"]"
    ];

    var AD_IFRAME_RE = /(doubleclick|googlesyndication|adservice\.google|uuidksinc|rtmark|vntsm|popads|propellerads|adsterra|hilltopads|onclickads|exoclick)/i;
    var AD_TEXT_RE = /(立即捡钱|立即前往|注册即送|注册领|注册送|领取|首存|首充|充值|雷火电竞|熊猫体育|开云体育|九游娱乐|betway|1xbet|n3b\.cc|leihuo58|181ty|kaiyun|电竞平台|体育平台)/i;
    var timer = 0;
    var lastTextClean = 0;
    var lastFloatingClean = 0;

    function isProtected(el) {
        try {
            return !!(el && el.closest && el.closest(PROTECTED));
        } catch (e) {
            return false;
        }
    }

    function hide(el) {
        if (!el || el.nodeType !== 1 || isProtected(el)) {
            return;
        }
        if (el.getAttribute("data-hltv-adblocked") === "1") {
            return;
        }
        el.setAttribute("data-hltv-adblocked", "1");
        el.style.setProperty("display", "none", "important");
    }

    function hideAdContainer(el) {
        if (!el || el.nodeType !== 1 || isProtected(el) || el.closest("[data-hltv-adblocked]")) {
            return;
        }
        var node = el;
        for (var depth = 0; depth < 4; depth++) {
            var parent = node.parentElement;
            if (!parent || parent === document.body || parent === document.documentElement) {
                break;
            }
            if (isProtected(parent) || parent.querySelector("table") ||
                parent.matches("main, article, .match-page, .contentCol, .leftCol, .rightCol, #match")) {
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
                text = (parent.innerText || "").trim();
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
            scope.querySelectorAll("a[href*=\"/out2/\"]").forEach(function (a) {
                if (isProtected(a)) {
                    return;
                }
                if (a.querySelector("img") || a.textContent.trim()) {
                    hideAdContainer(a);
                }
            });
        } catch (e) {
            // ignore
        }
    }

    function cleanAdText(scope) {
        try {
            var root = scope === document ? document.body : scope;
            if (!root) {
                return;
            }
            var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
            var node = walker.nextNode();
            while (node) {
                var text = (node.nodeValue || "").trim();
                if (text && text.length < 100 && AD_TEXT_RE.test(text)) {
                    var parent = node.parentElement;
                    if (parent && !parent.closest("[data-hltv-adblocked]")) {
                        hideAdContainer(parent);
                    }
                }
                node = walker.nextNode();
            }
            scope.querySelectorAll("img[alt], img[src]").forEach(function (img) {
                var label = (img.getAttribute("alt") || "") + " " + (img.getAttribute("src") || "");
                if (AD_TEXT_RE.test(label) && !img.closest("[data-hltv-adblocked]")) {
                    hideAdContainer(img);
                }
            });
        } catch (e) {
            // ignore
        }
    }

    function cleanFloatingAds(scope) {
        try {
            scope.querySelectorAll("div, section, aside, span").forEach(function (el) {
                if (isProtected(el) || el.closest("[data-hltv-adblocked]")) {
                    return;
                }
                var text = "";
                try {
                    text = (el.innerText || "").trim();
                } catch (e) {
                    text = "";
                }
                if (!text || text.length > 180 || !AD_TEXT_RE.test(text)) {
                    return;
                }
                var style = window.getComputedStyle(el);
                var position = style.position;
                var zIndex = parseInt(style.zIndex, 10) || 0;
                if (position !== "fixed" && position !== "absolute" && zIndex < 10) {
                    return;
                }
                var box = el;
                for (var depth = 0; depth < 3; depth++) {
                    var parent = box.parentElement;
                    if (!parent || parent === document.body || isProtected(parent)) {
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
            });
        } catch (e) {
            // ignore
        }
    }

    function clean(root) {
        var scope = root && root.querySelectorAll ? root : document;

        for (var i = 0; i < AD_SELECTORS.length; i++) {
            try {
                scope.querySelectorAll(AD_SELECTORS[i]).forEach(hide);
            } catch (e) {
                // 某个选择器被旧内核拒绝时继续跑其他的
            }
        }

        try {
            scope.querySelectorAll("iframe[src]").forEach(function (frame) {
                if (AD_IFRAME_RE.test(frame.src || "")) {
                    hide(frame);
                }
            });
        } catch (e) {
            // ignore
        }

        cleanAdLinks(scope);
        var now = Date.now();
        if (now - lastTextClean > 1200) {
            lastTextClean = now;
            cleanAdText(scope);
        }
        if (now - lastFloatingClean > 1000) {
            lastFloatingClean = now;
            cleanFloatingAds(scope);
        }

        // 顶栏 logoCon：保留第一个子节点（Logo），清掉后面夹带的广告
        try {
            scope.querySelectorAll(".logoCon").forEach(function (box) {
                if (isProtected(box)) {
                    return;
                }
                var kids = Array.prototype.slice.call(box.children);
                for (var j = 1; j < kids.length; j++) {
                    var child = kids[j];
                    var looksLikeAd = false;
                    try {
                        looksLikeAd = !!(
                            child.matches("a[href^=\"/out2/\"], img[src*=\"/retina/\"], img[src*=\"ad\"]") ||
                            child.querySelector(
                                "a[href^=\"/out2/\"], img[src*=\"/retina/\"], img[src*=\"ad\"]"
                            )
                        );
                    } catch (e) {
                        looksLikeAd = false;
                    }
                    if (looksLikeAd) {
                        child.remove();
                    }
                }
            });
        } catch (e) {
            // ignore
        }

        // 背景广告靠 body[data-href] 和动态 background-image 加载
        if (document.body) {
            if (document.body.hasAttribute("data-href")) {
                document.body.removeAttribute("data-href");
            }
            if (document.body.getAttribute("data-hltv-bg-cleaned") !== "1") {
                var bg = "";
                try {
                    bg = window.getComputedStyle(document.body).backgroundImage || "";
                } catch (e) {
                    bg = "";
                }
                if (bg && bg !== "none" && bg.indexOf("url(") !== -1) {
                    document.body.setAttribute("data-hltv-bg-cleaned", "1");
                    document.body.style.setProperty("background-image", "none", "important");
                }
            }
        }
    }

    function schedule() {
        if (timer) {
            return;
        }
        timer = window.setTimeout(function () {
            timer = 0;
            clean(document);
        }, 60);
    }

    function start() {
        clean(document);
        try {
            var observer = new MutationObserver(schedule);
            observer.observe(document.documentElement, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ["data-href", "style", "class"]
            });
        } catch (e) {
            // MutationObserver 不可用时还有下面的定时清理
        }

        // 页面脚本常常在前几秒不断插入广告，前 2 分钟多扫几次
        var ticks = 0;
        var interval = window.setInterval(function () {
            clean(document);
            ticks += 1;
            if (ticks >= 120) {
                window.clearInterval(interval);
            }
        }, 1000);

        ["play", "playing", "pause", "loadedmetadata", "seeked"].forEach(function (eventName) {
            document.addEventListener(eventName, schedule, true);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
        start();
    }
    window.addEventListener("load", schedule, { once: true });
})();
