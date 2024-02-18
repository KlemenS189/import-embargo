from tests.test_structure.module_a.service import is_weather_nice_today
from tests.test_structure.module_a.submodule_a.service import create_user


def orchestrator():
    weather_status = is_weather_nice_today()
    user = create_user()
