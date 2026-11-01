#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板匹配：补 OCR 认不出图标的短板（分享图标、×、返回箭头、星标…）。
只返回坐标文本，不占图片上下文。

用法:
    python3 match.py <截图>                      # 匹配 tpl/ 目录下全部模板
    python3 match.py <截图> tpl/share.png ...    # 只匹配指定模板
    python3 match.py <截图> --thr 0.75           # 自定义阈值(默认 0.80)
    python3 match.py <截图> --all                # 同一模板返回多个命中

输出每行:  <中心x>,<中心y>  <置信度>  <模板名>
坐标是设备像素。
"""
import sys, os, glob
import cv2
import numpy as np

# 模板目录属于各项目,不放共享库:命令行默认用"当前工作目录/tpl",
# 项目里的兼容文件 match.py 会把它自己旁边的 tpl/ 传进 main(tpldir=...)。

def find(img, tpl_path, thr=0.80, multi=False):
    tpl = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
    if tpl is None:
        return []
    th, tw = tpl.shape[:2]
    if th > img.shape[0] or tw > img.shape[1]:
        return []
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    hits = []
    if multi:
        ys, xs = np.where(res >= thr)
        cand = sorted(zip(res[ys, xs], xs, ys), reverse=True)
        for score, x, y in cand:
            c = (x + tw // 2, y + th // 2)
            # 非极大值抑制：与已选中心距离小于模板半径的丢弃
            if any(abs(c[0]-h[0]) < tw*0.6 and abs(c[1]-h[1]) < th*0.6 for h in hits):
                continue
            hits.append((c[0], c[1], float(score)))
    else:
        _, mx, _, mloc = cv2.minMaxLoc(res)
        if mx >= thr:
            hits.append((mloc[0] + tw // 2, mloc[1] + th // 2, float(mx)))
    return hits

def main(argv=None, tpldir=None):
    args = list(sys.argv[1:] if argv is None else argv)
    tpldir = tpldir or os.path.join(os.getcwd(), 'tpl')
    if not args:
        raise SystemExit(__doc__)
    thr = 0.80
    if '--thr' in args:
        i = args.index('--thr'); thr = float(args[i+1]); del args[i:i+2]
    multi = '--all' in args
    args = [a for a in args if a != '--all']

    shot = args[0]
    img = cv2.imread(shot, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f'读不到截图: {shot}')

    tpls = args[1:] or sorted(glob.glob(os.path.join(tpldir, '*.png')))
    if not tpls:
        raise SystemExit(f'没有模板。把图标裁成 png 放进 {tpldir}/')

    any_hit = False
    for t in tpls:
        for x, y, s in find(img, t, thr, multi):
            print(f"{x},{y}\t{s:.3f}\t{os.path.splitext(os.path.basename(t))[0]}")
            any_hit = True
    if not any_hit:
        print(f"(无命中, 阈值 {thr})", file=sys.stderr)


if __name__ == '__main__':
    main()
