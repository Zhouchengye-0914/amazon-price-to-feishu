"""A durable newest-run identity, separate from the last published result pointer."""
import json
from runtime_state import atomic_json

def identity(manifest, run_id):
    return {'period_id': manifest['period_id'], 'run_id': run_id,
            'snapshot_token': manifest['snapshot']['spreadsheet_token'],
            'result_token': manifest['result']['spreadsheet_token']}

def claim_latest_run(store, manifest, run_id):
    atomic_json(store.root / 'latest_run.json', identity(manifest, run_id))

def assert_latest_run(store, manifest, run_id):
    path = store.root / 'latest_run.json'
    if not path.is_file():
        raise RuntimeError('缺少最新批次登记，禁止恢复旧结果；请启动新批次')
    if json.loads(path.read_text(encoding='utf-8')) != identity(manifest, run_id):
        raise RuntimeError('最新批次已变化，禁止旧周期或旧运行发布')
    current = store.load(manifest['period_id'])
    if not current or current.get('snapshot_run_id') != run_id or identity(current, run_id) != identity(manifest, run_id):
        raise RuntimeError('当前manifest已变化，禁止旧快照发布')
