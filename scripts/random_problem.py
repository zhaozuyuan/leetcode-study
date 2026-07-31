#!/usr/bin/env python3
import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set


# solution 是仓库根目录下的 submodule；doocs/leetcode 的题目在子模块内的 solution/ 子目录下
SOLUTION_ROOT = Path(__file__).resolve().parents[1] / "solution" / "solution"
DEFAULT_HISTORY = Path.home() / ".config/leetcode-study/history.json"

DIFFICULTY_ALIASES = {
    "easy": "easy",
    "简单": "easy",
    "medium": "medium",
    "中等": "medium",
    "hard": "hard",
    "困难": "hard",
}

QUOTAS = {
    "easy": 3,
    "medium": 6,
    "hard": 1,
}
HEADING_LINK_RE = re.compile(r"^#\s+\[(?P<title>.+?)\]\(.+?\)\s*$")
HEADING_TEXT_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")

try:
    from charset_normalizer import from_bytes as _detect_encoding
except ImportError:
    _detect_encoding = None

# 读取文件时不再硬编码 UTF-8：严格 UTF-8 优先，其余候选按语言信号评分取最优，全部失败时 latin-1 无损兜底
COMMON_CJK = set("的一是不了人我在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看见面又手走开")
# 谚文只按常用音节计分：真实韩文几乎全用常用音节，而乱码式随机音节（EUC-KR 误解码产物）基本不会命中
COMMON_HANGUL = set("의이그는가나다라마바사아자차카타파하너더러머버서어저처커터허지기니리미비시히들을를에와과도로수합제목문해결답시간고있없않잘못")
# 假名只在日文编码下计分：GB18030 产物也可能含假名（GB2312 的 A4/A5 区），一律加分会被误解码产物钻空子
JAPANESE_ENCODINGS = frozenset({
    "shift_jis", "cp932", "euc_jp", "euc_jis_2004", "iso2022_jp",
    "iso2022_jp_1", "iso2022_jp_2", "iso2022_jp_3", "iso2022_jp_ext",
})


def _score_text(text: str, kana_bonus: int = 0) -> int:
    hanzi = kana = hangul = 0
    for ch in text:
        if "぀" <= ch <= "ヿ":
            kana += 1
        elif "가" <= ch <= "힣":
            if ch in COMMON_HANGUL:
                hangul += 1
        elif "一" <= ch <= "鿿":
            hanzi += 1
    return hanzi + 2 * sum(ch in COMMON_CJK for ch in text) + kana_bonus * kana + 3 * hangul


