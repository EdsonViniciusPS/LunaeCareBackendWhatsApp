import re


def normalize_phone(raw_phone: str | None) -> str:
    """
    Forma canônica de telefone usada em todo o módulo: apenas dígitos.
    Ex.: '+55 (11) 99999-8888' -> '5511999998888'; '5511999998888@s.whatsapp.net' -> '5511999998888'.
    """
    if not raw_phone:
        return ""
    return re.sub(r"\D", "", str(raw_phone).split("@", 1)[0])
