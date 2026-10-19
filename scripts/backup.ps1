# Script PowerShell para backup do PostgreSQL em ambiente Docker
param (
    [string]$ContainerName = "whatsapp-db",
    [string]$Database = "lunaecare_whatsapp",
    [string]$User = "lunae_user",
    [string]$BackupDir = "backups"
)

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutputFile = "$BackupDir\backup_${Database}_${Timestamp}.sql.gz"

Write-Host "Iniciando backup da base $Database em $OutputFile..." -ForegroundColor Cyan

docker exec -t $ContainerName pg_dump -U $User -d $Database --clean --if-exists | gzip > $OutputFile

if ($LASTEXITCODE -eq 0) {
    Write-Host "Backup concluído com sucesso em $OutputFile!" -ForegroundColor Green
} else {
    Write-Host "Erro ao gerar backup." -ForegroundColor Red
}
