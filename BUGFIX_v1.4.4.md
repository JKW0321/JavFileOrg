# Bug 修复说明（历史记录，当前基线：v1.5.0-Selenium）

> 说明：本文是 v1.4.4 阶段的增量修复记录。当前正式基线版本为 `v1.5.0-Selenium`。

## 🐛 问题描述

**用户报告**：
> 整理后文件名仍然在番号前面有网站名称。

**影响版本**：v1.4.3-Selenium
**严重程度**：🔴 高 — 用户可见，影响最终输出
**修复版本**：v1.4.4-Selenium (2026-07-03)

---

## 🔍 根因分析

`jav_file_organizer.py:856` 的 `sanitize_filename()` 只支持 4 种网站名清理规则：

```python
name = re.sub(r'\s*javbus\s*$', '', name, flags=re.IGNORECASE)
name = re.sub(r'\s*javhoo\s*$', '', name, flags=re.IGNORECASE)
name = re.sub(r'^\s*javbus\s*', '', name, flags=re.IGNORECASE)
name = re.sub(r'^\s*javhoo\s*', '', name, flags=re.IGNORECASE)
```

这些规则有以下缺陷：

1. **只匹配 `javbus` / `javhoo` 两个白名单** — `4k2.com@`、`hhd800.com@`、`169bbs.com@` 等十几种下载站前缀完全漏掉
2. **不支持 `@` 前缀** — v1.3.1 在 `clean_filename_for_search()` 里写过 `@` 清理，但 v1.4.3 重命名时直接拿原始 title 拼，没复用
3. **只匹配"独立单词"** — `[javbus]`、`(javbus)`、`javbus - xxx` 这类带括号/连字符的形式 100% 漏掉

### 触发链路

文件最终命名 = `extract_content()` 返回的 `title` → `sanitize_filename(f"{title}.mp4")`

`title` 来源有两种情况带网站名：
1. **JavBus / JavHoo 网页本身嵌了站点水印**
2. **`xxx.com@yyy` 这种下载站前缀**

v1.4.3 把"搜索用清理"和"重命名用清理"拆成了两套规则，后者更弱。

---

## ✅ 修复方案

### 重构（方案 B）

不再在 `sanitize_filename` 里修修补补，而是：

1. **抽出独立的 `filename_utils.py` 模块**，集中所有文件名相关的纯函数：
   - `strip_site_markers(name)` — 统一的网站名清理函数（**v1.4.4 新增核心**）
   - `extract_code_from_text(filename)` — 番号提取
   - `clean_filename_for_search(filename)` — 搜索词生成
   - `sanitize_filename(filename)` — 最终文件名清理

2. **`jav_file_organizer.py` 改为 thin wrapper**，所有同名方法只调纯函数 + 打日志。
   - 保留为实例方法的原因：`AtomicProcessor(self.sanitize_filename)` 这种回调场景

3. **`strip_site_markers` 处理所有已知网站名形态**：
   - 下载站前缀：`4k2.com@xxx`、`*.org@xxx`（正则 `^[\w][\w.-]*@`）
   - 带方括号：`[javbus]`、`(javbus)`、`【javhoo】`
   - 带连字符：`javbus - xxx`、`xxx - javbus`、`javbus-xxx`
   - 独立单词：开头 `javbus xxx`、末尾 `xxx javbus`
   - 大小写不敏感：`JAVBUS` 也能匹配

4. **`extract_code_from_text` 调用 `strip_site_markers`**，让下载站前缀场景也能正确提取番号。

5. **完整测试覆盖**：新增 `test_filename_utils.py`，**56 个测试用例全部通过**。

---

## 📊 修复效果对比