def read_text_robust(path: Path) -> str:
    raw = path.read_bytes()
    # 1) 严格 UTF-8（含 BOM）优先，零误判
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # 2) 各编码候选按语言信号评分取最优（GB18030 双字节范围与日文/繁体重叠，评分可避免互误判）
    best_text, best_score = None, 0
    for enc in ("gb18030", "big5", "shift_jis", "euc_kr", "euc_jp"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        score = _score_text(text, 3 if enc in JAPANESE_ENCODINGS else 0)
        if score > best_score:
            best_text, best_score = text, score
    if _detect_encoding is not None:
        for match in _detect_encoding(raw):
            score = _score_text(str(match), 3 if match.encoding in JAPANESE_ENCODINGS else 0)
            if score > best_score:
                best_text, best_score = str(match), score
    if best_text is not None:
        return best_text
    # 3) 全部失败：latin-1 无损兜底（不再静默丢字节）
    return raw.decode("latin-1")


def ensure_solution_updated(solution_root: Path) -> None:
    """拉取前先判断：solution 子模块落后于远程才更新；离线等失败场景静默降级"""
    if not (solution_root / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "-C", str(solution_root), "fetch", "--quiet"],
            check=True, capture_output=True, timeout=30,
        )
        local = subprocess.check_output(
            ["git", "-C", str(solution_root), "rev-parse", "HEAD"], timeout=10,
        )
        remote = subprocess.check_output(
            ["git", "-C", str(solution_root), "rev-parse", "FETCH_HEAD"], timeout=10,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return
    if local == remote:
        return
    try:
        # 子模块默认 detached HEAD，先切到跟踪分支再 ff 拉取，避免丢弃本地改动
        subprocess.run(
            ["git", "-C", str(solution_root), "checkout", "main"],
            check=True, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["git", "-C", str(solution_root), "pull", "--ff-only", "--quiet"],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return


def load_history(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(read_text_robust(path))
    except (json.JSONDecodeError, OSError):
        return set()

    seen = set()
    if not isinstance(data, list):
        return seen
    for item in data:
        if isinstance(item, dict):
            title = item.get("title")
            if isinstance(title, str):
                seen.add(title)
        elif isinstance(item, str):
            seen.add(item)
    return seen


def problem_title(problem_dir: Path) -> str:
    match = re.match(r"^\d+\.(.+)$", problem_dir.name)
    if match:
        return match.group(1).strip()
    return problem_dir.name


def problem_number(problem_dir: Path) -> str:
    match = re.match(r"^(\d+)\.", problem_dir.name)
    return match.group(1) if match else ""


def read_primary_title(readme: Path) -> Optional[str]:
    if not readme.exists():
        return None
    try:
        lines = read_text_robust(readme).splitlines()
    except OSError:
        return None
    for line in lines:
        link_match = HEADING_LINK_RE.match(line)
        if link_match:
            return link_match.group("title").strip()
        text_match = HEADING_TEXT_RE.match(line)
        if text_match:
            return text_match.group("title").strip()
    return None


def problem_display_title(problem_dir: Path) -> str:
    title = read_primary_title(problem_dir / "README.md")
    if title:
        return title
    raw_title = problem_title(problem_dir)
    number = problem_number(problem_dir)
    return f"{number}. {raw_title}" if number else raw_title


def read_difficulty(problem_dir: Path) -> Optional[str]:
    for readme_name in ("README_EN.md", "README.md"):
        readme = problem_dir / readme_name
        if not readme.exists():
            continue
        try:
            text = read_text_robust(readme)
        except OSError:
            continue
        match = re.search(r"^difficulty:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip().strip("\"'")
        return DIFFICULTY_ALIASES.get(raw.lower(), DIFFICULTY_ALIASES.get(raw))
    return None


def is_seen(problem_dir: Path, seen: Set[str]) -> bool:
    return problem_display_title(problem_dir) in seen


def iter_problem_dirs(solution_root: Path) -> Iterator[Path]:
    for readme in solution_root.glob("*/*/README_EN.md"):
        problem_dir = readme.parent
        if problem_dir.is_dir():
            yield problem_dir


def collect_candidates(solution_root: Path, seen: Set[str]) -> Dict[str, List[Path]]:
    buckets = {difficulty: [] for difficulty in QUOTAS}
    for problem_dir in iter_problem_dirs(solution_root):
        if is_seen(problem_dir, seen):
            continue
        difficulty = read_difficulty(problem_dir)
        if difficulty in buckets:
            buckets[difficulty].append(problem_dir)
    return buckets


def select_pool(buckets: Dict[str, List[Path]]) -> List[Path]:
    selected = []
    missing = []
    for difficulty, quota in QUOTAS.items():
        problems = buckets[difficulty]
        if len(problems) < quota:
            missing.append(f"{difficulty}: need {quota}, found {len(problems)}")
            continue
        selected.extend(random.sample(problems, quota))
    if missing:
        raise RuntimeError("未找到足够的未练习题目：" + "；".join(missing))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="随机推荐一道未练习 LeetCode 算法题")
    parser.parse_args()

    ensure_solution_updated(SOLUTION_ROOT)
    solution_root = SOLUTION_ROOT
    history = DEFAULT_HISTORY.expanduser()

    if not solution_root.exists():
        print(f"错误：题库目录不存在：{solution_root}", file=sys.stderr)
        return 1

    seen = load_history(history)
    buckets = collect_candidates(solution_root, seen)
    try:
        pool = select_pool(buckets)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    chosen = random.choice(pool)
    print(f"算法题目：{problem_display_title(chosen)}")
    print(f"题目所在本地目录：{chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
