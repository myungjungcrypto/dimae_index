module.exports = {
  apps: [
    {
      name: "dimae-index-dashboard",
      cwd: __dirname,
      script: "python3",
      args: "-m sentiment_index.cli dashboard --host 0.0.0.0 --port 8765",
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
    },
    {
      name: "dimae-index-hourly-update",
      cwd: __dirname,
      script: "python3",
      args: "-m sentiment_index.cli schedule --hourly --timezone Asia/Seoul --verbose",
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
    },
  ],
};
