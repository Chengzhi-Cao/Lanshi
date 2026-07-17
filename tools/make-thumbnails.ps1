param(
  [int]$Limit = 80
)

$ErrorActionPreference = "Continue"

$SiteRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$MediaRoot = Resolve-Path (Join-Path $SiteRoot "..")
$ThumbRoot = Join-Path $SiteRoot "thumbs"
$VideoExtensions = @(".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mpg", ".mpeg")

New-Item -ItemType Directory -Force -Path $ThumbRoot | Out-Null

$ffmpeg = $env:FFMPEG_PATH
if (-not $ffmpeg -or -not (Test-Path $ffmpeg)) {
  $command = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if ($command) { $ffmpeg = $command.Source }
}
if (-not $ffmpeg -or -not (Test-Path $ffmpeg)) {
  $known = "E:\Software\data\ChimeraX\ChimeraX\bin\ffmpeg.exe"
  if (Test-Path $known) { $ffmpeg = $known }
}
if (-not $ffmpeg -or -not (Test-Path $ffmpeg)) {
  Write-Host "FFmpeg not found. Thumbnails will show title placeholders."
  exit 0
}

function Get-VideoId([string]$Name) {
  $sha = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Name)
    $hashBytes = $sha.ComputeHash($bytes)
    return ([System.BitConverter]::ToString($hashBytes) -replace "-", "").ToLower().Substring(0, 16)
  }
  finally {
    $sha.Dispose()
  }
}

$files = Get-ChildItem -LiteralPath $MediaRoot -File |
  Where-Object { $VideoExtensions -contains $_.Extension.ToLower() } |
  Sort-Object Name

if ($Limit -gt 0) {
  $files = $files | Select-Object -First $Limit
}

$index = 0
foreach ($file in $files) {
  $index += 1
  $id = Get-VideoId $file.Name
  $thumb = Join-Path $ThumbRoot "$id.jpg"
  if (Test-Path $thumb) {
    Write-Host "[$index/$($files.Count)] exists $($file.Name)"
    continue
  }

  Write-Host "[$index/$($files.Count)] $($file.Name)"
  & $ffmpeg -y -hide_banner -loglevel error -ss 00:00:08 -i $file.FullName -frames:v 1 -vf "scale=640:-1" -q:v 5 $thumb
  if (-not (Test-Path $thumb)) {
    & $ffmpeg -y -hide_banner -loglevel error -ss 00:00:02 -i $file.FullName -frames:v 1 -vf "scale=640:-1" -q:v 5 $thumb
  }
}

Write-Host "Thumbnail generation done."
