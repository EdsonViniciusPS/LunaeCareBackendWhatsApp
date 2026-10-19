import logging
import re

SENSITIVE_PATTERNS = [
    (re.compile(r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+"), "[QR_CODE_MASKED]"),
    (re.compile(r"Bearer\s+ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"), "Bearer [JWT_MASKED]"),
    (re.compile(r"apikey['\":\s]+[A-Za-z0-9_-]{20,}"), "apikey: [API_KEY_MASKED]"),
    (re.compile(r"password['\":\s]+[A-Za-z0-9_!@#$%^&*()-+=]+"), "password: [PASSWORD_MASKED]"),
]


class SensitiveDataSanitizerFilter(logging.Filter):
    """
    Filtro de segurança e LGPD que remove tokens, QR Codes e segredos de todos os logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in SENSITIVE_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

        if record.args:
            clean_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in SENSITIVE_PATTERNS:
                        arg = pattern.sub(replacement, arg)
                clean_args.append(arg)
            record.args = tuple(clean_args)

        return True
