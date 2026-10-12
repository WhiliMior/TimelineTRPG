"""
输入纠错建议：指令名、属性名输错时给出「你是不是想输入 xxx」
"""

import difflib
import os
from collections.abc import Iterable


def closest(word: str, candidates: Iterable[str], cutoff: float = 0.5) -> str | None:
    """返回与 word 最接近的候选项（忽略大小写），没有足够接近的返回 None"""
    if not word:
        return None
    lowered: dict[str, str] = {}
    for candidate in candidates:
        lowered.setdefault(candidate.lower(), candidate)
    target = word.lower()
    if target in lowered:
        return None

    # 中文属性名只有两三个字，相似度经常打平（力良 对 力量/智力 都是 0.5），
    # 打平时取开头相同字数多的
    def score(candidate: str) -> tuple[float, int]:
        ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
        return ratio, len(os.path.commonprefix([target, candidate]))

    best = max(lowered, key=score, default=None)
    if best is None or score(best)[0] < cutoff:
        return None
    return lowered[best]
