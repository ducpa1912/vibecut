"""Story hook text scoring extracted from Studio's pipeline."""

from __future__ import annotations

import re

HOOK_WORDS = [
    "how", "why", "what", "secret", "never", "stop", "before", "after",
    "best", "worst", "mistake", "truth", "actually", "finally", "result",
    "changed", "you", "your", "did you know", "here's", "watch", "look",
    "wait", "number", "first", "last", "free", "easy", "fast", "only",
    "one thing", "nobody", "everyone", "should", "must", "need",
    "为什么", "怎么", "什么", "秘密", "千万", "不要", "一定", "最好",
    "第一", "最后", "结果", "竟然", "原来", "教你", "免费", "快速",
    "简单", "注意", "真的", "居然", "只要", "如何", "别再", "必看",
    "你", "我", "我们", "这件", "这个", "穿搭", "秋天",
]


def hook_text_score(text: str) -> float:
    if not text:
        return 0.0
    low = text.lower()
    hits = 0.0
    for word in HOOK_WORDS:
        if word in low:
            hits += 1.0
    if re.search(r"\d", text):
        hits += 0.6
    if any(mark in text for mark in ("?", "？", "!", "！")):
        hits += 0.7
    if 6 <= len(text) <= 140:
        hits += 0.4
    return min(1.0, hits / 3.2)
