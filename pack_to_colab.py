#!/usr/bin/env python3
"""현재 디렉토리의 모든 소스 파일과 폴더 구조를 Colab %%writefile 셀 기반 .ipynb로 패키징한다."""

import json
import uuid
from pathlib import Path

# 제외할 디렉토리 및 확장자 (필요 시 수정)
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".ipynb_checkpoints",
    ".specify",
    ".hermes",
    "specs",
    "hermes-env",
}
EXCLUDE_EXTS = {".ipynb", ".pyc"}


def make_code_cell(lines: list[str]) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": uuid.uuid4().hex[:12],
        "metadata": {},
        "outputs": [],
        "source": lines,
    }


def main() -> None:
    self_path = Path(__file__).resolve()
    base_dir = self_path.parent
    output_path = base_dir / f"{base_dir.name}.ipynb"

    target_files: list[Path] = []
    subdirs: set[str] = set()

    for path in sorted(base_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() in {self_path, output_path.resolve()}:
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(base_dir).parts):
            continue
        if path.suffix in EXCLUDE_EXTS:
            continue

        rel_path = path.relative_to(base_dir)
        if rel_path.parent != Path("."):
            subdirs.add(rel_path.parent.as_posix())
        target_files.append(path)

    cells: list[dict] = []

    # 하위 디렉토리가 존재하면 Colab %%writefile 오류 방지를 위해 폴더 생성 셀을 맨 앞에 추가
    if subdirs:
        dir_list = sorted(subdirs)
        setup_lines = [
            "import os\n",
            f"for d in {dir_list!r}:\n",
            "    os.makedirs(d, exist_ok=True)\n",
        ]
        cells.append(make_code_cell(setup_lines))

    packed_count = 0
    for file_path in target_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"[건너뜀 - 바이너리 파일] {file_path.relative_to(base_dir)}")
            continue

        rel_posix = file_path.relative_to(base_dir).as_posix()
        source_lines = [f"%%writefile {rel_posix}\n"] + content.splitlines(keepends=True)
        cells.append(make_code_cell(source_lines))
        packed_count += 1

    notebook = {
        "cells": cells,
        "metadata": {
            "colab": {
                "name": output_path.name,
                "provenance": [],
            },
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }

    output_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"생성 완료: {output_path} (총 {packed_count}개 파일 패키징)")


if __name__ == "__main__":
    main()

