# -*- coding: utf-8 -*-
"""run.py — 兼容入口：直接调用 main.main()

正式入口必须明确选择周报流程，禁止无参数误入旧六列流程：
  python app/run.py --weekly-run --confirm
  python app/run.py --weekly-run --dry-run --limit 1
  python app/run.py --weekly-push-only --run-id RUN_ID --confirm
"""
from main import main

if __name__ == '__main__':
    main()
