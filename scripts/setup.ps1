# One-shot setup for the Tekla machine. Safe to re-run.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

function Require($name, $hint) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "$name not found. $hint" }
    Write-Host "[ok] $name -> $($cmd.Source)"
    return $cmd
}

Require git 'Install Git for Windows: https://git-scm.com/downloads/win' | Out-Null
Require uv  'Install uv: https://docs.astral.sh/uv/getting-started/installation/' | Out-Null

# Hooks run `python`. The Microsoft Store alias is not a real interpreter.
$py = Require python 'Install Python 3.12 from python.org and tick "Add to PATH".'
if ($py.Source -like '*WindowsApps*') {
    throw 'python resolves to the Microsoft Store alias. Install Python from python.org, or disable the alias in Settings > Apps > App execution aliases.'
}

Write-Host '--- Python environment'
uv sync
uv run pre-commit install

Write-Host '--- Language servers for Claude Code plugins'
uv tool install pyright
if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    dotnet tool update --global csharp-ls
} else {
    Write-Warning 'dotnet not found: csharp-ls skipped (needed from Step 3).'
}

Write-Host '--- Claude Code plugins (project scope)'
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude plugin marketplace add anthropics/claude-plugins-official
    claude plugin marketplace add forrestchang/andrej-karpathy-skills
    claude plugin install andrej-karpathy-skills@karpathy-skills --scope project
    claude plugin install pyright-lsp@claude-plugins-official --scope project
    claude plugin install csharp-lsp@claude-plugins-official --scope project
} else {
    Write-Warning 'claude CLI not on PATH. Install the plugins from the desktop app: Code tab > + > Plugins > Add plugin (see README).'
}

Write-Host '--- Environment check'
uv run harness env-check
Write-Host 'Done. Open this folder in the Claude desktop app > Code tab > local session.'
