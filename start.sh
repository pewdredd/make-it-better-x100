#!/usr/bin/env bash
# Запускает оба прогона параллельно в фоне. Повторный запуск продолжает с последнего круга.
#   ./start.sh            - без картинок
#   ./start.sh --images   - с ключом OpenRouter из .env
cd "$(dirname "$0")"
mkdir -p logs
for m in sonnet opus; do
  nohup python3 run_rounds.py "$m" "$@" >> "logs/$m.out" 2>&1 &
  echo "$m запущен, лог: logs/$m.out"
done
