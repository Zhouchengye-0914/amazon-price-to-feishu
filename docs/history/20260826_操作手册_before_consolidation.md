# 文档已整合

价格任务独立于HTML：Windows入口不启动HTML服务，正式全量和缓存恢复都不下载HTML、不检查HTML端口或文件。新登记序号只新增原始周报快照，结果始终使用同一个固定链接`https://wit0jhu6kvu.feishu.cn/sheets/Epads8MQkhkuBctjl3lcqLUvnCg`；只更新内容和表名，权限不变，不重新授权协作者。相同序号不要覆盖源URL，应新增登记行。

交付先落盘`outputs/daily_runs/{日期}/{run_id}_weekly_bundle.json`，每段写入后回读才计成功；失败范围和改名异常见同目录`{run_id}_delivery.json`。同周阻断行可能保留旧价格，要看时间戳；换周新ASIN没有有效价格时显示空结果，不套用旧ASIN的价格。换周抓取期间固定表不变，发布时直接替换完整行块而非先清空。已有Sheet ID保留，不删除现有子表；同批重试保留首次`target_backups/{run_id}/`备份。`outputs/weekly_runs/fixed_result.json`须随manifest备份，不可丢失或随意改Token。锁标记文件可长期存在，不要据此手动删除；实际互斥由操作系统锁决定。

2026-08-26最终调度：每周一至周五07:30、15:30（北京时间）每天两次，无截止日期，周末不触发。`AmazonDaily_0730`和`AmazonDaily_1530`均已启用；下次分别是2026-08-27 07:30、2026-08-26 15:30，未启动即时补跑。电脑须开机且Administrator保持登录，无需打开GPT界面。安装脚本同样保留两个工作日任务。两个时段均写同一固定结果表，N币种、O Amazon链接、旧P清空；HTML下载独立关闭，不删除本地文件。下文七天窗口及此前仅下午的描述均为历史记录，以本段为准。

完成消息使用分段富文本和具名链接，不含模拟提示；本地数据路径只发周成业，其他协作者不显示此行。权限由现有`feishu_manager_open_id`确定，缺失时默认隐藏路径。手工重发须使用实际完成记录，不将模拟数据作为正式结果发送。

部署、运行命令、计划任务、产物目录和故障处理已统一迁移到 [`SPEC.md`](SPEC.md) 第 18～19 节。

2026-08-26起下一次正式写入改用A:O（N币种、O Amazon链接，无HTML列），旧布局先备份再迁移；表名写入后同步run_id。通知名单来自应用collaborators而非文档分享列表，逐人送达记录位于`outputs/daily_runs/{日期}/{run_id}_notifications.json`。错误230013需管理员处理应用可用范围并发布，程序不自动扩权。下文历史PoC的A:P示例不代表新布局，规则以SPEC第1节为准。

R1.2 完整副本验证命令：`python app/run.py --create-snapshot-poc --confirm`。该命令只允许创建或找回名称以 `TEST_周报完整快照_` 开头的 PoC 副本；原周报只读，结构校验失败时禁止进入 Amazon 抓取。副本异步未就绪时会有限轮询，不应手工重复执行复制；本地状态见 `outputs/poc_resources/r1_2_snapshot_pending.json`。

R1.3 独立结果表验证命令：`python app/run.py --create-result-poc --confirm`。该命令只创建或找回名称以 `TEST_独立结果表_` 开头的工作簿，并仅在 `TEST_RESULT!A2:P2` 初始化固定 16 列表头；不得把参考表、原周报或完整快照副本作为写入目标。本地状态见 `outputs/poc_resources/r1_3_result_spreadsheet.json`。

正式新周初始化使用 `python app/run.py --new-week --confirm`。同一登记周期重复运行会只读校验并复用 `outputs/weekly_runs/{period_id}/weekly_manifest.json` 中的快照和独立结果表；出现“已有初始化任务运行中”时不得删除锁后并行重试，应先确认另一进程是否仍在运行。只有明确需要新一代资源时才使用 `--recreate-weekly-assets --confirm`，旧 generation 会保留在 manifest history，云端资源不会自动删除。

每周正式资源初始化后运行 `python app/main.py --discover-weekly-mapping`。该命令只读扫描快照并写本地发现报告，不创建或修改飞书子表。业务命名的空模板仍会进入映射；含数据但无法识别 ASIN 表头、未知 Marketplace、结果名重名会阻断。当前报告路径为 `outputs/discovery/seq-2_sheet_mapping.json`；R1.13 创建正式结果子表前 `business_ready` 必须保持 false。

