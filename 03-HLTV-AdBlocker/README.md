# HLTV-AdBlocker · 反立即捡钱插件

在 `hltv.org` 上屏蔽赌博、弹窗、背景和横幅广告，并为新闻、评论、选手和战队补充中文参考。

**版本：v1.2.0 · Microsoft Edge / Chromium · 安装后单文件 CRX**

[下载 HLTV-AdBlocker.crx v1.2.0](https://github.com/d1zzyyyuki/vibecoding/releases/download/hltv-adblocker-v1.2.0/HLTV-AdBlocker.crx) · [下载 Edge 白名单 CMD v2](https://github.com/d1zzyyyuki/vibecoding/releases/download/hltv-adblocker-v1.2.0/HLTV-AdBlocker-Edge-Policy.cmd)

## v1.2.0 更新

- 优化 `content.js` / `zh.js` 执行策略：选择器合并、增量 MutationObserver、正则预编译、翻译请求去重
- 修复内容脚本和翻译脚本互相误伤：含“领取/首充/充值”的译文或评论不再被广告清理器隐藏
- 修复 `.logoCon` 顶栏被整条隐藏的问题，现在只隐藏广告子节点，保留 HLTV Logo
- 翻译节点不再触发自身重扫；MyMemory 额度耗尽后停止请求
- 去掉无效的 MyMemory 权限，manifest 加入固定 `key` 保持扩展 ID
- 修复 `nice try` / `NT` 的翻译，输出“尽力了”
- 补 `olofmeister（奥拉夫）`
- 翻译缓存升级到 v2，旧版缓存里的 Wildcard 错误不会再复用
- CMD 升级为 v2：支持 `/status`、`/remove`、幂等写入和回读校验

## v1.1.2 新增

- 修复 `Lynn Vision qualify for Stage 2 over HEROIC` 译成“通过 HEROIC 进入第 2 阶段”的问题，现在输出 `LVG战胜HEROIC，晋级Stage 2`
- `Stage 1` / `Stage 2` 等阶段名统一保留英文，不再混用“第一阶段 / 第2阶段”
- `eliminate` 不再译成“消除”，改成“淘汰出”
- `bench` 不再译成“替补”，改成“将选手放上替补席”
- 修复比赛/新闻评论没有参考翻译的问题；HLTV 实际评论容器是 `.forum-middle`
- 修复把“登录或注册即可评论”的提示误当成评论翻译的问题
- 保留 v1.1.1 的全部别称、广告过滤和翻译修复

## v1.1.1 新增

- 补 `kyousuke（京介）`、`SunPayus（太阳神）`、`chopper（大超）` 等选手别称
- `Lynn Vision` 统一显示/翻译为 `LVG`；`BETBOOM` 统一为 `BB`
- `Wildcard` 保持英文，不翻译
- `Major`、`IEM`、`ESL`、`BLAST`、`CS2`、`MVP` 等 CS 术语保持原文
- 翻译里的战队称呼统一使用 CS 圈常用说法
- 战队页面的队员列表也补上选手外号，不再只在比赛数据页生效
- `FUT`、`MIBR` 等没有通用别称的战队保持原名
- 修复 `Wildcard` 仍被机翻的问题
- 修复 `device denies the plant with a crucial shot` 这类 CS 句式被译成“设备/工厂/镜头”的问题，现在输出 `device用关键一枪阻止了下包`

## v1.1.0 新增

- HLTV 首页 **Today's news** 标题下方增加灰色小字中文参考翻译
- 新闻和比赛评论下方增加灰色小字 `参考翻译：…`
- 比赛页、数据表里的选手名后补灰色中文别称，例如 `TeSeS（龙哥）`、`karrigan（大表哥）`
- 战队名后补灰色中文别称，例如 `Falcons（猎鹰）`、`Spirit（绿龙）`
- 新闻和评论的翻译文本里，战队/选手名会替换成中文别称；`FUT`、`MIBR` 这种没有通用别称的保持原名
- 视频播放器上的浮动广告继续过滤

## 为什么做这个

HLTV 的比赛数据和赛程更新很快，但页面会夹带大量赌博/博彩广告。直播时打开 HLTV，这些广告容易让直播间被平台警告。

这个插件只清理广告，不碰 HLTV 的赔率区块。

## 安装（Edge）

1. 打开 `edge://extensions`
2. 打开左下角 **开发人员模式**
3. 如果看到 **允许来自其他应用商店的扩展**，也打开
4. 把 `HLTV-AdBlocker.crx` 拖进扩展页面
5. 完全退出 Edge（任务栏右键退出，而不是只关窗口）
6. 可选：右键 [`HLTV-AdBlocker-Edge-Policy.cmd`](https://github.com/d1zzyyyuki/vibecoding/releases/download/hltv-adblocker-v1.2.0/HLTV-AdBlocker-Edge-Policy.cmd)，选择 **以管理员身份运行**
7. 重新打开 Edge，把 HLTV-AdBlocker 的开关打开
8. 刷新 HLTV 页面

如果之前装过旧版，先删除旧扩展，再重复第 4–7 步。

> v1.2.0 的 CMD v2 是可选策略辅助，不是安装器。实际安装主要依赖开发者模式和 CRX；如果你的 Edge 没有配置 `ExtensionInstallBlocklist`，allowlist 可能不改变安装行为。如果 CRX 被拒绝，最稳的兜底是“加载解压缩的扩展”。

### 关于“单文件”

下载下来是 **CRX + 可选 CMD 两个小文件**；CMD 只做一次 Edge 白名单辅助，不参与插件运行。

- 扩展本体始终是一个 **CRX 单文件**，不需要解压、没有文件夹依赖。
- CMD 可以删除；插件安装完成后不依赖它。
- 换电脑时只需要 CRX；CMD 按需使用，便携、下载体积约 35 KB + 6 KB。

CMD v2 支持：

```text
HLTV-AdBlocker-Edge-Policy.cmd /status   只看当前策略，不需要管理员
HLTV-AdBlocker-Edge-Policy.cmd /remove   删除白名单项
```

## 如果提示 `CRX_REQUIRED_PROOF_MISSING`

这是 Edge 对“非 Edge 加载项商店来源”的 CRX 强制校验，和插件代码无关。优先按上面的开发者模式方式安装；如果仍然被拒，从源码仓库下载 `03-HLTV-AdBlocker/extension/` 目录，用 **加载解压缩的扩展** 安装。

## 会清理什么

- 顶部/两侧的赌博广告位、背景广告、`logoCon` 里夹带的赞助横幅
- Thunderpick、GG.Bet、1xBet 等博彩赞助框
- Google Ad Manager / DoubleClick 等广告网络的请求
- 弹窗、弹层类广告域名（PopAds、PropellerAds、Adsterra 等）
- 动态插入的广告 iframe、广告图片和广告容器

## 不会动什么

- **比赛赔率、赔率表、盘口数据**
- 赛程、比赛结果、新闻、数据页
- HLTV 站内的正常导航和链接

## 技术说明

- Manifest V3
- `declarativeNetRequest` 静态规则拦截广告网络（规则见 `extension/rules.json`）
- Content Script 在 HLTV 页面清理残留的广告容器和背景广告
- `zh.js` 负责新闻/评论参考翻译、选手和战队灰色别称
- 翻译通过 MyMemory 的公开接口，只发送需要翻译的标题/评论文本；不发送 cookie、账号或浏览历史，翻译结果缓存在本机
- 不注入远程代码，不收集数据，不联网回传（翻译请求除外）
- 所有广告域名规则只在 HLTV 页面发起的第三方请求上生效（`initiatorDomains: hltv.org`）

## 目录

```text
extension/           扩展源码（manifest、规则、content script、中文辅助、图标）
assets/              图标母版
tools/               图标生成、CRX 打包脚本
install/             Edge 白名单一次性修复脚本
dist/                构建产物（HLTV-AdBlocker.crx，不提交 Git）
```

## 构建

需要 Windows + Edge（Chromium 内核）。在项目目录执行：

```powershell
.\tools\build_crx.ps1
```

产物：

```text
dist/HLTV-AdBlocker.crx
```

首次构建会在 `keys/` 下生成签名私钥，后续构建复用它，保证扩展 ID 稳定。`keys/` 和 `dist/` 都不进仓库。

## 更新记录

### v1.2.0

- 优化内容脚本执行策略，修复广告清理与翻译脚本互相误伤。
- `.logoCon` 只隐藏广告子节点，保留 Logo。
- `nice try` / `NT` 翻译为“尽力了”，补 `olofmeister（奥拉夫）`。
- 翻译缓存升级到 v2，修复旧缓存导致 Wildcard 仍被翻译的问题。
- manifest 去掉无效权限并固定 key。
- CMD v2 支持 status/remove/回读校验。

### v1.1.2

- 修复 LVG / HEROIC 晋级句的语义。
- Stage 1 / Stage 2 统一保留英文。
- `eliminate` 改译“淘汰出”，`bench` 改译“放上替补席”。
- 修复新闻/比赛评论翻译；排除登录提示，不再误翻。

### v1.1.1

- 补充京介、太阳神、大超等选手别称。
- `Lynn Vision → LVG`、`BETBOOM → BB`；`Wildcard` 保持英文。
- 保护 `Major` 等 CS 术语和赛事名，翻译里统一使用“战队”称呼。
- 战队页队员列表也补灰色外号。
- 翻译中的战队/选手名称统一走同一套词表。
- 修复 Wildcard 被机翻、CS 固定句式误译（device/plant/crucial shot）的问题。

### v1.1.0

- 新闻标题、新闻评论和比赛评论增加中文参考翻译。
- 选手和战队增加灰色中文别称；翻译文本里的队名/选手名同步替换。
- 保留 v1.0.0 的全部广告过滤和 Edge 安装方式。
- 视频悬浮广告过滤继续保留。
- 扩展简介已更新为“广告过滤 + 中文化”，保持精简。

### v1.0.0 整理

- 精简扩展简介文案。
- 补强视频播放器浮动广告、`/out2/` 广告链接容器、Betway / 九游 / 雷火 / 熊猫 / 开云 / Stake 等赞助位的过滤。
- 重写 Edge 安装说明，补充本地 CRX 白名单方式和“运行 CMD 后保持单文件 CRX”的说明。

## 已知限制

- 本地 CRX 安装需要 Edge 开发人员模式，这是 Edge 的限制，不是插件需要联网安装
- 参考翻译依赖 MyMemory 网络服务；请求失败时不会显示翻译，稍后刷新即可
- 机器翻译只作参考，新闻标题和评论里的语气/梗可能不准确
- HLTV 改版后广告容器类名可能变化，需要更新 `content.css` / `content.js`
- 第三方直播 iframe 内部的广告不在本插件控制范围内
- 没有上架 Edge 加载项商店，因此不会自动更新

## License

MIT，见 [LICENSE](LICENSE)。
