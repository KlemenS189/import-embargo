from tests.test_structure.module_f.private_service import dont_touch
from tests.test_structure.module_f.private_submodule_f.utils import calculate_fee


def give_me_moneyz():
    calculate_fee()
    dont_touch()
    pass
