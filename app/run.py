# -*- coding: utf-8 -*-
"""run.py — 兼容入口：直接调用 main.main()

用法与重构前一致：
  python run.py                     # 全流程: 同步原始周报 → 抓取 → 计算 → 六列写回飞书
  python run.py --limit 5           # 每表前 5 行(自动 dry-run, 不写飞书)
  python run.py --no-headless       # 显示浏览器
  python run.py --fetch-only        # 同步+抓取，不写六列
  python run.py --push-only         # 用最近快照缓存推送
  python run.py --dry-run           # 只读+计算+本地输出
  python run.py --migrate-feishu-columns --confirm   # 一次性旧列清理+六列表头
"""
from main import main

if __name__ == '__main__':
    main()
