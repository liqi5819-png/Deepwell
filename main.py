from __future__ import annotations

import argparse, json
from datetime import datetime
from pathlib import Path

from frameworks import build_framework_prompt_from_data, build_framework_prompt_from_file
from generate_prompt_from_input import build_base_prompt_from_file
from llm_runner import CFG, LLMRunner


class WorkflowError(RuntimeError): pass


def read(x): return Path(x).read_text(encoding="utf-8")
def write(x, v): Path(x).write_text(json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else str(v), encoding="utf-8")
def pick(a, k): return getattr(a, k, None) or (read(getattr(a, f"{k}_file")) if getattr(a, f"{k}_file", None) else None)


def build_prompts(a):
    if not a.input: raise WorkflowError("需要 --input。")
    if a.mode == "workflow":
        base_result = build_base_prompt_from_file(a.input)
        framework_result = (
            build_framework_prompt_from_file(a.input, route_path=a.route, extraction_items_path=a.extraction_items)
            if a.route
            else build_framework_prompt_from_data(
                base_result["user_data"],
                route_results=base_result["route_result"],
                extraction_items_path=a.extraction_items,
                validate_inputs=False,
            )
        )
        return {
            "base_prompt": base_result["prompt"],
            "framework_prompt": framework_result["prompt"],
        }
    out = {}
    if a.mode == "base_prompt":
        out["base_prompt"] = build_base_prompt_from_file(a.input)["prompt"]
    if a.mode == "framework_prompt":
        out["framework_prompt"] = build_framework_prompt_from_file(
            a.input, route_path=a.route, extraction_items_path=a.extraction_items
        )["prompt"]
    return out


def args():
    x = argparse.ArgumentParser(description="流程入口：生成 base/framework prompt，并调用指定 LLM。")
    x.add_argument("--mode", choices=["workflow", "base_prompt", "framework_prompt"], default="workflow")
    x.add_argument("--provider", choices=list(CFG), default="kimi")
    x.add_argument("--input", required=True); x.add_argument("--route"); x.add_argument("--extraction-items")
    x.add_argument("--system-prompt"); x.add_argument("--system-prompt-file")
    x.add_argument("--model"); x.add_argument("--api-key"); x.add_argument("--base-url")
    x.add_argument("--dry-run", action="store_true"); x.add_argument("--print-prompt", action="store_true")
    x.add_argument("--output-json")
    return x.parse_args()


def main():
    a = args(); sp = pick(a, "system_prompt"); prompts = build_prompts(a)
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "mode": a.mode, "provider": a.provider, "model": a.model or CFG[a.provider][1], "base_url": a.base_url or CFG[a.provider][2], "system_prompt": sp, "results": {}}
    runner = None if a.dry_run else LLMRunner(a.provider, a.model, a.api_key, a.base_url)
    for name, prompt in prompts.items():
        row = {"prompt": prompt}
        if a.print_prompt or a.dry_run: print(f"===== {name} =====\n{prompt}\n")
        if not a.dry_run:
            try:
                res = runner.run(prompt, sp)
                row.update(res)
                print(f"===== {name}_response =====\n{res['response_text']}\n")
            except Exception as e:
                row["error"] = str(e)
                print(f"===== {name}_error =====\n{e}\n")
        out["results"][name] = row
    if a.output_json: write(a.output_json, out)


if __name__ == "__main__": main()
