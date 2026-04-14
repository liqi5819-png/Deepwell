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
    calculate_bmi,
    ensure_user_ids,
    get_display_label,
    get_user_id,
    load_user_input,
    summarize_food_allergy,
    summarize_health_status,
    validate_user_data,
)
from tools.knowledge import resolve_user_constraints_path


ROOT_DIR = Path(__file__).resolve().parent.parent


class LifestyleInputError(ValueError):
    """lifestyle.py 的输入或配置异常。"""


def _normalize_dict_list(raw_data: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(raw_data, dict):
        return [raw_data]
    if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
        return raw_data
    raise LifestyleInputError(f"{label} JSON 必须是对象或对象数组。")


def _ensure_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise LifestyleInputError(f"{field_name} 必须是数组。")


def build_user_summary(user_data: dict[str, Any], user_index: int) -> dict[str, Any]:
    return {
        "user_id": get_user_id(user_data, user_index),
        "age_years": user_data["basic_info"]["age_years"],
        "sex": get_display_label(user_data["basic_info"]["sex"], SEX_LABELS),
        "height_cm": user_data["basic_info"]["height_cm"],
        "weight_kg": user_data["basic_info"]["weight_kg"],
        "waist_cm": user_data["basic_info"]["waist_cm"],
        "bmi": calculate_bmi(user_data),
        "labor_intensity": get_display_label(
            user_data["physical_activity"]["labor_intensity"], LABOR_INTENSITY_LABELS
        ),
        "goal_type": get_display_label(user_data["goal"]["goal_type"], GOAL_TYPE_LABELS),
        "food_allergy": summarize_food_allergy(user_data),
        "health_status": summarize_health_status(user_data),
    }


def _normalize_constraints_payload(
    raw_constraints: Any,
    target_user_id: str,
) -> dict[str, Any]:
    if not isinstance(raw_constraints, dict):
        raise LifestyleInputError("用户约束文件必须是 JSON 对象。")

    if "generated_for_users" in raw_constraints:
        users = _ensure_list(raw_constraints.get("generated_for_users"), "generated_for_users")
        matched_user = next(
            (
                item
                for item in users
                if str(item.get("user_id", "")).strip() == target_user_id
            ),
            None,
        )
        if matched_user is None:
            raise LifestyleInputError(f"约束文件中未找到用户：{target_user_id}")

        return {
            "version": raw_constraints.get("version"),
            "user_id": target_user_id,
            "user_summary": matched_user.get("user_summary"),
            "source_guidelines": _ensure_list(
                matched_user.get("source_guidelines"), "source_guidelines"
            ),
            "dietary_constraints": _ensure_list(
                matched_user.get("dietary_constraints")
                or matched_user.get("restriction_items"),
                "dietary_constraints/restriction_items",
            ),
            "exercise_constraints": _ensure_list(
                matched_user.get("exercise_constraints")
                or matched_user.get("exercise_restrictions"),
                "exercise_constraints/exercise_restrictions",
            ),
            "special_notes": _ensure_list(matched_user.get("special_notes"), "special_notes"),
        }

    user_id = str(raw_constraints.get("user_id", "")).strip()
    if user_id and user_id != target_user_id:
        raise LifestyleInputError(
            f"约束文件用户 ID 不匹配：期望 {target_user_id}，实际 {user_id}"
        )

    if "dietary_constraints" not in raw_constraints and "exercise_constraints" not in raw_constraints:
        raise LifestyleInputError("约束文件结构无法识别：缺少 dietary_constraints/exercise_constraints。")

    return {
        "version": raw_constraints.get("version"),
        "user_id": target_user_id,
        "user_summary": raw_constraints.get("user_summary"),
        "source_guidelines": _ensure_list(raw_constraints.get("source_guidelines"), "source_guidelines"),
        "dietary_constraints": _ensure_list(
            raw_constraints.get("dietary_constraints"), "dietary_constraints"
        ),
        "exercise_constraints": _ensure_list(
            raw_constraints.get("exercise_constraints"), "exercise_constraints"
        ),
        "special_notes": _ensure_list(raw_constraints.get("special_notes"), "special_notes"),
    }


def load_user_constraints(user_id: str, constraints_path: str | Path | None = None) -> dict[str, Any]:
    resolved_path = (
        Path(constraints_path)
        if constraints_path is not None
        else resolve_user_constraints_path(user_id)
    )
    if not resolved_path.exists():
        raise FileNotFoundError(f"用户约束文件不存在：{resolved_path}")
    if not resolved_path.is_file():
        raise FileNotFoundError(f"用户约束路径不是文件：{resolved_path}")

    raw_constraints = load_user_input(resolved_path)
    normalized_constraints = _normalize_constraints_payload(raw_constraints, user_id)
    normalized_constraints["constraints_file"] = str(resolved_path)
    return normalized_constraints


def _format_constraint_condition(item: dict[str, Any]) -> str:
    operator = str(item.get("operator", "")).strip()
    unit = str(item.get("unit", "")).strip()
    target_value = item.get("target_value")
    min_value = item.get("min_value")
    max_value = item.get("max_value")

    if operator == "between":
        value_text = f"{min_value} - {max_value}"
    elif operator == "boolean_equals":
        value_text = "是" if target_value is True else "否" if target_value is False else str(target_value)
        unit = ""
    elif operator == "not_contains":
        if isinstance(target_value, list):
            value_text = "不包含 " + "、".join(str(value) for value in target_value)
        else:
            value_text = f"不包含 {target_value}"
        unit = ""
    elif operator == "enum_equals":
        value_text = str(target_value)
    elif operator in {"enum_equals", "=", ">=", "<=", "<", ">"}:
        value_text = f"{operator} {target_value}"
    else:
        value_text = str(target_value if target_value is not None else "")

    return f"{value_text} {unit}".strip()


def _build_dietary_constraint_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        display_name = str(item.get("display_name") or item.get("metric_key") or "未命名约束")
        condition = _format_constraint_condition(item)
        lines.append(f"- {display_name}: {condition}")
    return lines or ["- 无"]


def _build_exercise_constraint_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        item_name = str(item.get("item_name") or "未命名运动约束")
        value = item.get("value")
        unit = str(item.get("unit", "")).strip()
        frequency = str(item.get("frequency_or_duration", "")).strip()
        condition_parts = [str(value).strip() if value is not None else "", unit, frequency]
        condition = "，".join(part for part in condition_parts if part)
        lines.append(f"- {item_name}: {condition}" if condition else f"- {item_name}")
    return lines or ["- 无"]


def build_lifestyle_payload(
    user_data: dict[str, Any],
    constraints_data: dict[str, Any] | None = None,
    constraints_path: str | Path | None = None,
    validate_inputs: bool = True,
) -> dict[str, Any]:
    if validate_inputs:
        validate_user_data(user_data)

    normalized_user = ensure_user_ids([user_data])[0]
    user_summary = build_user_summary(normalized_user, 0)
    normalized_constraints = (
        constraints_data
        if constraints_data is not None
        else load_user_constraints(user_summary["user_id"], constraints_path)
    )

    return {
        "task_name": "lifestyle_suggestion_prompt",
        "version": "0.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "该结构用于给 LLM 生成生活方式建议。",
        "user_summary": user_summary,
        "constraints_file": normalized_constraints.get("constraints_file"),
        "user_constraints": normalized_constraints,
    }


def build_lifestyle_prompt(payload: dict[str, Any]) -> str:
    user_summary = payload["user_summary"]
    user_constraints = payload["user_constraints"]
    dietary_lines = "\n".join(
        _build_dietary_constraint_lines(user_constraints.get("dietary_constraints", []))
    )
    exercise_lines = "\n".join(
        _build_exercise_constraint_lines(user_constraints.get("exercise_constraints", []))
    )
    special_notes = user_constraints.get("special_notes", [])
    special_notes_lines = (
        "\n".join(f"- {note}" for note in special_notes) if special_notes else "- 无"
    )

    return dedent(
        """
        你是一名生活方式干预助手。
        你的任务是基于用户信息和用户级约束，生成 1 天可执行的生活方式建议，包括饮食与运动。

        工作原则：
        1. 如存在疾病状态、过敏或禁忌，建议中必须规避对应风险。
        2. 如果约束之间存在冲突，优先保证安全性，并说明调整理由。
        3. 不要编造输入中没有给出的医学禁忌、疾病结论或额外约束。

        输出要求：
        1. 使用中文输出。
        2. 按以下结构输出：
           一、饮食方案
           早餐：
           午餐：
           晚餐：
           全天控制：
           二、运动建议
        3. 早餐、午餐、晚餐都要写出具体食材及数量，尽量采用便于后续程序解析和营养成分计算的格式化表达。
        4. 每餐至少包含“食材”和“数量”两类信息；数量必须明确，不要使用“适量”“少许”等模糊描述。
        5. 全天控制部分要单独给出烹调油、盐、添加糖的控制建议；如约束中有能量、钠、营养比例等要求，也要体现在方案中。
        6. 运动建议必须包含运动类型、建议时长或频次、强度和注意事项。
        7. 不要输出文件路径，不要引用生成过程说明。

        【用户信息】
        - user_id：{user_id}
        - 年龄：{age_years} 岁
        - 性别：{sex}
        - 身高：{height_cm} cm
        - 体重：{weight_kg} kg
        - 腰围：{waist_cm} cm
        - BMI：{bmi}
        - 体力劳动强度：{labor_intensity}
        - 目标：{goal_type}
        - 食物过敏：{food_allergy}
        - 健康状态：{health_status}

        【饮食约束摘要】
        {dietary_lines}

        【运动约束摘要】
        {exercise_lines}

        【特殊说明】
        {special_notes_lines}
        """
    ).strip().format(
        user_id=user_summary["user_id"],
        age_years=user_summary["age_years"],
        sex=user_summary["sex"],
        height_cm=user_summary["height_cm"],
        weight_kg=user_summary["weight_kg"],
        waist_cm=user_summary["waist_cm"],
        bmi=user_summary["bmi"],
        labor_intensity=user_summary["labor_intensity"],
        goal_type=user_summary["goal_type"],
        food_allergy=user_summary["food_allergy"],
        health_status=user_summary["health_status"],
        dietary_lines=dietary_lines,
        exercise_lines=exercise_lines,
        special_notes_lines=special_notes_lines,
    )


def build_lifestyle_prompt_from_data(
    user_data: dict[str, Any] | list[dict[str, Any]],
    constraints_data: dict[str, Any] | None = None,
    constraints_path: str | Path | None = None,
    validate_inputs: bool = True,
) -> dict[str, Any]:
    normalized_users = ensure_user_ids(_normalize_dict_list(user_data, "输入"))
    if len(normalized_users) != 1:
        raise LifestyleInputError("lifestyle.py 当前仅支持单用户输入。")

    payload = build_lifestyle_payload(
        normalized_users[0],
        constraints_data=constraints_data,
        constraints_path=constraints_path,
        validate_inputs=validate_inputs,
    )
    return {
        "user_data": normalized_users[0],
        "payload": payload,
        "prompt": build_lifestyle_prompt(payload),
    }


def build_lifestyle_prompt_from_file(
    input_path: str | Path,
    constraints_path: str | Path | None = None,
) -> dict[str, Any]:
    return build_lifestyle_prompt_from_data(
        load_user_input(input_path),
        constraints_path=constraints_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据用户输入与用户约束文件，构建用于 LLM 生成生活方式建议的 prompt。"
    )
    parser.add_argument("--input", required=True, help="用户输入 JSON，当前仅支持单用户")
    parser.add_argument(
        "--constraints",
        help="可选：用户约束 JSON 文件；未传时默认从 knowledge/{user_id}_constraints.json 读取",
    )
    parser.add_argument("--output_prompt", help="可选：将 lifestyle prompt 写入文件")
    parser.add_argument("--output_payload", help="可选：将结构化上下文载荷写入 JSON 文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_lifestyle_prompt_from_file(
        args.input,
        constraints_path=args.constraints,
    )
    payload = result["payload"]
    prompt = result["prompt"]

    print("===== Lifestyle Payload =====")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("===== Lifestyle Prompt =====")
    print(prompt)

    if args.output_payload:
        Path(args.output_payload).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.output_prompt:
        Path(args.output_prompt).write_text(prompt, encoding="utf-8")


if __name__ == "__main__":
    main()