映射完成后运行 `python app/main.py --audit-product-links`。该命令只读生成标准 Amazon URL 报告；恶意域名、US/CA 跨站和疑似商品但 ASIN 无效会阻断，ASIN 列下方的普通业务标签只记录为跳过。当前报告为 `outputs/discovery/seq-2_product_links.json`。当前周 CPD 7表均有数据，必须先完成 CA 单 ASIN真实验证；最终页面跳到不同 ASIN 时以 `identity_mismatch` 阻断，不得把变体价格写给源 ASIN。

R1.7 单商品页面验证命令为 `python app/run.py --amazon-poc-marketplace US --amazon-poc-asin B0BN5CJFCX` 或将 Marketplace 改为 `CA`。两个参数必须同时提供；该命令只访问对应 Amazon 商品页并输出 `outputs/poc_resources/r1_7_{market}_{asin}.json`，不会写飞书、不会保存 HTML，也不会执行 R1.9 的归档后等待。CA 默认邮编为 `M5V 3A8`，页面证据应为 CAD；US 默认邮编为 90210，页面证据应为 USD。生产抓取保持每个 Marketplace 单活动 tab，并按 US、CA 分批执行。

R1.9 PoC 首次准备需在 Node.js 24+ 环境运行 `npm install --prefix tools/singlefile`，锁文件固定 `single-file-cli@2.1.3`。同 tab 归档命令为 `python app/html_poc.py --marketplace US --asin B0BN5CJFCX`（CA 同理）；断网验收使用 `python app/offline_verify.py <html路径> --asin <ASIN> --price <页面价格>`。PoC 产物只写 `outputs/poc_resources`，不写飞书；必须同时检查 `.html`、`.manifest.json` 和 `.offline.json`，不能仅看命令返回码。

MHTML 对照使用 `python app/mhtml_compare.py --marketplace US --asin B0BN5CJFCX`，CA 同理。命令在同一已加载 tab 内只导航一次，保留普通 `.html`、manifest 和 `.comparison.json`，临时 `.mhtml` 默认自动删除；仅排障时可加 `--keep-mhtml`。MHTML 不得写入 N 列，也不得作为普通 HTML 归档失败后的交付回退。

正式归档根目录由 `html_archive_root` 控制，当前为 `D:\projects\amazon_daily_structured_20260821\htmls`。程序只清理其直属、名称可解析为日期且早于五日窗口的目录；不要把其他业务文件放入日期目录。`html_min_free_gb=40` 不满足时归档应停止。当前仅完成存储模块和临时目录测试，尚未启用每日真实目录清理。

HTML归档通常应保持 `html_archive_enabled=true` 和 `html_archive_required=true`。但自2026-08-25起按用户明确交付决定临时暂停HTML下载，当前两个开关均为`false`；计划任务只抓价格/折扣并允许HTML链接列为空。恢复HTML前须同时恢复两个开关并先做最小子表验证。既有HTML文件不删除。

映射和链接审计通过后，运行 `python app/main.py --sync-weekly-result-base --confirm` 初始化本周独立结果表。命令固定从 manifest 的完整快照读取，先全量预检，再按映射创建或复用18个结果子表；每个子表写前备份到 `outputs/target_backups/{run_id}`，A2:P2 写固定表头，A3:G 权威同步，H:P 清空。成功后 manifest 才置 `business_ready=true`。重复 ASIN、快照映射漂移或目标 Token 不是独立结果表时禁止写入。当前正式结果表为 `https://wit0jhu6kvu.feishu.cn/sheets/UWLdsZzVrhh2pDtxrqvcjbyAnNf`。

`config/config.json`中的`feishu_manager_open_id`必须配置为本周文档人工管理员。`--new-week --confirm`在创建或复用完整快照及独立结果表时，会通过云文档权限API幂等授予该账号容器级`full_access`并写入manifest；任一授权失败都会阻断初始化。当前管理员为周成业（`ou_68e7d2af96255c1eeb1eea8021c80ea4`）。获得可管理权限后，可在文档右上角“分享/权限设置”管理协作者并处理阅读或编辑申请；企业级分享限制仍需在飞书管理后台审批或调整。

新的每日入口为 `python app/main.py --weekly-run`，只允许从当前 manifest 的完整快照读取并向独立结果表写 H:P；正式写入必须加 `--confirm`。最小只读实网验证可使用 `--weekly-run --sheets PD03 --limit 1 --force-fetch`，`--limit` 会自动启用 dry-run，因此只生成本地 HTML、缓存、CSV和摘要，不写飞书。旧默认 `full_flow` 和旧 `push-only` 仍属于兼容路径，在 R1.14 完成前不得用于正式周结果表。

