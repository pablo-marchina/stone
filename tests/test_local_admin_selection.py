import pytest
from tapi_gate0.local_admin_selection import select_admin_login


def admin(login="founder-login", disabled=False, locked=False):
    return {"login": login, "disabled": disabled, "temporarily_locked": locked}


def test_unique_admin():
    assert select_admin_login([admin()]) == "founder-login"
    assert select_admin_login([admin(), admin("disabled", disabled=True)]) == "founder-login"


@pytest.mark.parametrize("rows,code", [
    ([], "LOCAL_ADMIN_NOT_FOUND"),
    ([admin(disabled=True)], "LOCAL_ADMIN_NOT_FOUND"),
    ([admin(locked=True)], "LOCAL_ADMIN_TEMPORARILY_LOCKED"),
    ([admin(), admin("second")], "LOCAL_ADMIN_SELECTION_AMBIGUOUS"),
    ([admin(), admin("second", locked=True)], "LOCAL_ADMIN_SELECTION_AMBIGUOUS"),
])
def test_fails_closed(rows, code):
    with pytest.raises(ValueError, match=code):
        select_admin_login(rows)
