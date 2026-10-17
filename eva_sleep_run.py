"""Запуск «сна» Евы (консолидация дневника) в окружении форка.

    eva --run-module eva_sleep_run                 # dry-run: показать план и результат
    eva --run-module eva_sleep_run --apply         # слить и записать
    eva --run-module eva_sleep_run --apply --max-merges 5

Сам скрипт — ~/eva-home/sleep.py; здесь только правильный sys.path и аргументы.
"""
import runpy
import sys

sys.path.insert(0, "/home/iizey/eva-home")
sys.argv = ["sleep.py", *[a for a in sys.argv[1:] if a.startswith("--") or a.isdigit()]]
runpy.run_path("/home/iizey/eva-home/sleep.py", run_name="__main__")
