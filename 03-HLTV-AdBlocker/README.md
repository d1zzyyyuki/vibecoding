# HLTV-AdBlocker · 反立即捡钱插件

在 `hltv.org` 上屏蔽赌博、弹窗、背景和横幅广告，并为新闻、评论、选手和战队补充中文参考。

**版本：v1.1.1 · Microsoft Edge / Chromium · 安装后单文件 CRX**

[下载 HLTV-AdBlocker.crx](https://github.com/d1zzyyyuki/vibecoding/releases/tag/hltv-adblocker-v1.1.1)

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
6. 右键 `HLTV-AdBlocker-Edge-Policy.cmd`，选择 **以管理员身份运行**
7. 重新打开 Edge，把 HLTV-AdBlocker 的开关打开
8. 刷新 HLTV 页面

如果之前装过旧版，先删除旧扩展，再重复第 4–7 步。

### 关于“单文件”

严格说，下载下来是 **CRX + CMD 两个小文件**，因为 Edge 158 必须先做一次白名单校验；这不是插件要求，是浏览器的限制。

- CMD 只需要运行一次，之后扩展本体就是一个 **CRX 单文件**。
- 不需要解压、不需要加载文件夹、没有运行依赖。
- CMD 只是把扩展 ID 加入 Edge 白名单，可以删除；扩展安装完成后不依赖它。
- 换电脑时仍然只需要这两个小文件，便携、下载体积约 32 KB + 1 KB。

CMD 会写入一条 Edge 扩展白名单策略（`ExtensionInstallAllowlist`），只针对本扩展 ID；Edge 可能显示“由组织管理”，这是策略生效提示，不是改系统其它设置。不想要策略时，用管理员权限执行 CMD 中提示的 `reg delete` 命令即可。

## 如果提示 `CRX_REQUIRED_PROOF_MISSING`

这是 Edge 158 对“非 Edge 加载项商店来源”的 CRX 强制校验，和插件代码无关。扩展通常已经出现在列表里，只是开关是灰的。

按上面的安装步骤执行即可。如果不想改策略，也可以兜底：从源码仓库下载 `03-HLTV-AdBlocker/extension/` 目录，用 **加载解压缩的扩展** 安装。

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
- Release 继续只维护 v1.0.0，不新增版本号。

## 已知限制

- 本地 CRX 安装需要 Edge 开发人员模式，这是 Edge 的限制，不是插件需要联网安装
- 参考翻译依赖 MyMemory 网络服务；请求失败时不会显示翻译，稍后刷新即可
- 机器翻译只作参考，新闻标题和评论里的语气/梗可能不准确
- HLTV 改版后广告容器类名可能变化，需要更新 `content.css` / `content.js`
- 第三方直播 iframe 内部的广告不在本插件控制范围内
- 没有上架 Edge 加载项商店，因此不会自动更新

## License

MIT，见 [LICENSE](LICENSE)。
