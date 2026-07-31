#!/usr/bin/env python3
import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set


DEFAULT_SOLUTION_ROOT = Path.home() / "Work/algorithm/leetcode/solution"
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


def load_history(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
        lines = readme.read_text(encoding="utf-8", errors="ignore").splitlines()
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
            text = readme.read_text(encoding="utf-8", errors="ignore")
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

    solution_root = DEFAULT_SOLUTION_ROOT.expanduser()
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
