from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any

from tools.User_Profiling import (
    GOAL_TYPE_LABELS,
    LABOR_INTENSITY_LABELS,
    SEX_LABELS,
    ensure_user_ids,
    get_user_id,
    get_display_label,
    load_user_input,
    summarize_food_allergy,
    summarize_health_status,
    validate_user_data,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
EXTRACTION_ITEMS_FILE = ROOT_DIR / "指南提取信息.txt"
NUMBER_PLACEHOLDER = "<number>"
BOOLEAN_PLACEHOLDER = "<填写true或false>"
RATIO_PLACEHOLDER = "<填写比例字符串，如50:20:30>"
SINGLE_VALUE_OPERATOR = "<填写=或>=或<=>"
RATIO_OPERATOR = "<填写=或enum_equals>"
SINGLE_VALUE_ITEMS = (
    ("每日菜单中的食物组种类数", "food_group_count_per_day"),
    ("每日菜单中包含的优质蛋白种类数", "high_quality_protein_types_per_day"),
)
RANGE_ITEM_GROUPS = (
    (
        "g/day",
        (
            ("每日菜单中蔬菜克重范围", "vegetable_grams_per_day"),
            ("每日菜单中水果克重范围", "fruit_grams_per_day"),
            ("每日菜单中谷类克重范围", "grain_grams_per_day"),
            ("每日菜单中膳食纤维克重范围", "fiber_grams_per_day"),
            ("每日菜单中总脂肪含量范围", "total_fat_grams_per_day"),
            ("每日菜单中饱和脂肪含量范围", "saturated_fat_grams_per_day"),
        ),
    ),
    (
        "mg/day",
        (
            ("每日菜单中维生素C含量范围", "vitamin_c_mg_per_day"),
            ("每日菜单中钙含量范围", "calcium_mg_per_day"),
            ("每日菜单中铁含量范围", "iron_mg_per_day"),
            ("每日菜单中胆固醇含量范围", "cholesterol_mg_per_day"),
            ("每日菜单中钠含量范围", "sodium_mg_per_day"),
        ),
    ),
    (
        "mL/day",
        (("每日菜单中液态奶摄入量范围", "milk_ml_per_day"),),
    ),
    (
        "%energy",
        (("每日菜单中蛋白质能量比例范围", "protein_energy_ratio_percent"),),
    ),
    (
        "kcal/day",
        (("每日推荐能量摄入范围", "energy_kcal_per_day"),),
    ),
)
RATIO_ITEMS = (
    ("每日菜单中三大营养素比例范围", "macro_ratio_percent", "%energy"),
    ("每日菜单中脂肪酸比例范围", "fatty_acid_ratio", "ratio"),
)


def build_extraction_item_specs() -> dict[str, dict[str, str]]:
    specs: dict[str, dict[str, str]] = {
        **{
            name: {
                "metric_key": key,
                "mode": "single_value",
                "unit": "types/day",
                "scope": "per_day",
                "operator_hint": SINGLE_VALUE_OPERATOR,
                "target_hint": NUMBER_PLACEHOLDER,
            }
            for name, key in SINGLE_VALUE_ITEMS
        },
        "是否三餐全部使用精制谷物": {
            "metric_key": "refined_grains_all_meals",
            "mode": "boolean",
            "unit": "boolean",
            "scope": "whole_menu",
            "operator_hint": "boolean_equals",
            "target_hint": BOOLEAN_PLACEHOLDER,
        },
    }

    for unit, items in RANGE_ITEM_GROUPS:
        specs.update(
            {
                name: {
                    "metric_key": key,
                    "mode": "range",
                    "unit": unit,
                    "scope": "per_day",
                }
                for name, key in items
            }
        )

    specs.update(
        {
            name: {
                "metric_key": key,
                "mode": "ratio",
                "unit": unit,
                "scope": "per_day",
                "operator_hint": RATIO_OPERATOR,
                "target_hint": RATIO_PLACEHOLDER,
            }
            for name, key, unit in RATIO_ITEMS
        }
    )
    return specs


EXTRACTION_ITEM_SPECS = build_extraction_item_specs()


class FrameworkInputError(ValueError):
    """frameworks.py 的输入或配置异常。"""


def load_extraction_items(file_path: str | Path = EXTRACTION_ITEMS_FILE) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"提取项文件不存在：{path}")

    items = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not items:
        raise FrameworkInputError(f"提取项文件为空：{path}")
    return items