恢复写入必须使用 `python app/main.py --weekly-push-only --run-id <weekly-run批次> --sheets <子表> --confirm`。该命令不抓取、不刷新A:G；会校验当前周期、固定快照、独立结果Token、缓存schema、每条run_id、HTML存在性和SHA-256，写前备份、写后回读H:P。禁止使用旧 `--push-only` 代替。飞书API回读URL时会返回富文本数组，程序按其中 `link` 验证真实URL。

每个 `weekly-run` 在 `outputs/daily_runs/<日期>/` 原子保存 `<run_id>_weekly_bundle.json`。bundle 是恢复写入的首选来源，必须包含同一批的成功、页面异常、技术失败和源数据无效结果；不得从不同缓存或不同run_id手工拼装。限定运行会在 `--limit/--asins` 生效后保存精确快照，使恢复签名与实际抓取行集一致。

全量运行出现少量归档阻断时，先保留原全量批次及已成功写入行，再使用 `--weekly-run --sheets <Sheet> --asins <失败ASIN列表> --force-fetch` 生成独立恢复批次；逐个完成断网HTML验收后，使用该恢复批次自己的 `run_id` 执行 `--weekly-push-only`。不得把恢复结果手工并回原bundle，也不得重新覆盖已成功归档文件。2026-08-24全量基准：主批次 `20260824_181228` 处理141行、耗时3827.687秒、生成133份HTML共3,204,368,773字节；8项恢复批次 `20260824_192207` 耗时238.562秒，最终飞书141行覆盖完成。

正式全量固定为一个 Chromium 浏览器进程、四个商品 Tab、四个 worker。不得误配为四个浏览器；每个 Tab 必须在对应 HTML 落盘校验和1～3秒等待完成后才归还。中断恢复使用明确的 `--run-id <原批次> --weekly-run --confirm`，不要依赖“最新批次”自动选择。

HTML局域网服务使用TCP 8765，根目录固定为项目 `htmls`。手动启动/健康检查分别运行 `bin\start_html_server.ps1` 和 `.venv\Scripts\python.exe app\html_server.py --status`；状态记录在 `outputs/html_server.json`。Windows登录任务名为 `AmazonDaily_HTML_Server`，防火墙规则名为 `AmazonDaily HTML LAN 8765`，仅允许Private网络。正式任务启动前健康检查失败会停止抓取并向周成业发送一次异常通知。访问Token属于运行状态，不应粘贴到公开文档。

飞书通知按完整正式批次汇总：只在最终完成/部分完成时发送一次；运行问题额外通知一次。中间子表、只读发现、审计、PoC和dry-run不通知。最终通知必须写清开始/结束时间、完整耗时、子表数、写入/阻断数、结果表、证据位置和HTML端口是否开放。

七天本机稳定性窗口为北京时间2026-08-25至2026-08-31，每日固定07:30、15:30两个计划时段。2026-08-25的07:30时段因安装计划时已过点，使用当天手动启动的正式全量批次`20260825_085431`作为该时段补跑；15:30起由Windows任务计划程序执行。安装命令为`bin\schedule.bat --install`，卸载命令为`bin\schedule.bat --remove`；任务名固定为`AmazonDaily_0730`和`AmazonDaily_1530`。任务直接调用`bin\scheduled_run.ps1`，不依赖Codex/ChatGPT界面；独占锁`outputs/weekly_scheduler.lock`用于防止批次重叠，调度器日志写入`outputs/scheduler_logs/`。当前任务以`Administrator`的“仅用户登录时运行”模式创建：GPT/Codex可以关闭，但电脑必须开机且该Windows用户保持登录；若需要注销后仍运行，必须另行配置任务凭证并重新完成浏览器、Secret和文件权限验证。两个Codex自动任务已暂停，七天窗口内禁止恢复或并行安装另一套调度器。计划任务只复用当前weekly manifest，不创建或重建周快照/结果表；每个时段必须产生新的run_id和HTML，不跨批复用。

一次性交付任务：`AmazonDaily_20260826_0700`，计划于2026-08-26 07:00执行`bin\scheduled_run.bat`，状态为Ready。该任务同样是“仅用户登录时运行”，电脑必须开机且Administrator保持登录；使用当前暂停HTML的配置。

本机现状的 `.env` 是目录，程序只兼容其中唯一固定文件 `.env/飞书凭证.txt`：第一非空行必须与非敏感配置的 App ID 一致，第二非空行为 Secret；不扫描其他文件。标准部署仍推荐根目录 `.env` 文件中的 `FS_APP_SECRET=...`，系统环境变量 `FS_APP_SECRET` 优先级最高。不得同时新增另一份 Secret 到 JSON、代码或文档。

本文件仅保留旧路径兼容，不再维护另一套操作说明；执行具体变更前请同时查看 [`TASKS.md`](TASKS.md)。
