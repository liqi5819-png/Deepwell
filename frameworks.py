from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from generate_prompt_from_input import (
    GOAL_TYPE_LABELS,
    LABOR_INTENSITY_LABELS,
    SEX_LABELS,
    calculate_bmi,
    get_display_label,
    load_user_input,
    route_user_to_guideline,
    summarize_food_allergy,
    summarize_health_status,
    validate_user_data,
)


EXTRACTION_ITEMS_FILE = Path(__file__).resolve().parent / "指南提取信息.txt"


class FrameworkInputError(ValueError):
    """frameworks.py 的输入异常。"""


def load_extraction_items(file_path: str | Path = EXTRACTION_ITEMS_FILE) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"指南提取信息文件不存在：{path}")

    items = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not items:
        raise FrameworkInputError(f"指南提取信息文件为空：{path}")
    return items


def _normalize_dict_list(raw_data: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(raw_data, dict):
        return [raw_data]
    if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
        return raw_data
    raise FrameworkInputError(
        f"{label} JSON 必须是单个对象，或由多个对象组成的数组。"
    )


def normalize_user_inputs(raw_data: Any) -> list[dict[str, Any]]:
    """兼容单用户 dict 和多用户 list[dict] 两种输入。"""

    return _normalize_dict_list(raw_data, "输入")


def normalize_route_inputs(raw_data: Any) -> list[dict[str, Any]]:
    """兼容单路由 dict 和多路由 list[dict] 两种输入。"""

    return _normalize_dict_list(raw_data, "路由")


def build_user_summary(user_data: dict[str, Any], user_index: int) -> dict[str, Any]:
    basic_info = user_data["basic_info"]
    physical_activity = user_data["physical_activity"]
    goal = user_data["goal"]

    return {
        "user_id": f"user_{user_index + 1}",
        "age_years": basic_info["age_years"],
        "sex": get_display_label(basic_info["sex"], SEX_LABELS),
        "height_cm": basic_info["height_cm"],
        "weight_kg": basic_info["weight_kg"],
        "waist_cm": basic_info["waist_cm"],
        "bmi": calculate_bmi(user_data),
        "labor_intensity": get_display_label(
            physical_activity["labor_intensity"], LABOR_INTENSITY_LABELS
        ),
        "goal_type": get_display_label(goal["goal_type"], GOAL_TYPE_LABELS),
        "food_allergy": summarize_food_allergy(user_data),
        "health_status": summarize_health_status(user_data),
    }


def sanitize_route_result(route_result: dict[str, Any]) -> dict[str, Any]:
    """只保留 frameworks.py 需要的路由信息。"""

    selected_guidelines = route_result.get("selected_guidelines", [])
    return {
        "profile_tags": route_result.get("profile_tags", []),
        "bmi": route_result.get("bmi"),
        "mapping_rule": route_result.get("mapping_rule"),
        "disease_reasons": route_result.get("disease_reasons", []),
        "selected_guidelines": [
            {
                "file_name": item.get("file_name"),
                "file_path": item.get("file_path"),
                "exists": item.get("exists"),
            }
            for item in selected_guidelines
        ],
    }


def build_framework_payload(
    users_data: list[dict[str, Any]],
    route_results: list[dict[str, Any]] | None = None,
    extraction_items: list[str] | None = None,
    validate_inputs: bool = True,
) -> dict[str, Any]:
    """构建交给 LLM 的上下文载荷。"""

    extraction_items = extraction_items or load_extraction_items()

    if route_results is not None and len(route_results) != len(users_data):
        raise FrameworkInputError("用户数量与路由结果数量不一致，无法一一对应。")

    users_payload: list[dict[str, Any]] = []
    for index, user_data in enumerate(users_data):
        if validate_inputs:
            validate_user_data(user_data)
        route_result = (
            route_results[index]
            if route_results is not None
            else route_user_to_guideline(user_data)
        )

        users_payload.append(
            {
                "user_index": index + 1,
                "user_summary": build_user_summary(user_data, index),
                "route_result": sanitize_route_result(route_result),
            }
        )

    return {
        "task_name": "guideline_restriction_extraction",
        "version": "0.2",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": (
            "该结构用于给 LLM 生成用户级限制信息。"
            "当前优先抽取可机器校验的饮食约束，运动约束仅在指南中有明确量化规则时输出。"
        ),
        "extraction_items": extraction_items,
        "users": users_payload,
    }


