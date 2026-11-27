#!/usr/bin/env /usr/bin/python3
# -*- coding: utf-8 -*-
"""
本地 OCR：macOS Vision 框架，离线、免费、中文精度高。
只返回文本 + 设备坐标，不把图片塞进模型上下文。

用法:
    /usr/bin/python3 ocr.py <图片>                      # 全图
    /usr/bin/python3 ocr.py <图片> x0 y0 x1 y1          # 只识别裁剪区域
    /usr/bin/python3 ocr.py <图片> --json               # JSON 输出
    /usr/bin/python3 ocr.py <图片> x0 y0 x1 y1 --enhance [--invert]   # 增强认字(见 ocr_enhanced)

输出每行:  <中心x>,<中心y>  <文本>
坐标已换算回原图设备像素。
"""
import sys, json, objc
from Foundation import NSURL, NSBundle, NSArray, NSString

# lookUpClass 之前必须先把 framework 载进进程
for _fw in ('Vision', 'CoreImage'):
    _b = NSBundle.bundleWithPath_(f'/System/Library/Frameworks/{_fw}.framework')
    if _b is not None:
        _b.load()

VNRecognizeTextRequest = objc.lookUpClass('VNRecognizeTextRequest')
VNImageRequestHandler  = objc.lookUpClass('VNImageRequestHandler')
CIImage                = objc.lookUpClass('CIImage')

def ocr(path, box=None, langs=('zh-Hans', 'en')):
    img = CIImage.imageWithContentsOfURL_(NSURL.fileURLWithPath_(path))
    if img is None:
        raise SystemExit(f'读不到图片: {path}')
    ext = img.extent()
    W, H = ext.size.width, ext.size.height

    if box:
        x0, y0, x1, y1 = box
        img = img.imageByCroppingToRect_(((x0, H - y1), (x1 - x0, y1 - y0)))
        ox, oy = x0, y0
        w, h = x1 - x0, y1 - y0
    else:
        ox, oy = 0, 0
        w, h = W, H

    # 认完字马上退出的短命进程崩过一次(桌面弹「Python quit unexpectedly」)。
    # 原因:直接传 Python 列表,Vision 拿到的是 PyObjC 的代理数组(OC_PythonArray),
    # 它会在自己的后台队列里异步释放;那时主线程若已在收尾解释器,代理去拿 GIL → 线程被强退 → 崩。
    # 改法:传给 Vision 的数组都先转成纯 NSArray(不含 Python 对象),整段包在 autorelease 池里,
    # 临时代理当场在主线程释放;用完把 req/handler 引用丢掉。
    with objc.autorelease_pool():
        req = VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(0)          # 0 = accurate
        # 元素也要转成系统字符串:只转外层,里面的 str 仍是 Python 代理(SeeU 复查查出)
        req.setRecognitionLanguages_(NSArray.arrayWithArray_([NSString.stringWithString_(str(l)) for l in langs]))
        req.setUsesLanguageCorrection_(True)

        # 系统更新后(OS 25.6.0→27.0.0)传空字典 {} 会报
        # "NSInvalidArgumentException - key does not exist",改传 None 才行。
        handler = VNImageRequestHandler.alloc().initWithCIImage_options_(img, None)
        # 动态加载的 framework 没有方法签名元数据，error 不是 out 参数，只有一个返回值
        ok = handler.performRequests_error_(NSArray.arrayWithObject_(req), None)
        if not ok:
            raise SystemExit('识别失败')
        out = _collect(req, ox, oy, w, h)
        del req, handler, img
    return out


def _collect(req, ox, oy, w, h):
    out = []
    for obs in (req.results() or []):
        cands = obs.topCandidates_(1)
        if not cands:
            continue
        text = cands[0].string()
        conf = float(cands[0].confidence())
        bb = obs.boundingBox()            # 归一化，原点左下
        cx = ox + (bb.origin.x + bb.size.width  / 2) * w
        cy = oy + (1 - (bb.origin.y + bb.size.height / 2)) * h
        bw = bb.size.width * w             # 整条识别结果的像素宽度。
        # 用途:两个挨得很近的图标(比如并排的两个数字气泡)会被 Vision 合并识别成同一条
        # 文本(比如"3g4g"),原来只有中心点,拆不出各自坐标——加上宽度后,调用方可以
        # 按字符位置比例在这条 bbox 里插值出每个子匹配的大致 x,不用再猜。
        out.append({'text': text, 'x': round(cx), 'y': round(cy), 'w': round(bw, 1),
                    'conf': round(conf, 2)})
    out.sort(key=lambda d: (d['y'], d['x']))
    return out

def ocr_enhanced(path, box, invert=False, scale=3, cutoff=2, langs=('zh-Hans', 'en')):
    """整图认不出的半透明/压在光圈上的字的兜底:裁 box → 灰度 + 自动拉对比度(可反色)→ 放大 scale 倍 → OCR,
    坐标(含宽度 w)换算回原图。白字压浅色底一般要 invert=True。box 必填:只对小块区域用,整图放大太慢。"""
    import os, tempfile
    from PIL import Image, ImageOps
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    g = ImageOps.autocontrast(ImageOps.grayscale(Image.open(path).convert('RGB').crop((x0, y0, x1, y1))),
                              cutoff=cutoff)
    if invert:
        g = ImageOps.invert(g)
    g = g.resize(((x1 - x0) * scale, (y1 - y0) * scale))
    fd, tmp = tempfile.mkstemp(suffix='.png', prefix='ocr_enh_')
    os.close(fd)
    try:
        g.save(tmp)
        res = ocr(tmp, langs=langs)
    finally:
        os.remove(tmp)
    return [dict(e, x=x0 + round(e['x'] / scale), y=y0 + round(e['y'] / scale), w=round(e['w'] / scale, 1))
            for e in res]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    flags = {'--json', '--enhance', '--invert'}
    args = [a for a in argv if a not in flags]
    as_json = '--json' in argv
    if not args:
        raise SystemExit(__doc__)
    path = args[0]
    box = tuple(map(float, args[1:5])) if len(args) >= 5 else None
    if '--enhance' in argv:
        if not box:
            raise SystemExit('--enhance 要给区域 x0 y0 x1 y1')
        res = ocr_enhanced(path, box, invert='--invert' in argv)
    else:
        res = ocr(path, box)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print(f"{r['x']},{r['y']}\t{r['text']}")


if __name__ == '__main__':
    main()
