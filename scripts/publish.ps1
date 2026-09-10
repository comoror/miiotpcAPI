# miiotpcApi 发布脚本
#
# 用法：
#   .\scripts\publish.ps1 -Test        # 发布到 TestPyPI（验证用）
#   .\scripts\publish.ps1              # 发布到正式 PyPI（不可撤销！）
#   .\scripts\publish.ps1 -Build -Test # 先构建再发 TestPyPI
#
# 前提：项目根目录的 .env 中已配置 UV_PUBLISH_TOKEN

param(
    [switch]$Test,
    [switch]$Build,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---- 读取 .env ----
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "错误：未找到 .env 文件" -ForegroundColor Red
    Write-Host "请在项目根目录创建 .env，内容为："
    Write-Host "  UV_PUBLISH_TOKEN=pypi-..."
    exit 1
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if ($key -and $val) {
            Set-Item -Path "env:$key" -Value $val
        }
    }
}

if (-not $env:UV_PUBLISH_TOKEN) {
    Write-Host "错误：.env 中未找到 UV_PUBLISH_TOKEN" -ForegroundColor Red
    exit 1
}
Write-Host "已加载发布令牌（前 12 位）: $($env:UV_PUBLISH_TOKEN.Substring(0, [Math]::Min(12, $env:UV_PUBLISH_TOKEN.Length)))..." -ForegroundColor DarkGray

# ---- 构建 ----
if ($Build -or -not (Test-Path 'dist')) {
    Write-Host "`n[1/2] 构建发行包..." -ForegroundColor Cyan
    uv build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "构建失败" -ForegroundColor Red
        exit 1
    }
}

$artifacts = Get-ChildItem dist -File -ErrorAction SilentlyContinue
if (-not $artifacts) {
    Write-Host "错误：dist/ 下没有构建产物，请先运行 uv build" -ForegroundColor Red
    exit 1
}

Write-Host "`n将发布以下文件：" -ForegroundColor Yellow
$artifacts | ForEach-Object { Write-Host "  - $($_.Name) ($([Math]::Round($_.Length/1KB,1)) KB)" }

# ---- 确认 ----
$target = if ($Test) { 'TestPyPI' } else { '正式 PyPI' }
if ($Test) {
    $url = 'https://test.pypi.org/legacy/'
} else {
    $url = $null
}

if (-not $Force) {
    Write-Host ""
    if ($Test) {
        Write-Host "目标：TestPyPI（测试环境，可随意覆盖）" -ForegroundColor Green
    } else {
        Write-Host "目标：正式 PyPI" -ForegroundColor Red
        Write-Host "注意：正式发布的版本号无法覆盖或删除，只能发新版本！" -ForegroundColor Red
    }
    $answer = Read-Host "确认发布到 $target？输入 yes 继续"
    if ($answer -ne 'yes') {
        Write-Host "已取消"
        exit 0
    }
}

# ---- 发布 ----
Write-Host "`n[2/2] 发布到 $target ..." -ForegroundColor Cyan
if ($url) {
    uv publish --publish-url $url dist/*
} else {
    uv publish dist/*
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n发布成功！" -ForegroundColor Green
    if ($Test) {
        Write-Host "验证安装："
        Write-Host "  uv tool install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple miiotpcApi"
    } else {
        Write-Host "项目主页：https://pypi.org/project/miiotpcApi/"
    }
} else {
    Write-Host "`n发布失败，退出码 $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
