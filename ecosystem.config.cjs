module.exports = {
  apps: [{
    name: 'eve-api',
    // VBS wrapper: hides console on Windows while PM2 keeps supervising the process
    script: 'wscript.exe',
    args: '//nologo //B scripts\\start-eve-api-hidden.vbs',
    cwd: 'D:/app/eve',
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
