// Template: Setup-EVEDeploy.ps1 replaces __EVE_ROOT__ with the project path
// and writes ecosystem.config.js (PM2 does not load .cjs reliably on Windows).
module.exports = {
  apps: [{
    name: 'eve-api',
    // VBS → pythonw → uvicorn (no console window on Windows)
    script: 'wscript.exe',
    args: '//nologo //B __EVE_ROOT__/scripts/start-eve-api-hidden.vbs',
    cwd: '__EVE_ROOT__',
    interpreter: 'none',
    windowsHide: true,
    env: {
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'UTF-8',
    },
    max_restarts: 10,
    restart_delay: 5000,
    autorestart: true,
  }],
};
