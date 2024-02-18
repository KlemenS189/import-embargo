from tests.test_structure.module_a.service import is_weather_nice_today
from tests.test_structure.module_a import service
from tests.test_structure.module_a.submodule_a.service import (
    create_user,
    get_user_by_id,
)


def orchestrator():
    weather_status = is_weather_nice_today()
    user = create_user()
    found_user = service.get_user_by_id()
