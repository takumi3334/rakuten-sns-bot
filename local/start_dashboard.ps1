# ローカル専用ダッシュボードを開く(PowerShell用)。
#   powershell -ExecutionPolicy Bypass -File local\start_dashboard.ps1
# 自分のPC(127.0.0.1)からだけ見られる。止めるときは、開いた最小化ウィンドウを閉じる。
# 楽天アフィリエイトの実績CSVは local\affiliate\YYYY-MM.csv に置く(Gitには上がらない)。

$root = Split-Path -Parent $PSScriptRoot
$port = 8765

Start-Process -FilePath "py" -ArgumentList "-m", "http.server", $port, "--bind", "127.0.0.1", "--directory", $root -WindowStyle Minimized
Start-Sleep -Seconds 1
Start-Process "http://localhost:$port/local/dashboard.html"
