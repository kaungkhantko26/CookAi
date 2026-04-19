module.exports = {
  apps: [
    {
      name: "cookai-user-bot",
      script: "bot.py",
      interpreter: "./.venv/bin/python",
      cwd: "/root/telegram-chatbot",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "cookai-admin-bot",
      script: "admin_bot.py",
      interpreter: "./.venv/bin/python",
      cwd: "/root/telegram-chatbot",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "cookai-admin-dashboard",
      script: "dashboard.py",
      interpreter: "./.venv/bin/python",
      cwd: "/root/telegram-chatbot",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
