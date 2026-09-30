# -*- coding: utf-8 -*-
"""
gpk_dump.py —— 解开 Myth.Cool 皮肤安装包 (.gpk)，导出其中的原始素材。

用途：不解包就只能看现象；解包后能直接知道「这个皮肤的底层到底是什么」
（GIF 动图？CSS 动画？多大的素材？），是排查闪屏 / 定位动态来源最直接的一步。

背景与结论见 docs/05-闪黑排查.md §4.4.1。

.gpk 格式（实测，见下）
--------------------------------------------------
    [1 字节 0x00 或其它前缀字节][JSON 目录][数据区]

    - JSON 目录起点 = 文件里第一个 b'{"files"' 的位置
    - JSON 结构是一棵 {"files": {...}} 的树，叶子节点形如
          {"size": N, "zipped": 0|1, "offset": "<相对数据区起点的偏移>"}
    - 数据区起点 = JSON 结束位置 + 1（实测偏移 1 字节，用 GIF/PNG magic 校验）
    - zipped=1 的文件其压缩方式为**私有格式**（头部 magic 0xcda6e0a0），
      本工具不尝试解，只提示「该文件已压缩」，不影响 CSS/图片的导出

用法
--------------------------------------------------
    python gpk_dump.py --list  <xxx.gpk>              # 只列清单，不导出
    python gpk_dump.py --dump  <xxx.gpk> -o <目录>     # 导出全部资源
    python gpk_dump.py --find  <xxx.gpk>               # 找本机所有皮肤包并列出

不带参数时按 --find 处理。

皮肤包默认位置：
    %LOCALAPPDATA%\\MythCool\\Apps\\<应用id>\\<版本>\\dial<编号>.gpk
其中 dial<编号> 的编号与官方皮肤编号对应（如 dial31 = AeeBiCui「博物馆1」）。
"""
import argparse
import json
import os
import struct
import sys

MAGIC_JSON = b'{"files"'


def _json_tree(data):
    """定位并解析 gpk 头部的 JSON 目录，返回 (dir_json, 数据区起点)。"""
    s = data.find(MAGIC_JSON)
    if s < 0:
        raise ValueError('没找到 JSON 目录（不是 .gpk？）')
    depth = 0
    end = None
    for i in range(s, len(data)):
        c = data[i]
        if c == 0x7B:        # {
            depth += 1
        elif c == 0x7D:      # }
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError('JSON 目录没有正常闭合')
    d = json.loads(data[s:end].decode('utf-8', errors='replace'))
    # 数据区起点 = JSON 尾 + 1（实测偏差 1 字节，下面会做 magic 校验）
    base = end + 1
    return d, base


def _walk(node, path=''):
    """把 {"files":{...}} 树拍平成 [(路径, 叶子信息), ...]。"""
    out = []
    if isinstance(node, dict) and 'files' in node:
        for k, v in node['files'].items():
            out.extend(_walk(v, path + '/' + k))
    else:
        out.append((path, node))
    return out


def _check_base(data, base, leaves):
    """用已知文件头 magic 校验数据区起点；不对就 ±几字节试一遍。"""
    probes = []
    for _p, v in leaves:
        try:
            off = int(v.get('offset', 0))
        except (TypeError, ValueError):
            continue
        probes.append(off)
        if len(probes) >= 3:
            break
    if not probes:
        return base
    magics = (b'GIF8', b'\x89PNG', b'RIFF', b'\xff\xd8\xff', b'WEBP', b'<', b'{', b'@')
    for delta in (0, 1, -1, 2, -2, 3, -3, 4):
        cand = base + delta
        ok = 0
        for off in probes:
            chunk = data[cand + off:cand + off + 8]
            if any(chunk.startswith(m) for m in magics):
                ok += 1
        if ok == len(probes):
            return cand
    return base


def _kind(name):
    n = name.lower()
    if n.endswith('.gif'):
        return 'GIF 动图'
    if n.endswith('.png'):
        return 'PNG 图'
    if n.endswith('.webp'):
        return 'WebP 图'
    if n.endswith('.jpg') or n.endswith('.jpeg'):
        return 'JPEG 图'
    if n.endswith('.css'):
        return 'CSS'
    if n.endswith('.js'):
        return 'JS'
    if n.endswith('.html'):
        return 'HTML'
    if n.endswith('.ttf') or n.endswith('.woff') or n.endswith('.woff2'):
        return '字体'
    return ''


def _gif_frames(blob):
    """粗略数 GIF 帧数与单帧延时（用于判断「多少 fps 的持续动画」）。"""
    if not blob.startswith(b'GIF8'):
        return None
    try:
        flags = blob[10]
        i = 13
        if flags & 0x80:
            i += 3 * (2 ** ((flags & 0x07) + 1))
        frames = 0
        delays = []
        while i < len(blob):
            b = blob[i]
            if b == 0x21:                       # extension
                label = blob[i + 1]
                if label == 0xF9 and i + 6 <= len(blob):   # Graphic Control
                    bs = blob[i + 2]
                    delays.append(struct.unpack('<H', blob[i + 4:i + 6])[0])
                    i += 2 + bs + 1
                else:
                    i += 2
                    while i < len(blob) and blob[i] != 0:
                        i += 1 + blob[i]
                    i += 1
            elif b == 0x2C:                     # image descriptor
                frames += 1
                i += 10
                lf = blob[i - 1]
                if lf & 0x80:
                    i += 3 * (2 ** ((lf & 0x07) + 1))
                i += 1
                while i < len(blob) and blob[i] != 0:
                    i += 1 + blob[i]
                i += 1
            elif b == 0x3B:                     # trailer
                break
            else:
                i += 1
        uniq = sorted(set(delays))
        return frames, uniq, sum(delays) * 10
    except Exception:
        return None


