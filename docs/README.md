# PP 周报 · 亚马逊价格校验 + 飞书六列回写（每日任务版）

> 当前实施口径请先阅读 [`当前业务规则.md`](当前业务规则.md)。目录中的修改建议、评审意见和重构方案属于历史设计记录；与当前业务规则冲突时，不再作为实现依据。

> 每日自动抓取亚马逊价格 → 按四种折扣类型分类计算 → 固定六列写回飞书。

## 核心流程

```
飞书原始周报 ──读取/快照──> 目标表 A:G 刷新
                              │
                              └──实时 Amazon 抓取/计算──> 目标表 H:M
```

- **原始表**：`O1t1wJVlHiEbd1kLdj6cIr0KnIg`（只读，公式列）
- **目标表**：`JbiQwDZXeiJan0k8ydRczfWNnFc`（所有子表统一 A:M）
- 同步到目标表的数据与用于抓取的数据**来自同一快照**，保证口径一致。

## 固定六列（顺序不可改）

| # | 列名 | 示例 |
|---|------|------|
| 1 | 展示价格 | `59.99` |
| 2 | 折扣类型 | `原价调整` / `code` / `价格折扣` / `coupon` / `-` |
| 3 | 折扣值 | `25%`（百分比）或 `-10.00`（金额） |
| 4 | 最终价格 | `44.99` |
| 5 | 一致性检查 | `✅(+0.20)` / `❌(-0.75)` / `-` |
| 6 | 时间戳 | `2026-08-21 16:00:00` |

- 正常页面只允许四种类型；Page Not Found / 售罄 / 异常统一输出 `-`（异常原因在本地日志与 CSV 区分）。
- 一致性 = `|最终价格 − 目标成交价| ≤ price_tolerance`（默认 0.50），差值正负含义：正=更贵，负=更便宜。
- 所有金额用 `Decimal` + `ROUND_HALF_UP` 两位小数，禁止 float 参与计算。

## 四种类型计算口径

| 类型 | 折扣值 | 最终价格 |
|------|--------|----------|
| 原价调整 | 目标成交价 − 正常售价（金额） | = 展示价格 |
| code | 页面 Code 百分比，如 `30%` | 展示价格 × (1 − Code%) |
| 价格折扣 | 页面 Save%，如 `25%` | = 展示价格（**不重复扣减**） |
| coupon | 优先页面比例，只有金额时存金额 | Coupon 后最终价 > 展示价−Saving > 展示价×(1−%) |

类型按页面证据判定，优先级 `coupon > code > 价格折扣 > 原价调整`；周报类型只用于诊断预期是否匹配。

### 数据完整性保护

- **源数据无效行**（ASIN 合法但正常售价/目标成交价为空）：标记 `source_data_invalid`，不进入抓取、不参与一致性统计，日志按 Sheet 列出；六列写入 `-` 异常结果（防止目标表残留旧成功数据）。
- **目标成交价来源追踪**：`feishu_value` / `excel_cached_value` / `local_fallback`。上传 xlsx 的公式无缓存值时允许使用已验证的本地计算；只有目标价仍为 `missing` 才触发保护。
- 源表列布局（表头行、目标成交价在 K 还是 L 列）自动探测，不依赖固定列号。

## CLI

| 命令 | 说明 |
|------|------|
| `python run.py` | 全流程：同步周报 → 抓取 → 计算 → 六列写回 |
| `python run.py --sheets PD03` | 只处理 PD03 |
| `python run.py --asins B0...,B0...` | 只对指定 ASIN 在线抓取（自动 dry-run，四种类型专项测试） |
| `python run.py --limit 5` | 每表前 5 行（**自动 dry-run，不改飞书**） |
| `python run.py --no-headless` | 显示浏览器调试（默认无头） |
| `python run.py --force-fetch` | 忽略缓存重新抓取 |
| `python run.py --fetch-only` | 同步+抓取，不写六列 |
| `python run.py --push-only` | 用最近快照缓存推送，不抓取 |
| `python run.py --dry-run` | 读取+计算+本地输出，不改飞书 |
| `python run.py --resume` | 恢复最近有效的未完成批次（跨进程断点续跑） |
| `python run.py --run-id <id>` | 明确恢复指定批次（排错用） |
| `python run.py --force-push` | 异常比例超阈值时仍写入（人工确认后恢复推送） |