| 输入 | v1.4.3 输出（错误） | v1.4.4 输出（正确） |
|---|---|---|
| `4k2.com@ABF-139-C.mp4` | `4k2.com@ABF-139-C.mp4` ❌ | `ABF-139-C.mp4` ✅ |
| `hhd800.com@SONE-753-C_[4K].mp4` | `hhd800.com@SONE-753-C_[4K].mp4` ❌ | `SONE-753-C_[4K].mp4` ✅ |
| `javbus.com@START321.mp4` | `.com@START321.mp4` ❌（半清理出错） | `START321.mp4` ✅ |
| `[javbus] (javbus) javbus - ABF-139.mp4` | 原样保留 ❌ | `ABF-139.mp4` ✅ |
| `ABF-139 javbus.mp4` | `ABF-139 javbus.mp4` ❌ | `ABF-139.mp4` ✅ |
| `javbus - START-321.mp4` | `- START-321.mp4` ❌ | `START-321.mp4` ✅ |

---

## 📝 修改文件清单

| 文件 | 变更 | 行数变化 |
|---|---|---|
| `filename_utils.py` | **新增** — 抽出全部纯函数 | 0 → 266 |
| `jav_file_organizer.py` | 改用 `from filename_utils import ...` | 1870 → 1740（-130） |
| `test_filename_utils.py` | **新增** — 56 个测试用例 | 0 → 200 |

---

## 🧪 测试

```bash
$ python3 -m pytest test_filename_utils.py -v
============================== 56 passed in 0.03s ==============================
```

测试覆盖：
- `strip_site_markers`: 23 个用例（含 5 个误伤防护）
- `extract_code_from_text`: 14 个用例（含 3 个 no-match）
- `clean_filename_for_search`: 7 个用例
- `sanitize_filename`: 10 个用例

---

## ⚠️ 已知行为变更

1. **`javbus.mp4` → `unnamed.mp4`** — 整串就是 javbus 时被 strip 成空，然后降级为 `unnamed`。这是有意取舍：宁可改名也不留网站名。如果有用户希望保留这种罕见合法文件名，可以后续加开关。

2. **`extract_code_from_text` 现在会剥离版本后缀**（如 `-C`、`-U`）。这是修复前 `clean_filename_for_search` 降级路径已有的行为，现在两条路径统一，避免出现"提取到 `ABF-139-C` 但搜索词是 `abf-139`"的不一致。

3. **`clean_filename_for_search('RBD011a.mp4')` 现在返回 `rbd-011` 而不是 `rbd-011a`** — 因为 `RBD011a` 被识别为序列文件（base=`RBD-011`, seq=`1`），优先返回基础番号。这是 Bug 3 的连锁修复：以前单文件路径会按 `rbd-011a` 单独搜索，可能搜不到正确封面（因为网站一般只有 `RBD-011` 整个系列的封面页）。

---

## 🐛 Bug 3：序列文件识别失败导致"图片-1、视频-1"

### 用户报告（2026-07-03）

> 之前还有一个 bug，就是在处理多文件连续视频的时候，如 xxx-1, xxx-2，整理后应该是一个 jpg + 视频文件 -1 -2 -3 的结构。后来变成 图片-1，视频-1 的了。

### 根因

两层 bug 叠加：

**Bug 3a — `extract_series_info` 正则用 `^...$` 锚点**

主程序 `jav_file_organizer.py:787` 的 4 个序列正则：

```python
pattern1 = r'^([a-zA-Z]+-\d+)-(\d+)$'
pattern2 = r'^([a-zA-Z]+-\d+)([a-zA-Z])$'
pattern3 = r'^([a-zA-Z]+\d+)-(\d+)$'
pattern4 = r'^([a-zA-Z]+\d+)([a-zA-Z])$'
```

每个都要求 **stem 整个就是** `ABC-123-N` 形式。实际用户下载的视频 99% 是带完整标题的：

| 文件名 | 修复前识别结果 |
|---|---|
| `ABF-139-1.mp4` | ✅ 识别成 `(ABF-139, 1)` |
| `ABF-139-1 美少女 第1話.mp4` | ❌ 识别失败，当成独立文件 |
| `ABF-139a 美少女.mp4` | ❌ 识别失败 |
| `4k2.com@ABF-139-1 美少女.mp4` | ❌ 识别失败 |

**Bug 3b — 走单文件路径时，搜索词包含序列号**

