# Dump Recycle Bin entries as TSV: name, original folder, deleted date, $R path, size.
# Read-only: never modifies the Recycle Bin.
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$shell = New-Object -ComObject Shell.Application
$bin = $shell.NameSpace(0xA)
foreach ($item in $bin.Items()) {
    $name = $item.Name
    $origin = $bin.GetDetailsOf($item, 1)
    $deleted = $bin.GetDetailsOf($item, 2)
    $size = 0
    try { $size = (Get-Item -LiteralPath $item.Path -Force).Length } catch { }
    Write-Output ($name + "`t" + $origin + "`t" + $deleted + "`t" + $item.Path + "`t" + $size)
}
