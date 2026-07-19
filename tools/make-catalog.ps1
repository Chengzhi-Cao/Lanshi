$ErrorActionPreference = "Stop"

$SiteRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$MediaRoot = Resolve-Path (Join-Path $SiteRoot "..")
$VideoExtensions = @(".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mpg", ".mpeg")
$SeriesPatterns = @(
  "Black Bird",
  "Blackbird",
  "Darkwing",
  "Dark Wondra",
  "DarkWondra",
  "Dark Canary",
  "Dark Widow",
  "Catwarrior",
  "Supernova",
  "Ultrawoman",
  "WhiteAngel",
  "White Angel",
  "Wondra",
  "Wonderkick",
  "TeenBat",
  "TeenWing",
  "Sexy Spies",
  "Scotland Yard",
  "SYCC",
  "UKSG",
  "Athena",
  "Spider Warrior",
  "Sierra Skye"
)

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

function Get-CleanTitle([string]$Stem) {
  $title = $Stem -replace "[_+]+", " "
  $title = $title -replace "\b20\d{10,14}\b", ""
  $title = $title -replace "(?i)AAAA+\b", ""
  $title = $title -replace "\s+", " "
  $title = $title.Trim(" -_.")
  if ([string]::IsNullOrWhiteSpace($title)) { return $Stem }
  return $title
}

function Get-Series([string]$Title) {
  $normalized = $Title -replace "_", " "
  foreach ($pattern in $SeriesPatterns) {
    if ($normalized.ToLower().Contains($pattern.ToLower())) {
      if ($pattern -eq "DarkWondra") { return "Dark Wondra" }
      if ($pattern -eq "WhiteAngel") { return "White Angel" }
      return $pattern
    }
  }
  $parts = $normalized -split "\s+"
  if ($parts.Length -gt 0 -and $parts[0]) { return $parts[0] }
  return "Other"
}

function Get-SizeLabel([int64]$Size) {
  if ($Size -ge 1GB) { return "{0:N1} GB" -f ($Size / 1GB) }
  return "{0:N0} MB" -f ($Size / 1MB)
}

function Get-PriceCents([int64]$Size) {
  return 100
}

$videos = Get-ChildItem -LiteralPath $MediaRoot -File |
  Where-Object { $VideoExtensions -contains $_.Extension.ToLower() } |
  ForEach-Object {
    $id = Get-VideoId $_.Name
    $title = Get-CleanTitle $_.BaseName
    $price = Get-PriceCents $_.Length
    [PSCustomObject]@{
      id = $id
      title = $title
      fileName = $_.Name
      series = Get-Series $title
      size = $_.Length
      sizeLabel = Get-SizeLabel $_.Length
      priceCents = $price
      priceLabel = ("{0}{1:N2}" -f [char]0x00A5, ($price / 100))
      updatedAt = [int64]([DateTimeOffset]$_.LastWriteTime).ToUnixTimeSeconds()
      thumb = "./thumbs/$id.jpg"
      ext = $_.Extension.ToLower()
    }
  } |
  Sort-Object @{Expression = { $_.series.ToLower() }}, @{Expression = { $_.title.ToLower() }}

$json = $videos | ConvertTo-Json -Depth 4
$content = "window.VIDEO_CATALOG = $json;`n"
Set-Content -LiteralPath (Join-Path $SiteRoot "catalog.js") -Value $content -Encoding UTF8
Write-Host "Generated catalog.js with $($videos.Count) videos."