被错误识别成"独立文件"后，`clean_filename_for_search` 提取出 `abf-139-1`（**保留了 `-1`**），用这个去搜索网站 → 网站返回的 title 可能相同（因为 `abf-139-1`、`abf-139-2` 都能搜到同一页），但每集都被独立处理 → 每集都单独下载一张图 → 最终文件命名混乱。

### 修复

**修复 1**：在 `filename_utils.py` 新增 `extract_series_info()` 纯函数：
- 用 `re.search` 替代 `re.match`，去掉 `^$` 锚点
- 支持 stem 含完整标题、下载站前缀等场景
- 调用 `strip_site_markers` 先清理网站名前缀，避免 `4k2.com@` 中的 `.` 干扰 `\b` 边界
- 顺序敏感：先 strip → 再切扩展名（顺序反了 `'4k2.com@xxx'.rsplit('.', 1)[0]` 会截成 `'4k2'`）

**修复 2**：在 `clean_filename_for_search()` 中**优先调用** `extract_series_info()`：
- 命中时返回基础番号（`abf-139`），不带 `-1`/`-a` 后缀
- 避免每集按 `abf-139-1`、`abf-139-2` 单独搜索 → 拿不到系列封面
- 没识别成序列时降级到原 `extract_code_from_text` 路径

**修复 3**：主程序 `extract_series_info` 方法改为 thin wrapper（同步前面 `sanitize_filename` 等的架构）。

### 修复后行为

```
输入文件:
  ABF-139-1 美少女 第1話.mp4
  ABF-139-2 美少女 第2話.mp4
  ABF-139-3 美少女 第3話.mp4

detect_series_files:
  → groups: {'ABF-139': [(file1, '1'), (file2, '2'), (file3, '3')]}
  → standalone: []

process_series_group(ABF-139):
  → 搜索关键词: abf-139 (不带 -1)
  → 网站返回 title: "ABF-139 美少女と、貸し切り温泉と、濃密性交と。"
  → 下载 1 张共享封面: ABF-139.jpg
  → 移动文件:
      ABF-139 美少女と、貸し切り温泉と、濃密性交と。-1.mp4
      ABF-139 美少女と、貸し切り温泉と、濃密性交と。-2.mp4
      ABF-139 美少女と、貸し切り温泉と、濃密性交と。-3.mp4

最终 Finish/ 目录:
  ✅ ABF-139.jpg           (共享封面)
  ✅ ABF-139 ...-1.mp4     (第1集)
  ✅ ABF-139 ...-2.mp4     (第2集)
  ✅ ABF-139 ...-3.mp4     (第3集)
```

### 测试

```
test_filename_utils.py
├── TestStripSiteMarkers          (23 用例)
├── TestExtractCode               (14 用例)
├── TestCleanFilenameForSearch    ( 7 用例)
├── TestSanitizeFilename          (10 用例)
├── TestExtractSeriesInfo         (21 用例, NEW)
├── TestCleanFilenameForSearchSeries ( 8 用例, NEW)
└── TestDetectSeriesFiles         ( 4 用例, NEW, 端到端)

============================== 89 passed in 0.14s ==============================
```

---

## 🎯 经验教训

1. **同一类清理逻辑只写一次** — v1.3.1 的 `@` 清理在 `clean_filename_for_search` 里写过一遍，v1.4.3 重命名时又要写一遍但没复用，是典型的复制粘贴债务
2. **thin wrapper > 复制实现** — 把核心逻辑放纯函数，方法只负责日志/回调/副作用，主程序瘦了 130 行
3. **白名单黑名单都要测** — 不仅要测"该清理的被清掉了"，还要测"不该清理的不要清掉"（java ≠ javbus）
4. **正则 `\b` 不认识 `-`** — pattern 2 `ABC-123X` 在 `X` 后面是 `-` 时没有 word boundary，会漏匹配。这是导致 `ABF-139-C` 提取异常的根因。
5. **strip 顺序敏感** — `'4k2.com@ABF-139'.rsplit('.', 1)[0]` 返回 `'4k2'`，不是 `'4k2.com@ABF-139'`。先 strip 网站前缀 → 再切扩展名，反过来就截错。
6. **网站改版是常态** — JavHoo URL 结构变了 `/en/{query}` → `/search/{query}`，代码用的还是老 URL，**完全失效**且没人发现（因为没真实网络测试）。