def load(fp):
    data = open(fp, 'rb').read()
    tree, base = _json_tree(data)
    leaves = _walk(tree)
    base = _check_base(data, base, leaves)
    return data, leaves, base


def cmd_list(fp):
    data, leaves, base = load(fp)
    print('文件      : %s' % fp)
    print('总大小    : %.2f MB' % (len(data) / 1048576.0))
    print('数据区起点: %d' % base)
    print('资源数    : %d' % len(leaves))
    print('-' * 78)
    for p, v in leaves:
        name = p.rsplit('/', 1)[-1]
        size = int(v.get('size', 0))
        zp = v.get('zipped', 0)
        kind = _kind(name)
        tag = ' [已压缩:私有格式,未导出]' if zp else ''
        print('  %-42s %10s  %-9s%s' % (name, size, kind, tag))
        if name.lower().endswith('.gif') and not zp:
            off = int(v['offset'])
            info = _gif_frames(data[base + off:base + off + size])
            if info:
                n, uniq, total = info
                fps = ''
                if len(uniq) == 1 and uniq[0]:
                    fps = '  ≈%.0f fps 持续循环' % (100.0 / uniq[0])
                print('       └ 帧数=%d  单帧延时=%s(centisec)  一轮=%dms%s'
                      % (n, uniq, total, fps))
    print('-' * 78)
    gifs = [p for p, v in leaves if p.lower().endswith('.gif') and not v.get('zipped')]
    if gifs:
        print('⚠ 该皮肤含 %d 个 GIF 动图 —— 它们由浏览器解码播放，'
              '不受 CSS animation:none 管辖。' % len(gifs))
    return 0


def cmd_dump(fp, outdir):
    data, leaves, base = load(fp)
    os.makedirs(outdir, exist_ok=True)
    n_ok = n_skip = 0
    for p, v in leaves:
        name = p.rsplit('/', 1)[-1]
        if v.get('zipped'):
            n_skip += 1
            print('  跳过(私有压缩) %s' % name)
            continue
        off = int(v['offset'])
        size = int(v['size'])
        blob = data[base + off:base + off + size]
        open(os.path.join(outdir, name), 'wb').write(blob)
        n_ok += 1
        extra = ''
        if name.lower().endswith('.gif'):
            info = _gif_frames(blob)
            if info:
                extra = '  帧数=%d 一轮=%dms' % (info[0], info[2])
        print('  导出 %-42s %9d%s' % (name, len(blob), extra))
    print('-' * 78)
    print('完成：导出 %d 个，跳过 %d 个（私有压缩格式）→ %s' % (n_ok, n_skip, outdir))
    return 0


def cmd_find():
    root = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'MythCool', 'Apps')
    if not os.path.isdir(root):
        print('没找到 %s —— Myth.Cool 装了没？' % root)
        return 1
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith('.gpk'):
                found.append(os.path.join(dirpath, f))
    if not found:
        print('%s 下没有 .gpk' % root)
        return 1
    print('本机皮肤/应用包（共 %d 个）：' % len(found))
    print('-' * 78)
    for fp in sorted(found):
        try:
            _d, leaves, _b = load(fp)
            size = os.path.getsize(fp)
            print('  %-14s %8.2f MB  %3d 个资源   %s'
                  % (os.path.basename(fp), size / 1048576.0, len(leaves),
                     os.path.dirname(fp)))
        except Exception as e:
            print('  %-14s 解析失败: %s' % (os.path.basename(fp), e))
    print('-' * 78)
    print('提示：dial<编号> 的编号对应官方皮肤编号。'
          '想导出某个皮肤的全部素材：')
    print('      python gpk_dump.py --dump "<上面的完整路径>" -o <目标目录>')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='解开 Myth.Cool 皮肤包 (.gpk)，查看/导出其中的原始素材')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--list', action='store_true', help='列出包内清单（默认动作）')
    g.add_argument('--dump', action='store_true', help='导出全部资源')
    g.add_argument('--find', action='store_true',
                   help='扫描本机所有 .gpk（不带参数时默认如此）')
    ap.add_argument('gpk', nargs='?', help='要处理的 .gpk 路径')
    ap.add_argument('-o', '--out', default=None, help='导出目录（--dump 用）')
    a = ap.parse_args()

    if a.find or not a.gpk:
        return cmd_find()
    if not os.path.isfile(a.gpk):
        print('文件不存在: %s' % a.gpk, file=sys.stderr)
        return 1
    if a.dump:
        out = a.out or (os.path.splitext(os.path.basename(a.gpk))[0] + '_dump')
        return cmd_dump(a.gpk, out)
    return cmd_list(a.gpk)


if __name__ == '__main__':
    sys.exit(main())