def build_constraint_template_items(extraction_items: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for display_name in extraction_items:
        try:
            spec = EXTRACTION_ITEM_SPECS[display_name]
        except KeyError as exc:
            raise FrameworkInputError(
                f"提取项未配置映射：{display_name}"
            ) from exc
        item: dict[str, Any] = {
            "metric_key": spec["metric_key"],
            "display_name": display_name,
            "operator": "between" if spec["mode"] == "range" else spec["operator_hint"],
            "unit": spec["unit"],
            "scope": spec["scope"],
        }
        if spec["mode"] == "range":
            item["min_value"] = NUMBER_PLACEHOLDER
            item["max_value"] = NUMBER_PLACEHOLDER
        else:
            item["target_value"] = spec["target_hint"]
        items.append(item)

    items.append(
        {
            "metric_key": "allergen_ingredient_exclusion",
            "display_name": "过敏原禁忌食材",
            "operator": "not_contains",
            "target_value": ["<填写过敏原或禁忌食材>"],
            "unit": "ingredient",
            "scope": "whole_menu",
        }
    )
    return items


def _normalize_dict_list(raw_data: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(raw_data, dict):
        return [raw_data]
    if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
        return raw_data
    raise FrameworkInputError(f"{label} JSON 必须是对象或对象数组。")


def build_user_summary(user_data: dict[str, Any], user_index: int) -> dict[str, Any]:
    return {
        "user_id": get_user_id(user_data, user_index),
        "age_years": user_data["basic_info"]["age_years"],
        "sex": get_display_label(user_data["basic_info"]["sex"], SEX_LABELS),
        "labor_intensity": get_display_label(
            user_data["physical_activity"]["labor_intensity"], LABOR_INTENSITY_LABELS
        ),
        "goal_type": get_display_label(user_data["goal"]["goal_type"], GOAL_TYPE_LABELS),
        "food_allergy": summarize_food_allergy(user_data),
        "health_status": summarize_health_status(user_data),
    }


def sanitize_route_result(route_result: dict[str, Any]) -> dict[str, Any]:
    """只保留 frameworks.py 需要的路由信息。"""

    selected_guidelines = route_result.get("selected_guidelines", [])
    return {
        "user_id": route_result.get("user_id"),
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
    """构建用于渲染 prompt 的上下文载荷。"""

    extraction_items = extraction_items or load_extraction_items()

    if route_results is None:
        raise FrameworkInputError(
            "缺少 route_results；frameworks.py 不会自动执行指南路由。"
        )

    if len(route_results) != len(users_data):
        raise FrameworkInputError("用户数量与路由结果数量不一致，无法一一对应。")

    users_payload: list[dict[str, Any]] = []
    for index, user_data in enumerate(users_data):
        if validate_inputs:
            validate_user_data(user_data)
        route_result = route_results[index]

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
    template_user_id = (
        payload["users"][0]["user_summary"]["user_id"]
        if len(payload["users"]) == 1
        else "<填写当前用户user_id>"
    )
    output_template_json = json.dumps(
        {
            "version": "user_constraints_v1",
            "user_id": template_user_id,
            "dietary_constraints": build_constraint_template_items(payload["extraction_items"]),
            "exercise_constraints": [
                {
                    "item_name": "<填写运动约束名称>",
                    "value": "<填写数字或枚举值>",
                    "unit": "<填写明确单位，如min/day或times/week>",
                    "frequency_or_duration": "<填写频次或时长说明>",
                }
            ],
            "special_notes": ["<填写无法量化但必须保留的说明>"],
        },
        ensure_ascii=False,
        indent=2,
    )
    return dedent(
        """
        你是一名医学与营养指南信息抽取助手。
        你的任务是根据输入的用户基础信息和对应指南文件，抽取只适用于该用户、且可被程序直接校验的结构化约束，并输出为便于程序直接读取的 JSON。

        工作目标：
        1. 从对应指南中抽取当前输入用户适用的、可量化且可程序校验的运动与饮食约束。

        抽取原则：
        1. 如果指南没有给出明确数值、范围、阈值或可枚举要求，不要编造；该项可以不输出。
        2. 如果多个指南对同一指标给出不同限制，优先保留更适合该用户疾病状态的限制，不要额外输出来源说明字段。
        3. 如果指南文件为图片型 PDF，请调用合适的工具读取其文本。

        输出要求：
        1. 把输出直接保存为本地 JSON 文件，默认保存路径为"knowledge/{{user_id}}_constraints.json"；其中 user_id 必须替换为当前用户的真实 user_id，例如 "knowledge/user_1_constraints.json"。
        2. 以下 JSON 模板就是唯一的输出字段定义标准，请严格按该结构填写。
        3. 如果某一项在当前指南中没有明确可校验规则，可以不输出该项。
        4. 下方模板中的尖括号内容只是填写提示，实际输出时必须替换成真实值，不能原样保留。

        请按以下 JSON 模板输出：
        {output_template_json}

        以下是本次输入：
        {users_json}
        """
    ).strip().format(
        output_template_json=output_template_json,
        users_json=users_json,
    )


def build_framework_prompt_from_data(
    users_data: dict[str, Any] | list[dict[str, Any]],
    route_results: dict[str, Any] | list[dict[str, Any]] | None = None,
    extraction_items_path: str | Path | None = None,
    validate_inputs: bool = True,
) -> dict[str, Any]:
    """从已准备好的用户数据和路由结果生成 framework payload 与 prompt。"""

    normalized_users = ensure_user_ids(_normalize_dict_list(users_data, "输入"))
    if route_results is None:
        raise FrameworkInputError(
            "build_framework_prompt_from_data() 缺少 route_results。"
            "请先运行 User_Profiling.py。"
        )
    normalized_routes = _normalize_dict_list(route_results, "路由")
    extraction_items = load_extraction_items(extraction_items_path or EXTRACTION_ITEMS_FILE)
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

    if route_path is None:
        raise FrameworkInputError(
            "build_framework_prompt_from_file() 缺少 route_path。"
            "请先传入 User_Profiling.py 输出的 route JSON。"
        )
    return build_framework_prompt_from_data(
        load_user_input(input_path),
        route_results=load_user_input(route_path),
        extraction_items_path=extraction_items_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据用户输入和已生成的路由结果，构建用于 LLM 抽取限制信息的 prompt。"
    )
    parser.add_argument("--input", required=True, help="用户输入 JSON，支持单用户或多用户")
    parser.add_argument("--route", required=True, help="必填：来自 User_Profiling.py 的路由结果 JSON，支持单用户或多用户")
    parser.add_argument("--extraction_items", default=str(EXTRACTION_ITEMS_FILE), help="可选：指南提取信息文件路径")
    parser.add_argument("--output_prompt", help="可选：将 LLM prompt 写入文件")
    parser.add_argument("--output_payload", help="可选：将结构化上下文载荷写入 JSON 文件，便于后续调试")
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
        Path(args.output_payload).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.output_prompt:
        Path(args.output_prompt).write_text(prompt, encoding="utf-8")


if __name__ == "__main__":
    main()