def build_llm_prompt(payload: dict[str, Any]) -> str:
    """生成交给 LLM 的提示词。"""

    users_json = json.dumps(payload["users"], ensure_ascii=False, indent=2)
    extraction_items_json = json.dumps(payload["extraction_items"], ensure_ascii=False, indent=2)

    prompt_lines = [
        "你是一名医学与营养指南信息抽取助手。",
        "你的任务是根据输入的用户基础信息和对应指南文件，抽取只适用于该用户、且可被程序直接校验的结构化约束，并只返回一个 JSON 对象。",
        "",
        "工作目标：",
        "1. 重点抽取饮食与营养相关的可量化约束，用于后续和模型生成的每日食谱进行自动比对。",
        "2. 运动字段暂时保留，但只有当指南中给出明确、可量化、可执行的运动约束时才填写；否则返回空数组。",
        "3. 只保留当前输入用户适用的规则，不要输出其他 BMI 档位、其他目标类型或其他疾病分支的通用内容。",
        "",
        "抽取原则：",
        "1. 每条饮食约束必须尽量转成机器可比较结构，不要只写自然语言描述。",
        "2. 如果指南没有给出明确数值、范围、阈值或可枚举要求，不要编造；该项可以不输出。",
        "3. 如果多个指南对同一指标给出不同限制，优先保留更适合该用户疾病状态的限制，并在 source_guidelines 中列出来源。",
        "4. 如果用户有食物过敏，相关禁忌要体现在 restriction_items 或 special_notes 中。",
        "5. 输出必须是 JSON，不要输出 Markdown，不要输出解释性前后缀。",
        "",
        "restriction_items 字段要求：",
        "1. restriction_items 只放饮食与营养约束。",
        "2. 每条 restriction_items 必须包含以下字段：metric_key、display_name、constraint_level、operator、min_value、max_value、target_value、unit、scope、reason、source_guidelines。",
        "3. metric_key 必须使用稳定英文键名，不能使用自由文本。",
        "4. display_name 使用中文，尽量与待提取指标一致。",
        "5. constraint_level 只允许使用 hard 或 soft。",
        "6. operator 只允许使用 between、<=、>=、=、boolean_equals、enum_equals。",
        "7. min_value、max_value、target_value 只能填写数字、布尔值、字符串枚举值或 null，不能写成“300-500”这类拼接文本。",
        "8. unit 必须写清单位，例如 g/day、mg/day、kcal/day、%energy、servings/day；如果是布尔或枚举规则，可写 boolean 或 enum。",
        "9. scope 只允许使用 per_day、per_meal、whole_menu。",
        "10. 对于布尔或枚举约束，使用 target_value 表达目标值，并让 min_value、max_value 为 null。",
        "",
        "exercise_restrictions 字段要求：",
        "1. 只有在指南中存在明确量化运动规则时才输出，否则返回空数组。",
        "2. 每条 exercise_restrictions 仍使用原结构：item_name、value、unit、frequency_or_duration、reason、source_guidelines。",
        "",
        "建议使用的 metric_key 示例：",
        """[
  "food_group_count_per_day",
  "refined_grains_all_meals",
  "high_quality_protein_types_per_day",
  "vegetable_grams_per_day",
  "fruit_grams_per_day",
  "grain_grams_per_day",
  "milk_ml_per_day",
  "fiber_grams_per_day",
  "vitamin_c_mg_per_day",
  "calcium_mg_per_day",
  "iron_mg_per_day",
  "total_fat_grams_per_day",
  "saturated_fat_grams_per_day",
  "cholesterol_mg_per_day",
  "protein_energy_ratio_percent",
  "sodium_mg_per_day",
  "macro_ratio_percent",
  "fatty_acid_ratio",
  "energy_kcal_per_day"
]""",
        "",
        "本次重点需要抽取以下指标：",
        extraction_items_json,
        "",
        "请按以下 JSON 结构输出：",
        """{
  "version": "user_specific_restrictions_v2",
  "generated_for_users": [
    {
      "user_id": "user_1",
      "user_summary": {
        "age_years": 0,
        "sex": "",
        "bmi": 0,
        "goal_type": "",
        "health_status": "",
        "labor_intensity": ""
      },
      "source_guidelines": [
        {
          "file_name": "",
          "file_path": ""
        }
      ],
      "restriction_items": [
        {
          "metric_key": "vegetable_grams_per_day",
          "display_name": "每日菜单中蔬菜克重",
          "constraint_level": "hard",
          "operator": "between",
          "min_value": 300,
          "max_value": 500,
          "target_value": null,
          "unit": "g/day",
          "scope": "per_day",
          "reason": "指南给出的推荐摄入范围。",
          "source_guidelines": ["一般饮食.pdf"]
        },
        {
          "metric_key": "refined_grains_all_meals",
          "display_name": "是否三餐全部使用精制谷物",
          "constraint_level": "hard",
          "operator": "boolean_equals",
          "min_value": null,
          "max_value": null,
          "target_value": false,
          "unit": "boolean",
          "scope": "whole_menu",
          "reason": "指南不建议三餐全部使用精制谷物。",
          "source_guidelines": ["一般饮食.pdf"]
        }
      ],
      "exercise_restrictions": [
        {
          "item_name": "",
          "value": "",
          "unit": "",
          "frequency_or_duration": "",
          "reason": "",
          "source_guidelines": [""]
        }
      ],
      "special_notes": []
    }
  ]
}""",
        "",
        "补充约束：",
        "1. 最终输出只包含当前输入用户，不要补充额外用户。",
        "2. restriction_items 中不要保留无法用于程序判断的泛化建议，例如“注意均衡饮食”“少吃油炸食物”，除非它能被明确结构化。",
        "3. 如果某个 extraction_items 在当前指南中没有明确可校验规则，可以不输出该项。",
        "4. source_guidelines 必须写出具体指南文件名。",
        "5. 如果存在过敏或禁忌但无法量化，可写入 special_notes。",
        "",
        "以下是本次输入：",
        users_json,
    ]

    return "\n".join(prompt_lines)


