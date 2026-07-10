# maplebirch-v3-layer-compat

秋枫白桦框架 v3.1.14 图层命名兼容补丁（NPC 侧边栏身体层 + PC 脸部 blush 层）。

## 这个 mod 解决什么问题

在 DoL 0.5.9.8+（含 0.5.10.x）上，搭配 maplebirch **v3.1.14** 框架时，NPC 侧边栏和 PC 脸部会刷出一批加载失败报错：

```
Failed to load image img/body/basehead.png for layer nnpc_head ;
Failed to load image img/body/basenoarms-classic.png for layer nnpc_body ;
Failed to load image img/body/leftarmidle-classic.png for layer nnpc_leftarm ;
Failed to load image img/body/rightarmidle-classic.png for layer nnpc_rightarm ;
Failed to load image img/body/breasts/breasts0.png for layer nnpc_breasts ;
Failed to load image img/face/default/default/blush1.png for layer blush ;
```

### 根因（一句话）

maplebirch v3.1.14 的图层 `srcfn` 生成的是**旧版无连字符**图片名（`basehead`、`breasts0`、`leftarmidle`、`blush1`），
而游戏 0.5.9.8+ 与 AU 美化包提供的都是**新版带连字符**命名（`base-head`、`breasts-0`、`left-arm-idle`、`blush-1`）。
名字对不上 → 图层 404。

上游在 maplebirch **v4.1.6–v4.1.12** 把所有图层改成了带连字符命名修好了这个问题。
但稳定线必须停留在 3.x（因为 maplebirchExpansion v1.2.4 只有 3.x 版，没有 4.x 兼容版），
吃不到这批修复，所以需要这个补丁把 v4 的命名逻辑 **backport** 到 3.x。

## 工作原理

补丁通过框架公开 API `maplebirch.char.use(layerMap)` 重新注册受影响图层的 `srcfn`，
把它们改写成 v4.1.12 的带连字符命名。**不修改框架任何源码**，是标准的 addon 用法。

覆盖的图层（全部来自 v4.1.12 源码逐条转写）：

| 图层 | v3.1.14（坏） | 本补丁（= v4.1.12） |
|------|--------------|---------------------|
| `nnpc_head` | `img/body/basehead.png` | `img/face/<style>/base-head.png`，`loadImage`失败回退 `img/body/base-head.png` |
| `nnpc_body` | `basenoarms-classic.png` | `base-classic.png` |
| `nnpc_breasts` | `breasts0.png` | `breasts-0.png` / `clothed-N.png` |
| `nnpc_leftarm` | `leftarmidle-classic.png` | `left-arm-idle-classic.png` / `left-arm-cover.png` |
| `nnpc_rightarm` | `rightarmidle-classic.png` | `right-arm-idle-classic.png` / `right-arm-<pose>.png` |
| `blush` | `blush1`（无连字符） | `blush-1`（带连字符） |

### 为什么安全

1. **深合并、只覆盖叶子**：`char.use()` 内部是 `merge(this.layers, obj, { mode: 'merge' })`。
   本补丁每个图层只提供 `srcfn`，其余字段（`showfn`/`zfn`/`dxfn`/`dyfn`/`filters`/`animation`/`masksrcfn`）
   原样保留框架自己的逻辑，不动。
2. **加载序天然靠后**：`boot.json` 声明依赖 `maplebirch`，所以本 mod 必然在框架之后加载。
   补丁在 `:storyready` 事件里执行（此时框架的 `NPCSidebar.init()` 已注册完基础层），
   合并顺序保证我们的 `srcfn` 最后写入、生效。
3. **blush 复用框架自己的 `faceStyleSrcFn`**：5 级路径回退级联与框架完全一致，
   只是叶子名多了一个连字符。

## 适用范围

- ✅ maplebirch **v3.x**（`>=3.1.0 <4.0.0`，见 boot.json 依赖声明）
- ❌ maplebirch v4.x：v4 已自带修复，装本补丁无害但无意义（同名覆盖成同样的值）。
  boot.json 的版本上限 `<4.0.0` 会让 ModLoader 在 4.x 上跳过它。

## 制作经验记录（给后来者）

这个 mod 是 DOL-X 项目第一个**自研**的兼容 mod，过程沉淀几条经验：

1. **先拿源码，别靠更新日志推断**。最初根因是靠 maplebirch 的 `UPDATE.md` 推断的，
   直到把 v3.1.14 / v4.1.12 两个 tag 的 `base_layers.ts`、`Character.ts` 源码拉下来逐行对比，
   才坐实“就是连字符命名”这一个点。省掉了一整轮猜测。
2. **认清 API 的合并语义**。`char.use()` 是深合并而非整体替换，这决定了补丁只需写 `srcfn`
   而不用把每层所有字段抄全——抄全反而容易和框架的其它修复打架。
3. **时机 = 事件 + 加载序**。covering-layer 类补丁最怕“被框架默认值盖回去”。
   先读 `EventEmitter.trigger`（按注册序遍历）+ `boot.json` 依赖（决定加载序），
   确认 `:storyready` 里注册必然靠后，才敢下笔。
4. **复用框架内部函数走公开出口**。`nnpc_head` 的回退要用 `loadImage`，
   它通过 `maplebirch.tool.utils.loadImage` 暴露；blush 的 5 级回退用 `maplebirch.char.faceStyleSrcFn`。
   能复用就别重写，行为才对得齐。
5. **boot.json 的空数组字段是保命字段，一个都不能省（血泪教训）**。
   本 mod 第一版 boot.json 图简洁，只写了实际用到的 `scriptFileList`，省掉了
   `styleFileList` / `tweeFileList` / `imgFileList`。结果整个 mod 被 ModLoader
   **静默拒绝**——进了包、却不加载、mod 管理器里查无此 mod、只在日志里留一行
   `validateBootJson(bootJ) failed`。表现就是"补丁像没装一样，报错原样保留"，
   极难排查（因为它不报错、只是不出现）。
   根因：ModLoader 的 `ModZipReader.validateBootJson` 硬性要求
   `styleFileList` / `scriptFileList` / `tweeFileList` / `imgFileList` **四个字段
   必须显式存在且是字符串数组**（`isArray(undefined) === false` → 整个校验挂）。
   即使为空也必须写成 `[]`。对照旁证：同样极简的 `GuideToMe` 能正常加载，
   正因为它老实写全了这几个空数组。
6. **本地就能模拟 ModLoader 的合法性校验，别只靠"构建日志说注入成功"**。
   构建期"mod 打进包了"和运行期"ModLoader 接受它"是两回事。本地虽然跑不了浏览器，
   但可以从构建产物 HTML 里挖出 `validateBootJson` 的布尔门表达式（`let c = ...`），
   用脚本对着待发布的 boot.json 逐字段核对那 6 项检查（name/version 非空 +
   四个 FileList 是数组）。这是本地能做的、最接近真机的 mod 合法性验证，
   交付手写 mod 前应当作为标准步骤。

## 许可

随 DoL 本体，遵守 CC BY-NC-SA 4.0。