---

## 🐛 Bug 4：JavHoo 搜索 URL 失效 + 无详情页升级

### 用户问题

> 你看看 javhoo 还有别的办法吗？

### 实测 javhoo.com（2026-07-03）

| URL | 状态 |
|---|---|
| `https://www.javhoo.com/en/ABF-139`（代码当前用的）| ❌ **404 Not Found** |
| `https://www.javhoo.com/en/search/ABF-139` | ✅ 200 + 25KB 内容 |
| `https://www.javhoo.com/search/ABF-139` | ✅ 200 + 26KB 内容（含 article）|
| `https://www.javhoo.com/?s=ABF-139` | ✅ 200 + 25KB |

**结论**：JavHoo 站改版了，URL 结构从 `/en/{code}` 变成 `/search/{code}`。**当前代码 JavHoo 实际完全失效**，只是没人触发测试才发现。

### 实测拿到的好数据（验证 A+C 修复有效）

```
SONE-753:
  title = 'SONE-753 大人しい新入女子社員を一泊出張に同行させ相部屋に連れ込むと…
           まさかのド淫乱メスに変身して精液透明になるまで絞りヌカれた… 乃坂ひより'
  image = 'https://pics.javhoo.net/2025/07/SONE-753_b.jpg'  ← 详情页的高清 _b 版本

SSIS-001:
  title = 'SSIS-001 一ヶ月間の禁欲の果てに彼女のルームメイト2人と浮気SEXだけに…'
  image = 'https://pics.javhoo.net/2021/02/cover/SSIS-001.jpg'

STAR-999:
  title = 'STAR-999 SODstar 唯井まひろ 18歳 性感エステ×フルコース 10コーナー240分SP'
  image = 'https://pics.javhoo.net/thumb.png'  ← 搜索页的小图（详情页偶尔 timeout 时兜底）
```

### 修复 A：搜索 URL

```diff
- 'search_url': 'https://www.javhoo.com/en/{query}',
+ 'search_url': 'https://www.javhoo.com/search/{query}',
```

同步改了 GUI 默认值 (`search_url_var`)，用户开软件就能看到正确 URL。

### 修复 C：详情页升级（拿高清封面 + 更准标题）

新增两个辅助方法：

**`_find_detail_url(soup, search_url, search_query, detail_pattern)`**
- 从搜索结果页的 `<article>` 里挑 `<a href="/sone-753">` 这种详情页 URL
- 兜底：用 `detail_url_pattern` 直接拼（小写 code）

**`_fetch_detail_page(detail_url, search_url, website_config)`**
- GET 详情页（超时 10s，比搜索页更严）
- 提取 `<h1>` 标题 + `pics.javhoo.net` 域名的高清封面
- 异常全部向上抛，由 `extract_content` 的 try/except 兜底

**配置新增字段 `detail_url_pattern`**（可选）：
```python
'detail_url_pattern': 'https://www.javhoo.com/{code_lower}',
```

**升级逻辑**（`extract_content` 内）：
```python
if detail_url and (title or image_url):
    try:
        upgrade_title, upgrade_image = self._fetch_detail_page(...)
        # 详情页拿到的标题更精准时优先用
        if upgrade_title and len(upgrade_title) > len(title or ''):
            title = upgrade_title
        # 详情页封面优先（更高清）
        if upgrade_image:
            image_url = upgrade_image
    except Exception as e:
        self.log(f"⚠️ 详情页升级失败（保留搜索页结果）: {e}", "WARNING")
```

**关键设计**：详情页失败时**绝不丢失**已拿到的搜索页数据，只是 log 一行 warning。这保证 JavHoo 详情页偶发 timeout（实测有）时整体不挂。

### 兼容设计

- `detail_url_pattern` 是可选字段 — JavBus / JAVLibrary 不填就走原有路径
- `_find_detail_url` 返回 None 时整段升级逻辑跳过
- 旧 GUI 配置不会被破坏（只改默认值）

### 已知遗留问题（v1.4.5 待办）

