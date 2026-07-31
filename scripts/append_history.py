#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_HISTORY = Path.home() / ".config/leetcode-study/history.json"
# solution 是仓库根目录下的 submodule；doocs/leetcode 的题目在子模块内的 solution/ 子目录下
SOLUTION_ROOT = Path(__file__).resolve().parents[1] / "solution" / "solution"
REQUIRED_FIELDS = {
    "title": str,
    "path": str,
    "accepted_at": str,
}
HEADING_LINK_RE = re.compile(r"^#\s+\[(?P<title>.+?)\]\(.+?\)\s*$")
HEADING_TEXT_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
HEADING_NUMBER_RE = re.compile(r"^\d+\.\s+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

try:
    from charset_normalizer import from_bytes as _detect_encoding
except ImportError:
    _detect_encoding = None

# \u8bfb\u53d6\u6587\u4ef6\u65f6\u4e0d\u518d\u786c\u7f16\u7801 UTF-8\uff1a\u4e25\u683c UTF-8 \u4f18\u5148\uff0c\u5176\u4f59\u5019\u9009\u6309\u8bed\u8a00\u4fe1\u53f7\u8bc4\u5206\u53d6\u6700\u4f18\uff0c\u5168\u90e8\u5931\u8d25\u65f6 latin-1 \u65e0\u635f\u515c\u5e95
COMMON_CJK = set("\u7684\u4e00\u662f\u4e0d\u4e86\u4eba\u6211\u5728\u6709\u4ed6\u8fd9\u4e2d\u5927\u6765\u4e0a\u56fd\u4e2a\u5230\u8bf4\u4eec\u4e3a\u5b50\u548c\u4f60\u5730\u51fa\u9053\u4e5f\u65f6\u5e74\u5f97\u5c31\u90a3\u8981\u4e0b\u4ee5\u751f\u4f1a\u81ea\u7740\u53bb\u4e4b\u8fc7\u5bb6\u5b66\u5bf9\u53ef\u5979\u91cc\u540e\u5c0f\u4e48\u5fc3\u591a\u5929\u800c\u80fd\u597d\u90fd\u7136\u6ca1\u65e5\u4e8e\u8d77\u8fd8\u53d1\u6210\u4e8b\u53ea\u4f5c\u5f53\u60f3\u770b\u89c1\u9762\u53c8\u624b\u8d70\u5f00")
# \u8c1a\u6587\u53ea\u6309\u5e38\u7528\u97f3\u8282\u8ba1\u5206\uff1a\u771f\u5b9e\u97e9\u6587\u51e0\u4e4e\u5168\u7528\u5e38\u7528\u97f3\u8282\uff0c\u800c\u4e71\u7801\u5f0f\u968f\u673a\u97f3\u8282\uff08EUC-KR \u8bef\u89e3\u7801\u4ea7\u7269\uff09\u57fa\u672c\u4e0d\u4f1a\u547d\u4e2d
COMMON_HANGUL = set("\uc758\uc774\uadf8\ub294\uac00\ub098\ub2e4\ub77c\ub9c8\ubc14\uc0ac\uc544\uc790\ucc28\uce74\ud0c0\ud30c\ud558\ub108\ub354\ub7ec\uba38\ubc84\uc11c\uc5b4\uc800\ucc98\ucee4\ud130\ud5c8\uc9c0\uae30\ub2c8\ub9ac\ubbf8\ube44\uc2dc\ud788\ub4e4\uc744\ub97c\uc5d0\uc640\uacfc\ub3c4\ub85c\uc218\ud569\uc81c\ubaa9\ubb38\ud574\uacb0\ub2f5\uc2dc\uac04\uace0\uc788\uc5c6\uc54a\uc798\ubabb")
# \u5047\u540d\u53ea\u5728\u65e5\u6587\u7f16\u7801\u4e0b\u8ba1\u5206\uff1aGB18030 \u4ea7\u7269\u4e5f\u53ef\u80fd\u542b\u5047\u540d\uff08GB2312 \u7684 A4/A5 \u533a\uff09\uff0c\u4e00\u5f8b\u52a0\u5206\u4f1a\u88ab\u8bef\u89e3\u7801\u4ea7\u7269\u94bb\u7a7a\u5b50
JAPANESE_ENCODINGS = frozenset({
    "shift_jis", "cp932", "euc_jp", "euc_jis_2004", "iso2022_jp",
    "iso2022_jp_1", "iso2022_jp_2", "iso2022_jp_3", "iso2022_jp_ext",
})


def _score_text(text: str, kana_bonus: int = 0) -> int:
    hanzi = kana = hangul = 0
    for ch in text:
        if "\u3040" <= ch <= "\u30ff":
            kana += 1
        elif "\uac00" <= ch <= "\ud7a3":
            if ch in COMMON_HANGUL:
                hangul += 1
        elif "\u4e00" <= ch <= "\u9fff":
            hanzi += 1
    return hanzi + 2 * sum(ch in COMMON_CJK for ch in text) + kana_bonus * kana + 3 * hangul


def read_text_robust(path: Path) -> str:
    raw = path.read_bytes()
    # 1) \u4e25\u683c UTF-8\uff08\u542b BOM\uff09\u4f18\u5148\uff0c\u96f6\u8bef\u5224
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # 2) \u5404\u7f16\u7801\u5019\u9009\u6309\u8bed\u8a00\u4fe1\u53f7\u8bc4\u5206\u53d6\u6700\u4f18\uff08GB18030 \u53cc\u5b57\u8282\u8303\u56f4\u4e0e\u65e5\u6587/\u7e41\u4f53\u91cd\u53e0\uff0c\u8bc4\u5206\u53ef\u907f\u514d\u4e92\u8bef\u5224\uff09
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
    # 3) \u5168\u90e8\u5931\u8d25\uff1alatin-1 \u65e0\u635f\u515c\u5e95\uff08\u4e0d\u518d\u9759\u9ed8\u4e22\u5b57\u8282\uff09
    return raw.decode("latin-1")


def submodule_url() -> str:
    """\u4ece\u4ed3\u5e93\u6839\u76ee\u5f55 .gitmodules \u8bfb\u53d6 solution \u5b50\u6a21\u5757\u7684\u8fdc\u7a0b\u5730\u5740"""
    parent_root = Path(__file__).resolve().parents[1]
    out = subprocess.check_output(
        ["git", "config", "-f", str(parent_root / ".gitmodules"), "submodule.solution.url"],
        timeout=10,
    )
    return out.decode().strip()


def ensure_solution_updated(solution_root: Path) -> None:
    """\u62c9\u53d6\u524d\u5148\u5224\u65ad\uff1asolution \u5b50\u6a21\u5757\u7f3a\u5931 .git\uff0c\u6216\u843d\u540e\u8fdc\u7a0b\u8d85\u8fc7 30 \u4e2a commit \u65f6\uff0c\u4ee5\u6d45\u514b\u9686\u65b9\u5f0f\u62c9\u53d6\u6700\u65b0\uff1b\u5931\u8d25\u9759\u9ed8\u964d\u7ea7"""
    try:
        if not (solution_root / ".git").exists():
            # \u5b50\u6a21\u5757\u4e0d\u5b58\u5728\uff1a\u6d45\u514b\u9686\uff08depth=1\uff09\u6700\u65b0\u4ee3\u7801
            solution_root.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", "--single-branch", "--branch", "main",
                 submodule_url(), str(solution_root)],
                check=True, capture_output=True, timeout=300,
            )
            return
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
        # \u843d\u540e\u8d85\u8fc7 30 \u4e2a commit\uff1a\u7528\u6d45\u62c9\u53d6\uff08depth=1\uff09+ reset \u76f4\u63a5\u8df3\u5230\u8fdc\u7a0b\u6700\u65b0\uff0c\u907f\u514d\u5386\u53f2\u8d8a\u79ef\u8d8a\u6df1
        behind = int(subprocess.check_output(
            ["git", "-C", str(solution_root), "rev-list", "--count", "HEAD..FETCH_HEAD"],
            timeout=10,
        ).decode().strip())
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired, ValueError):
        return
    try:
        if behind > 30:
            subprocess.run(
                ["git", "-C", str(solution_root), "fetch", "--depth", "1", "origin", "main"],
                check=True, capture_output=True, timeout=60,
            )
            subprocess.run(
                ["git", "-C", str(solution_root), "reset", "--hard", "FETCH_HEAD"],
                check=True, capture_output=True, timeout=30,
            )
            return
        # \u843d\u540e\u4e0d\u591a\uff1a\u5b50\u6a21\u5757\u9ed8\u8ba4 detached HEAD\uff0c\u5148\u5207\u5230\u8ddf\u8e2a\u5206\u652f\u518d ff \u62c9\u53d6\uff0c\u907f\u514d\u4e22\u5f03\u672c\u5730\u6539\u52a8
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
    data = json.loads(read_text_robust(path))
    if not isinstance(data, list):
        raise ValueError("history.json must be a JSON array")
    for item in data:
        validate_entry(item)
    return data


def read_primary_title(readme: Path) -> str:
    if not readme.exists():
        raise ValueError("required README file does not exist: {}".format(readme))
    for line in read_text_robust(readme).splitlines():
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
    solution_root = SOLUTION_ROOT.resolve()
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

    ensure_solution_updated(SOLUTION_ROOT)
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
