"""Read full sheet capacity in bounded ranges, preserving physical row positions."""
def read_rows(fc, token, sid, first='A', last='O', start=1, row_count=None):
    end = int(row_count or 2000)
    def col_number(name):
        value = 0
        for letter in name:
            value = value * 26 + ord(letter) - 64
        return value
    width = col_number(last) - col_number(first) + 1
    step = min(2000, max(1, 10000 // width)) if row_count else 2000
    rows = []
    for offset in range(start, end + 1, step):
        stop = min(end, offset + step - 1)
        chunk = fc.read_values(token, sid, f'{first}{offset}:{last}{stop}')
        if len(chunk) > stop - offset + 1:
            raise RuntimeError('飞书返回行数超过请求范围，禁止错位写入')
        rows.extend(chunk)
        if stop < end:
            rows.extend([[] for _ in range(stop - offset + 1 - len(chunk))])
    while rows and not any(value not in ('', None, []) for value in rows[-1]):
        rows.pop()
    return rows
