# 设置 PYTHONPATH 环境变量（用于模块导入路径）
$env:PYTHONPATH = ".\;.\packages\sekaibot-adapter-cqhttp;.\packages\sekaibot-adapter-onebot;.\packages\sekaibot-plugin-apscheduler"

# 设置开发模式标志
$env:SEKAIBOT_DEV = "1"

# 执行指定 Python 文件
& "d:/QQBot/chatbot/.conda/Scripts/python.exe" "d:/QQBot/chatbot/example/main.py"

# 等待按键防止窗口关闭
Read-Host "Press Enter to exit"
