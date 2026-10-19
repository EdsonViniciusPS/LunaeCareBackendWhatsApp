from app.core.security import create_access_token


def auth(clinic_id: str, user_id: str = "user_1", **kwargs) -> dict:
    token = create_access_token(clinic_id=clinic_id, user_id=user_id, **kwargs)
    return {"Authorization": f"Bearer {token}"}