def build_framework_prompt_from_data(
    users_data: dict[str, Any] | list[dict[str, Any]],
    route_results: dict[str, Any] | list[dict[str, Any]] | None = None,
    extraction_items_path: str | Path | None = None,
    validate_inputs: bool = True,
) -> dict[str, Any]:
    """从已准备好的用户数据和路由结果生成 framework payload 与 prompt。"""

    normalized_users = normalize_user_inputs(users_data)
    normalized_routes = (
        normalize_route_inputs(route_results)
        if route_results is not None
        else None
    )
    extraction_items = (
        load_extraction_items(extraction_items_path)
        if extraction_items_path
        else load_extraction_items()
    )
    payload = build_framework_payload(
        normalized_users,
        normalized_routes,
        extraction_items,
        validate_inputs=validate_inputs,
    )
    return {
        "users_data": normalized_users,
        "payload": payload,
        "prompt": build_llm_prompt(payload),
    }


def build_framework_prompt_from_file(
    input_path: str | Path,
    route_path: str | Path | None = None,
    extraction_items_path: str | Path | None = None,
) -> dict[str, Any]:
    """从输入文件生成 framework payload 与 prompt。"""

    raw_user_input = load_user_input(input_path)
    route_results = load_user_input(route_path) if route_path else None
    return build_framework_prompt_from_data(
        raw_user_input,
        route_results=route_results,
        extraction_items_path=extraction_items_path,
    )


def save_text_output(content: str, output_path: str | Path) -> None:
    Path(output_path).write_text(content, encoding="utf-8")


def save_json_output(content: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据用户输入和已路由指南，构建用于 LLM 抽取限制信息的 prompt。"
    )
    parser.add_argument("--input", required=True, help="用户输入 JSON，支持单用户或多用户")
    parser.add_argument(
        "--route",
        help="可选：来自 generate_prompt_from_input.py 的路由结果 JSON，支持单用户或多用户",
    )
    parser.add_argument(
        "--extraction_items",
        default=str(EXTRACTION_ITEMS_FILE),
        help="可选：指南提取信息文件路径",
    )
    parser.add_argument("--output_prompt", help="可选：将 LLM prompt 写入文件")
    parser.add_argument(
        "--output_payload",
        help="可选：将结构化上下文载荷写入 JSON 文件，便于后续调试",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_framework_prompt_from_file(
        args.input,
        route_path=args.route,
        extraction_items_path=args.extraction_items,
    )
    payload = result["payload"]
    prompt = result["prompt"]

    print("===== Framework Payload =====")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("===== LLM Prompt =====")
    print(prompt)

    if args.output_payload:
        save_json_output(payload, args.output_payload)

    if args.output_prompt:
        save_text_output(prompt, args.output_prompt)


if __name__ == "__main__":
    main()
