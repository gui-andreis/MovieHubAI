"""Rate limit em memória (janela deslizante de 60s). Suficiente para 1 instância no Render."""
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit_per_minute: int, window_seconds: float = 60.0):
        self.limit = limit_per_minute
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> tuple[bool, int]:
        """Registra uma chamada. Retorna (permitido, segundos até liberar)."""
        if self.limit <= 0:
            return True, 0
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(1, int(self.window - (now - q[0])) + 1)
        q.append(now)
        if len(self._hits) > 20000:  # evita crescer sem limite
            for k in [k for k, v in self._hits.items() if not v][:10000]:
                self._hits.pop(k, None)
        return True, 0
