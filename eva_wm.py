"""Запуск сборки рабочей памяти Евы в окружении форка.

    eva --run-module eva_wm            # dry-run: показать, что получилось
    eva --run-module eva_wm --apply    # записать ~/eva-home/working_memory.md

Тонкая обёртка: сам скрипт лежит в её доме (~/eva-home/working_memory.py), а зависимости
(hermes_cli.config_effective, plugins.platforms.telegram.eva_gate) живут только в форке.
"""
import runpy
import sys

sys.path.insert(0, "/home/iizey/eva-home")
sys.argv = ["working_memory.py", *[a for a in sys.argv[1:] if a.startswith("--")]]
runpy.run_path("/home/iizey/eva-home/working_memory.py", run_name="__main__")
