"""Adaptive cooldown — dynamically adjust delay based on iteration duration."""


def calc_adaptive_cooldown(
    avg_duration: float,
    min_cooldown: int = 2,
    max_cooldown: int = 60,
) -> int:
    """Calculate adaptive cooldown based on iteration duration.

    Short iterations (< 30s) suggest fast cycles that may hit rate limits,
    so we apply longer cooldowns. Long iterations (> 5min) don't need
    significant cooldown since the iteration itself is slow.

    Returns cooldown in seconds (clamped to [min_cooldown, max_cooldown]).
    """
    if avg_duration <= 0:
        return min_cooldown
    if avg_duration >= 300:  # 5+ minutes
        return min_cooldown
    if avg_duration <= 5:  # Very fast — likely rate-limit sensitive
        return max_cooldown
    if avg_duration <= 15:
        return max_cooldown // 2
    # Linear interpolation between 15s and 300s
    ratio = (avg_duration - 15) / (300 - 15)
    cooldown = int(max_cooldown - ratio * (max_cooldown - min_cooldown))
    return max(min_cooldown, min(max_cooldown, cooldown))
