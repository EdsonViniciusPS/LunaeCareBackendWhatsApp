import logging
import time
from collections import defaultdict
from typing import Optional
from fastapi import HTTPException, Request, Response, status
from redis import Redis

from app.core.config import settings
from app.core.tenancy import TenantContext

logger = logging.getLogger(__name__)

# Fallback em memória para ambientes sem Redis (ex: testes locais)
_in_memory_buckets = defaultdict(list)
_redis_offline_until = 0.0


class RateLimiter:
    """
    Controlador de taxa de requisições por clínica (Sliding Window).
    Protege a API contra abusos e previne banimento de contas WhatsApp por disparos em massa.
    """

    def __init__(self, times: int = 60, seconds: int = 60, key_prefix: str = "rate"):
        self.times = times
        self.seconds = seconds
        self.key_prefix = key_prefix
        self._redis_client: Optional[Redis] = None

    def _get_redis(self) -> Optional[Redis]:
        global _redis_offline_until
        now = time.time()
        if now < _redis_offline_until:
            return None
        try:
            if not self._redis_client:
                self._redis_client = Redis.from_url(
                    settings.REDIS_URL, socket_connect_timeout=0.1, socket_timeout=0.1
                )
            self._redis_client.ping()
            return self._redis_client
        except Exception:
            _redis_offline_until = now + 5.0
            return None

    async def __call__(self, request: Request, response: Response):
        # 1. Identifica a chave: prioriza clinic_id do tenant se autenticado, ou IP do cliente
        clinic_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from app.core.security import decode_access_token
                claims = decode_access_token(auth_header.split(" ", 1)[1])
                clinic_id = claims.get(settings.JWT_CLINIC_CLAIM)
            except Exception:
                pass

        key_id = f"clinic_{clinic_id}" if clinic_id else f"ip_{request.client.host if request.client else 'unknown'}"
        rate_key = f"{self.key_prefix}:{key_id}"
        now = time.time()

        r = self._get_redis()
        if r:
            # Implementação Redis Sliding Window com Sorted Set
            try:
                pipeline = r.pipeline()
                pipeline.zremrangebyscore(rate_key, 0, now - self.seconds)
                pipeline.zadd(rate_key, {str(now): now})
                pipeline.zcard(rate_key)
                pipeline.expire(rate_key, self.seconds)
                results = pipeline.execute()
                current_count = results[2]
                remaining = max(0, self.times - current_count)

                response.headers["X-RateLimit-Limit"] = str(self.times)
                response.headers["X-RateLimit-Remaining"] = str(remaining)

                if current_count > self.times:
                    retry_after = int(self.seconds)
                    response.headers["Retry-After"] = str(retry_after)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Limite de taxa de requisições excedido para esta clínica. Aguarde antes de tentar novamente.",
                        headers={"Retry-After": str(retry_after)}
                    )
                return
            except HTTPException:
                raise
            except Exception as exc:
                logger.debug("Redis rate limit fallback para memória: %s", exc)

        # Fallback local em memória (para testes e modo isolado)
        window_start = now - self.seconds
        timestamps = [ts for ts in _in_memory_buckets[rate_key] if ts > window_start]
        timestamps.append(now)
        _in_memory_buckets[rate_key] = timestamps

        remaining = max(0, self.times - len(timestamps))
        response.headers["X-RateLimit-Limit"] = str(self.times)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        if len(timestamps) > self.times:
            retry_after = int(self.seconds)
            response.headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de taxa de requisições excedido para esta clínica. Aguarde antes de tentar novamente.",
                headers={"Retry-After": str(retry_after)}
            )


# Limitadores pré-configurados
rate_limit_standard = RateLimiter(times=120, seconds=60, key_prefix="std")
rate_limit_messages = RateLimiter(times=40, seconds=60, key_prefix="msgs")  # Max 40 msgs/min por clínica
