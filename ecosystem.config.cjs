module.exports = {
  apps: [{
    name: 'eve-api',
    script: '.venv/Scripts/python.exe',
    args: '-m uvicorn eve.api.main:app --host 127.0.0.1 --port 8001',
    cwd: 'D:/app/eve',
    interpreter: 'none',
    env: {
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'UTF-8',
    },
    max_restarts: 10,
    restart_delay: 5000,
    autorestart: true,
  }],
};
