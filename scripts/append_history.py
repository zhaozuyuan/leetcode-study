#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_HISTORY = Path.home() / ".config/leetcode-study/history.json"
DEFAULT_SOLUTION_ROOT = Path.home() / "Work/algorithm/leetcode/solution"
REQUIRED_FIELDS = {
    "title": str,
    "path": str,
    "accepted_at": str,
}
HEADING_LINK_RE = re.compile(r"^#\s+\[(?P<title>.+?)\]\(.+?\)\s*$")
HEADING_TEXT_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
HEADING_NUMBER_RE = re.compile(r"^\d+\.\s+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def validate_entry(item: Any) -> None:
    if not isinstance(item, dict):
        raise ValueError("history.json entries must be objects")
    if set(item) != set(REQUIRED_FIELDS):
        raise ValueError("history.json entry fields must be title, path, accepted_at")
    for key, typ in REQUIRED_FIELDS.items():
        if not isinstance(item[key], typ):
            raise ValueError("history.json field {} has invalid type".format(key))


def load_history(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("history.json must be a JSON array")
    for item in data:
        validate_entry(item)
    return data


def read_primary_title(readme: Path) -> str:
    if not readme.exists():
        raise ValueError("required README file does not exist: {}".format(readme))
    for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines():
        link_match = HEADING_LINK_RE.match(line)
        if link_match:
            return link_match.group("title").strip()
        text_match = HEADING_TEXT_RE.match(line)
        if text_match:
            return text_match.group("title").strip()
    raise ValueError("required README file has no primary title: {}".format(readme))


def resolve_problem_dir(problem_path: Path) -> Path:
    problem_dir = problem_path.expanduser().resolve()
    if not problem_dir.is_dir():
        raise ValueError("problem path must be a directory: {}".format(problem_dir))
    solution_root = DEFAULT_SOLUTION_ROOT.expanduser().resolve()
    try:
        problem_dir.relative_to(solution_root)
    except ValueError as exc:
        raise ValueError("problem path must be under {}".format(solution_root)) from exc
    return problem_dir


def read_chinese_title(problem_dir: Path) -> str:
    english_title = read_primary_title(problem_dir / "README_EN.md")
    chinese_title = read_primary_title(problem_dir / "README.md")
    if not CJK_RE.search(chinese_title):
        raise ValueError(
            "README.md title must be Chinese for README_EN.md title '{}': {}".format(
                english_title,
                chinese_title,
            )
        )
    if not HEADING_NUMBER_RE.search(chinese_title):
        raise ValueError("README.md title must include the problem number: {}".format(chinese_title))
    return chinese_title


def build_entry(problem_path: Path) -> Dict[str, str]:
    problem_dir = resolve_problem_dir(problem_path)
    entry = {
        "title": read_chinese_title(problem_dir),
        "path": str(problem_dir),
        "accepted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    validate_entry(entry)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Append an accepted problem to history.json")
    parser.add_argument("problem_path", type=Path)
    args = parser.parse_args()

    history_path = DEFAULT_HISTORY.expanduser()
    data = load_history(history_path)
    data.append(build_entry(args.problem_path))
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
