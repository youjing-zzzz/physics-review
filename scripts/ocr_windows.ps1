# 用 Windows 自带 OCR 识别图片文字（无需下载任何模型）
#
# 用法：
#   powershell -File scripts/ocr_windows.ps1 -Path data/ocr-cache/<某目录>
#   powershell -File scripts/ocr_windows.ps1 -Path 某张图.jpg
#
# 输出：与图片同名的 .txt（UTF-8），另打印每张的字数与行数。
#
# 注意（踩过的坑）：
#   1) 本文件必须保存为 UTF-8 带 BOM，否则 PS 5.1 按 GBK 读会解析失败。
#   2) 不用 StorageFile.GetFileFromPathAsync：在受限进程里常被权限代理挡住，
#      改为自己开文件流 + AsRandomAccessStream，稳定得多。

param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$OutDir = ""
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]

function Await($op, $type) {
    try {
        $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
        $task.Wait(-1) | Out-Null
        return $task.Result
    } catch [System.AggregateException] {
        $inner = $_.Exception.Flatten().InnerExceptions[0]
        throw "WinRT 调用失败：$($inner.GetType().Name) - $($inner.Message)"
    }
}

$lang = New-Object Windows.Globalization.Language 'zh-Hans-CN'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) { throw "无法创建中文 OCR 引擎，请确认系统已安装简体中文语言包" }

$items = if (Test-Path $Path -PathType Container) {
    Get-ChildItem $Path -Include *.jpg, *.png -File -Recurse
} else {
    Get-Item $Path
}

foreach ($item in $items) {
    # 单张坏图不能让整批中断：真实照片里出现损坏/截断的 JPEG 很常见
    try {
        $fs = [IO.File]::OpenRead($item.FullName)
        try {
            $ras = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($fs)
            $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($ras)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        } finally {
            $fs.Dispose()
        }
    } catch {
        Write-Warning ("跳过无法识别的图片：{0}（{1}）" -f $item.Name, $_.Exception.Message)
        continue
    }

    $lines = foreach ($line in $result.Lines) { (($line.Words | ForEach-Object { $_.Text }) -join '') }
    $text = ($lines -join "`n") -replace ' +', ' '

    $target = if ($OutDir) {
        $d = New-Item -ItemType Directory -Force -Path $OutDir
        Join-Path $d.FullName ($item.BaseName + '.txt')
    } else {
        Join-Path $item.DirectoryName ($item.BaseName + '.txt')
    }
    [IO.File]::WriteAllText($target, $text, (New-Object Text.UTF8Encoding $false))

    $chars = ($text -replace '\s', '').Length
    Write-Host ("{0} -> {1} 字 / {2} 行" -f $item.Name, $chars, @($result.Lines).Count)
}
