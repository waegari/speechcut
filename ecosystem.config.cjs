// Setup-EVEDeploy.ps1 replaces __EVE_ROOT__ with the install path, then:
//   pm2 start ecosystem.config.cjs
module.exports = {
  apps: [{
    name: 'eve-api',
    // pythonw via .cmd — no console window, PM2-friendly on Windows
    script: '__EVE_ROOT__/scripts/start-eve-api.cmd',
    cwd: '__EVE_ROOT__',
    interpreter: 'none',
    windowsHide: true,
    env: {
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'UTF-8',
    },
    max_restarts: 5,
    min_uptime: 30000,
    restart_delay: 10000,
    exp_backoff_restart_delay: 100,
    autorestart: true,
  }],
};
