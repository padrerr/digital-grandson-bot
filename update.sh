#!/bin/bash
cd /root/digital-grandson-bot
git pull
systemctl restart dobrosmena
echo "Готово. Бот перезапущен."
