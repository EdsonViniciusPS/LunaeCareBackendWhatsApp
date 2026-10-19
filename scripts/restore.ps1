# Script PowerShell para restauração de backup do PostgreSQL em ambiente Docker
param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [string]$ContainerName = "whatsapp-db",
    [string]$Database = "lunaecare_whatsapp",
    [string]$User = "lunae_user"
)

if (-not (Test-Path $BackupFile)) {
    Write-Host "Arquivo de backup não encontrado: $BackupFile" -ForegroundColor Red
    exit 1
}

Write-Host "Restaurando base $Database a partir de $BackupFile..." -ForegroundColor Yellow

if ($BackupFile.EndsWith(".gz")) {
    gzip -dc $BackupFile | docker exec -i $ContainerName psql -U $User -d $Database
} else {
    Get-Content $BackupFile | docker exec -i $ContainerName psql -U $User -d $Database
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Restauração concluída com sucesso!" -ForegroundColor Green
} else {
    Write-Host "Erro durante restauração do banco de dados." -ForegroundColor Red
}