未收录的番号（实测 ABF-139、MIAB-001）会拿到垃圾值：
- title = `"搜索结果    abf-139"`
- image = `"https://pics.javhoo.net/logo.png"`

不是崩，是**不精准**。需要新增 `no_results_selector` 配置 + 检测逻辑，命中时直接 return None。下个版本处理。

### 新增测试

`test_javhoo_live.py` — 真实访问 javhoo.com 的 3 个测试：

```
[A: 搜索 URL 修复]                ✅
[A+C: extract_content 已知番号]   ✅ 3/3 (SONE-753 / STAR-999 / SSIS-001)
[A: 未收录番号兜底]                ✅ 不崩
```

容忍网络抖动：单次 timeout 自动重试 2 次；至少 50% 命中率才算通过。

### 全套测试结果（2026-07-03）

```
test_filename_utils.py           89 passed    (单元测试)
test_e2e_series_e2e.py            2/2 通过     (序列文件 e2e)
test_javhoo_live.py               3/3 通过     (JavHoo 真实网络)
```

---

## 🐛 Bug 5（已复现、用户选择不改）：_1 占位文件

### 用户描述（2026-07-03）

> 有的时候会多保存出来一套图片+视频，后缀加了 _1 的文件，视频文件很小，只是占位，图片是完整的。同时也有一套正常的存在。

### 复现脚本

`test_repro_duplicate.py` — 跑了两个场景：

**场景 A：Finish 里已有同名文件**
```
预设: Finish/ABF-139.mp4 = 100 字节（之前处理留下的）
→ process_file_atomic 检测到冲突，自动加 _1
→ 实际生成:
   ABF-139.mp4    (100 字节)   ← 旧的，留下没动
   ABF-139_1.jpg  (633 字节)   ← 新图片
   ABF-139_1.mp4  (1MB)        ← 新视频（1MB 完整）
```

**场景 B：源视频本身就是 100 字节占位**
```
→ 正常处理，不触发 _1
→ 生成:
   ABF-139.jpg  (633 字节)
   ABF-139.mp4  (100 字节)   ← 因为源文件就是 100 字节
```

### 根因分析

**不是 bug** — atomic_processor 的去重逻辑 (`atomic_processor_v11.py:135`) 设计正确：

```python
while os.path.exists(new_video_path):
    name, ext = os.path.splitext(base_new_path)
    new_video_path = f"{name}_{counter}{ext}"   # 加 _1
    counter += 1
```

避免数据丢失的正确行为。问题是：

1. **atomic_processor 完全没打日志**告诉上层"我加了 _1"
2. **上层 GUI 也不知道发生了什么** — 用户看 Finish 里有 `ABF-139.mp4` 和 `ABF-139_1.mp4` 两个，不知道哪个是新的
3. 实际触发场景：用户**多次运行软件处理同一目录**（GUI 重启 / 拖错文件 / 部分文件上次失败这次重跑），atomic_processor 为不丢数据而加 _1

### 为什么"占位视频看起来很小"

用户的"小占位"是**上一次处理留下的旧文件**（比如上次中断 / 上次源文件就是 100 字节 / 上次只下了一半）。新的完整视频被命名为 `_1` 留下来跟它并存。

### 建议（未实施，用户选择不动）

如果以后想改，最小改动是：
```python
# atomic_processor_v11.py 第 135 行附近
if counter > 1:
    # 已经在循环里加过 _1
    print(f"⚠️ {base_new_path} 已存在，新文件命名为 {os.path.basename(new_video_path)}")
```

但 atomic_processor 不依赖 `self.log()`（它是独立模块），要么 print，要么通过回调通知上层。**架构上是 atomic_processor 应该接受一个 `notify` 回调而不是 print。**

### 为什么不修

用户决定先不动，记一笔现象 + 复现脚本留底。

### 复现脚本保留

`test_repro_duplicate.py` 留在仓库里，将来如果想批量清理"占位 + _1"残留，可以基于这个脚本扩展。


---

**修复人员**：Claude (Hermes Agent)
**修复日期**：2026-07-03
**版本**：v1.4.4-Selenium
