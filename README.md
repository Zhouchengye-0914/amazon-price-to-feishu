# Amazon Daily

当前正式入口、部署和运行命令见[docs/SPEC.md](docs/SPEC.md)第18～19节。目录及配置职责见第3～4节；实施状态见[docs/TASKS.md](docs/TASKS.md)，未解决问题见[docs/REVIEWS.md](docs/REVIEWS.md)。

启动中心选项3执行PD03单条只读验证，选项4执行正式周报全量；Windows工作日07:30/15:30也进入weekly-run。无参数及旧push-only拒绝执行，防止误入旧六列流程。真实在线验收边界见REVIEWS。

源码在app，配置与模板在config，脚本在bin，测试在tests；完整文档导航见[docs/README.md](docs/README.md)。

outputs不进入Git，但其中固定结果身份、周manifest、运行证据及写前备份必须保留并随部署迁移，不能作为普通缓存整体删除。Secret仅按SPEC指定来源注入，不复制成多份本地配置。

所有CLI与Windows调度共用运行锁；发布以latest_run登记和本批源指纹为准，旧批次不得覆盖新结果。v4不接受旧规则缓存恢复，需新建正式抓取批次。当前完整优化清单与离线验证范围见TASKS顶部，未完成的在线验收见REVIEWS。