`--push-only` 必须使用已完成的实时抓取快照；它仍会先刷新 A:G，再写缓存中的 H:M，不会使用本地 HTML。

### 异常比例保护

技术异常（crawl_error/parse_error）占比超过 `max_error_ratio_for_push`（默认 10%）时，**本次不自动写入飞书六列**，只保留本地 CSV/缓存/证据，日志明确提示"本次未推送"。人工确认结果后可用 `--force-push` 或 `--push-only` 恢复推送。

## 🖥️ 换电脑部署

1. 拷贝整个 `amazon_daily` 文件夹到新电脑
2. 安装 **Python 3.10+**（勾选 Add to PATH）
3. 双击根目录 **启动中心.bat**，选择“首次部署”
4. 配置飞书：在 `config/config.json` 填 `feishu_app_secret`（或环境变量 `FS_APP_SECRET`）
5. 固定美国 VPN 后，从启动中心执行验收、PD03 或全量任务

## 统一飞书布局与推送顺序

所有子表固定为 A:M：A:G 是 7 个原始字段，H:M 是 6 个抓取结果字段；表头第 2 行、数据第 3 行起。每日运行严格执行：读取原始表、备份目标表、刷新 A:G、实时抓取、写入 H:M。旧结果区只在检测到完整六列表头时清理，备份保存在 `outputs\target_backups\`。

## 📁 目录说明

| 路径 | 说明 |
|------|------|
| `outputs\snapshots\{run_id}\` | 原始周报快照（每次运行先保存） |
| `outputs\fetch_cache\{run_id}\` | 抓取缓存（含指纹，跨快照不误用） |
| `outputs\csv\` | 本地完整诊断 CSV（比飞书多技术字段） |
| `outputs\debug\{run_id}\` | 异常页截图/HTML/诊断 JSON（保留 7 天） |
| `outputs\logs\` | 运行日志（保留 30 个） |
| `outputs\daily_runs\YYYY-MM-DD\` | 每次正式运行的 JSON 摘要 |
| `outputs\target_backups\{run_id}\` | 写入前的目标表备份 |

## ⚠️ 注意事项

1. **必须美国节点**：程序不做 IP 检测或切换，也不自动读取系统代理；请在运行前固定好美国 VPN。只有 `config/config.json` 明确填写 `proxy` 时才使用代理。
2. 缓存默认只复用**同一快照**；换新周报后旧缓存自动失效（指纹不符）。
3. 技术异常（captcha/超时/解析冲突）占比 > 10% 时，运行日志会告警，不要把结果直接当售罄。
4. 飞书两张表都要**共享给应用**（原始表只读、目标表可编辑），否则报 91403。
5. 若"浏览器起不来"：删除 `%LOCALAPPDATA%\Temp\DrissionPage` 后重试。
6. **并发模型**：单浏览器 + 多 tab（一个 ChromiumPage，每个线程持有一个独立标签页），`workers` 即 tab 并发数，实测 4 tab 稳定（4 个 ASIN 25s，无 `PageDisconnectedError`）。不要用多浏览器实例并发——DrissionPage 4.1.1.4 多实例会报 `PageDisconnectedError`。并发数过高可能触发 Amazon 风控（captcha 上升），默认 4 即可。
7. **源表类型**：原始周报 wiki 解析后可能是上传的 xlsx 文件（`obj_type=file`），程序会自动下载解析（公式读缓存值，缺失本地兜底）；目标表为云电子表格（`sheet`），走表格 API。
