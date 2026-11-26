# SeeU Windows 版 · 认字:调 Windows 自带的文字识别(Windows.Media.Ocr,系统自带,不用装东西)。
#   ocr.ps1 <png 路径> [语言,如 zh-Hans]     输出一行 JSON:{lang, lines:[{text, x, y, w, h}]}(像素坐标,相对图片左上角)
#   ocr.ps1 -List                           列出能用的识别语言
param([string]$Path = "", [string]$Lang = "", [switch]$List)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
    if (-not $task.Wait(20000)) { throw "超时" }      # 硬上限 20 秒
    $task.Result
}
if ($List) {
    $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }
    ConvertTo-Json -Compress @{ langs = @($langs) }
    exit 0
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
if ($Lang) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang)) }
else { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { ConvertTo-Json -Compress @{ error = "no_engine" }; exit 0 }
$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
$lines = @()
function Seg($words) {
    $x1 = 1e9; $y1 = 1e9; $x2 = 0; $y2 = 0
    foreach ($w in $words) { $r = $w.BoundingRect
        $x1 = [Math]::Min($x1, $r.X); $y1 = [Math]::Min($y1, $r.Y); $x2 = [Math]::Max($x2, $r.X + $r.Width); $y2 = [Math]::Max($y2, $r.Y + $r.Height) }
    return ,@{ text = (($words | % { $_.Text }) -join " "); x = [int]$x1; y = [int]$y1; w = [int]($x2 - $x1); h = [int]($y2 - $y1) }
}
# 同一行里两个词隔得比字高还远(如菜单「文件」「编辑」被认成一行)就拆成两项,按名字点才点得准
foreach ($l in $res.Lines) {
    $hmax = 0; foreach ($w in $l.Words) { $hmax = [Math]::Max($hmax, $w.BoundingRect.Height) }
    $seg = @(); $prev = $null
    foreach ($w in $l.Words) { $r = $w.BoundingRect
        if ($prev -ne $null -and ($r.X - $prev) -gt [Math]::Max(8, $hmax * 1.2)) {
            $lines += Seg $seg; $seg = @() }
        $seg += $w; $prev = $r.X + $r.Width }
    if ($seg.Count) { $lines += Seg $seg }
}
$stream.Dispose()
ConvertTo-Json -Compress -Depth 4 @{ lang = $engine.RecognizerLanguage.LanguageTag; lines = @($lines) }
