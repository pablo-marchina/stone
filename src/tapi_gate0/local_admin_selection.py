"""Select one existing enabled administrator without guessing credentials."""


def select_admin_login(admins):
    enabled = [row for row in admins if not row["disabled"]]
    if not enabled:
        raise ValueError("LOCAL_ADMIN_NOT_FOUND")
    if len(enabled) != 1:
        raise ValueError("LOCAL_ADMIN_SELECTION_AMBIGUOUS")
    if enabled[0]["temporarily_locked"]:
        raise ValueError("LOCAL_ADMIN_TEMPORARILY_LOCKED")
    return enabled[0]["login"]
