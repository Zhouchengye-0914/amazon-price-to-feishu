# Amazon Daily 纯净交付版

根目录只保留本说明和 `启动中心.bat`。

## 首次使用

1. 安装 Python 3.10+，勾选 `Add Python to PATH`。
2. 双击 `启动中心.bat`，选择“首次部署”。
3. 在 `config/config.json` 填写 `feishu_app_secret`。
4. 固定美国 VPN。
5. 再次打开启动中心，选择“部署验收”。
6. 先运行 PD03，确认后再执行全量任务。

详细说明见 `docs/操作手册.md` 和 `docs/当前业务规则.md`。

## 文件夹

- `app/`：正式程序。
- `config/`：配置和依赖清单。
- `bin/`：部署、运行、验收和计划任务脚本。
- `docs/`：交付文档。
- `tests/`：自动测试。
- `outputs/`：首次运行后自动生成的每日记录，不随交付包提供。
