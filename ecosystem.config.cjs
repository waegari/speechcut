module.exports = {
  apps: [{
    name: 'eve-api',
    // launcher: hide console + spawn workers via pythonw.exe on Windows
    script: '.venv/Scripts/pythonw.exe',
    args: '-m eve.api.launcher',
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
