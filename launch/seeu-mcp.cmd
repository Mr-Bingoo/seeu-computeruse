@echo off
rem SeeU plugin launcher for Windows (Claude Code / Codex plugin): starts SeeU's MCP server with Python.
rem Uses the py launcher when present (python.org installs), otherwise python from PATH.
setlocal
set "SEEU_DIR=%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SEEU_DIR%\seeu\win\mcp_server.py" %*
) else (
  python "%SEEU_DIR%\seeu\win\mcp_server.py" %*
)
exit /b %errorlevel%
