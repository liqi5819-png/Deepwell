from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.frameworks import build_framework_prompt_from_data
from tools.knowledge import resolve_user_constraints_path
from tools.lifestyle import build_lifestyle_prompt_from_data
from tools.User_Profiling import (
    ROUTE_OUTPUT_FILE,
    build_base_prompt_from_data,
    ensure_user_ids,
    load_user_input,
    normalize_user_inputs,
    restore_user_input_shape,
    save_json_output,
)
from tools.llm_runner import CFG, LLMRunner


ROOT_DIR = Path(__file__).resolve().parent
BASE_PROMPT_FILE = ROOT_DIR / "base_prompt.txt"
FRAMEWORK_PROMPT_FILE = ROOT_DIR / "framework_prompt.txt"
LIFESTYLE_PROMPT_FILE = ROOT_DIR / "lifestyle_prompt.txt"
NORMALIZED_INPUT_FILE = ROOT_DIR / "workflow_user_input.json"


def build_constraints_file_path(user_id: str) -> Path:
    return resolve_user_constraints_path(user_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Workflow 入口：使用 knowledge.py 内置规则生成 "
            "base/framework/lifestyle prompt，并按需调用指定 LLM。"
        )
    )
    parser.add_argument("--provider", choices=list(CFG), default="kimi")
    parser.add_argument("--input", required=True)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-prompt", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument(
        "--constraints-file",
        help=(
            "可选：framework_prompt 的 LLM 回复保存路径；"
            '未传时默认写入 knowledge/{user_id}_constraints.json'
        ),
    )
    return parser.parse_args()


def run_prompt_stage(
    *,
    stage_name: str,
    prompt: str,
    runner: LLMRunner | None,
    print_prompt: bool,
    dry_run: bool,
    response_output_path: Path | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"prompt": prompt}

    if print_prompt or dry_run:
        print(f"===== {stage_name} =====\n{prompt}\n")

    if runner is None:
        return row

    try:
        result = runner.run(prompt, None)
        row.update(result)
        print(f"===== {stage_name}_response =====\n{result['response_text']}\n")
        if response_output_path is not None:
            response_output_path.write_text(result["response_text"], encoding="utf-8")
            row["saved_constraints_file"] = str(response_output_path)
    except Exception as exc:
        row["error"] = str(exc)
        print(f"===== {stage_name}_error =====\n{exc}\n")

    return row


def main() -> None:
    args = parse_args()

    users_data = ensure_user_ids(normalize_user_inputs(load_user_input(args.input)))
    normalized_input = restore_user_input_shape(users_data)
    save_json_output(normalized_input, NORMALIZED_INPUT_FILE)

    if len(users_data) != 1:
        raise ValueError("main.py 当前仅支持单用户 workflow 输入。")
    user_id = users_data[0]["user_id"]

    base = build_base_prompt_from_data(users_data[0])
    save_json_output(base["route_result"], ROUTE_OUTPUT_FILE)

    framework = build_framework_prompt_from_data(
        users_data,
        route_results=base["route_result"],
    )["prompt"]

    constraints_path = (
        Path(args.constraints_file)
        if args.constraints_file
        else build_constraints_file_path(user_id)
    )

    BASE_PROMPT_FILE.write_text(base["prompt"], encoding="utf-8")
    FRAMEWORK_PROMPT_FILE.write_text(framework, encoding="utf-8")

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "workflow",
        "provider": args.provider,
        "model": args.model or CFG[args.provider][1],
        "base_url": args.base_url or CFG[args.provider][2],
        "system_prompt": None,
        "results": {},
        "normalized_input_file": str(NORMALIZED_INPUT_FILE),
        "constraints_file": str(constraints_path),
        "lifestyle_prompt_file": str(LIFESTYLE_PROMPT_FILE),
    }

    runner = None if args.dry_run else LLMRunner(
        args.provider, args.model, None, args.base_url
    )

    output["results"]["base_prompt"] = run_prompt_stage(
        stage_name="base_prompt",
        prompt=base["prompt"],
        runner=runner,
        print_prompt=args.print_prompt,
        dry_run=args.dry_run,
    )
    output["results"]["framework_prompt"] = run_prompt_stage(
        stage_name="framework_prompt",
        prompt=framework,
        runner=runner,
        print_prompt=args.print_prompt,
        dry_run=args.dry_run,
        response_output_path=constraints_path,
    )

    try:
        lifestyle = build_lifestyle_prompt_from_data(
            users_data,
            constraints_path=constraints_path,
        )["prompt"]
        LIFESTYLE_PROMPT_FILE.write_text(lifestyle, encoding="utf-8")
        output["results"]["lifestyle_prompt"] = run_prompt_stage(
            stage_name="lifestyle_prompt",
            prompt=lifestyle,
            runner=runner,
            print_prompt=args.print_prompt,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        output["results"]["lifestyle_prompt"] = {"error": str(exc)}
        print(f"===== lifestyle_prompt_error =====\n{exc}\n")

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
