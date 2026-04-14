from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from tools.knowledge import (
    GuidelineMetadata,
    find_candidate_guidelines,
    get_guideline_registry,
    select_guidelines_for_user,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
ROUTE_OUTPUT_FILE = ROOT_DIR / "route_output.json"

REQUIRED_TOP_LEVEL_FIELDS = [
    "basic_info",
    "physical_activity",
    "goal",
    "food_allergy",
    "health_status",
]

REQUIRED_BASIC_INFO_FIELDS = ["age_years", "sex", "height_cm", "weight_kg", "waist_cm"]
REQUIRED_PHYSICAL_ACTIVITY_FIELDS = ["labor_intensity"]
REQUIRED_GOAL_FIELDS = ["goal_type"]
REQUIRED_FOOD_ALLERGY_FIELDS = ["has_food_allergy", "allergy_foods"]
REQUIRED_HEALTH_STATUS_FIELDS = [
    "healthy",
    "diabetes",
    "fatty_liver",
    "chronic_kidney_disease",
    "hypertension",
    "hyperuricemia_or_gout",
    "hyperthyroidism",
]

SEX_LABELS = {
    "male": "男",
    "female": "女",
}

LABOR_INTENSITY_LABELS = {
    "light": "轻体力劳动",
    "moderate": "中等体力劳动",
    "heavy": "重体力劳动",
}

GOAL_TYPE_LABELS = {
    "weight_loss": "减重",
    "healthy_lifestyle": "健康生活方式",
}


class InputDataError(ValueError):
    """输入数据结构异常。"""


def load_user_input(file_path: str | Path) -> Any:
    """读取标准化用户输入 JSON 文件。"""

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在：{path}")
    if not path.is_file():
        raise FileNotFoundError(f"输入路径不是文件：{path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise InputDataError(f"输入文件编码读取失败，请确认是 UTF-8：{path}") from exc
    except json.JSONDecodeError as exc:
        raise InputDataError(
            f"JSON 解析失败：{path}，第 {exc.lineno} 行第 {exc.colno} 列附近格式有误。"
        ) from exc


def normalize_user_inputs(raw_data: Any) -> list[dict[str, Any]]:
    if isinstance(raw_data, dict):
        return [raw_data]
    if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
        return raw_data
    raise InputDataError("输入 JSON 必须是单个对象，或由多个对象组成的数组。")


def get_user_id(user_data: dict[str, Any], user_index: int) -> str:
    raw_user_id = str(user_data.get("user_id", "")).strip()
    return raw_user_id or f"user_{user_index + 1}"


def ensure_user_ids(users_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_users: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, user_data in enumerate(users_data):
        normalized_user = dict(user_data)
        user_id = get_user_id(normalized_user, index)
        if user_id in seen_ids:
            raise InputDataError(f"用户 ID 重复：{user_id}")
        normalized_user["user_id"] = user_id
        normalized_users.append(normalized_user)
        seen_ids.add(user_id)

    return normalized_users


def restore_user_input_shape(users_data: list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]]:
    return users_data[0] if len(users_data) == 1 else users_data


def validate_user_data(user_data: dict[str, Any]) -> None:
    """做最基本的字段存在性检查。"""

    _require_fields(user_data, REQUIRED_TOP_LEVEL_FIELDS, parent_name="root")
    _require_fields(user_data["basic_info"], REQUIRED_BASIC_INFO_FIELDS, parent_name="basic_info")
    _require_fields(
        user_data["physical_activity"],
        REQUIRED_PHYSICAL_ACTIVITY_FIELDS,
        parent_name="physical_activity",
    )
    _require_fields(user_data["goal"], REQUIRED_GOAL_FIELDS, parent_name="goal")
    _require_fields(
        user_data["food_allergy"],
        REQUIRED_FOOD_ALLERGY_FIELDS,
        parent_name="food_allergy",
    )
    _require_fields(
        user_data["health_status"],
        REQUIRED_HEALTH_STATUS_FIELDS,
        parent_name="health_status",
    )


def _require_fields(data: dict[str, Any], required_fields: list[str], parent_name: str) -> None:
    missing = [field for field in required_fields if field not in data]
    if missing:
        missing_str = ", ".join(missing)
        raise InputDataError(f"缺少关键字段：{parent_name}.{missing_str}")


def extract_user_profile_tags(user_data: dict[str, Any]) -> list[str]:
    """从输入中提取可用于指南路由的用户标签。"""

    health_status = user_data["health_status"]
    goal_type = str(user_data["goal"].get("goal_type", "")).strip()
    bmi = calculate_bmi(user_data)
    tags: list[str] = []

    if health_status.get("healthy") is True:
        tags.append("healthy")

    diabetes = health_status.get("diabetes", {})
    if diabetes.get("has_diabetes") is True:
        tags.append("diabetes")
        diabetes_type = diabetes.get("diabetes_type")
        if diabetes_type:
            tags.append(str(diabetes_type))
        if diabetes.get("uses_insulin") is True:
            tags.append("uses_insulin")

    fatty_liver = health_status.get("fatty_liver", {})
    if fatty_liver.get("has_fatty_liver") is True:
        tags.append("fatty_liver")
        severity = fatty_liver.get("severity")
        if severity:
            tags.append(f"fatty_liver_{severity}")

    ckd = health_status.get("chronic_kidney_disease", {})
    if ckd.get("has_ckd") is True:
        tags.append("chronic_kidney_disease")
        stage_group = ckd.get("stage_group")
        if stage_group:
            tags.append(f"ckd_{stage_group}")

    hypertension = health_status.get("hypertension", {})
    if hypertension.get("has_hypertension") is True:
        tags.append("hypertension")

    hyperuricemia_or_gout = health_status.get("hyperuricemia_or_gout", {})
    if hyperuricemia_or_gout.get("has_hyperuricemia_or_gout") is True:
        tags.append("hyperuricemia_or_gout")

    hyperthyroidism = health_status.get("hyperthyroidism", {})
    if hyperthyroidism.get("has_hyperthyroidism") is True:
        tags.append("hyperthyroidism")

    if bmi < 24.0:
        tags.append("bmi_lt_24")
    elif bmi < 32.5:
        tags.append("bmi_24_to_32_5")
    else:
        tags.append("bmi_ge_32_5")

    if goal_type:
        tags.append(goal_type)

    return sorted(set(tags))


def summarize_health_status(user_data: dict[str, Any]) -> str:
    """把 health_status 转成适合写入 prompt 的中文摘要。"""

    health_status = user_data["health_status"]
    items: list[str] = []

    if health_status.get("healthy") is True:
        items.append("健康")

    diabetes = health_status.get("diabetes", {})
    if diabetes.get("has_diabetes") is True:
        diabetes_text = "糖尿病"
        if diabetes.get("diabetes_type"):
            diabetes_text += f"（{diabetes['diabetes_type']}）"
        if diabetes.get("uses_insulin") is True:
            diabetes_text += "，正在使用胰岛素"
        items.append(diabetes_text)

    fatty_liver = health_status.get("fatty_liver", {})
    if fatty_liver.get("has_fatty_liver") is True:
        severity = fatty_liver.get("severity")
        if severity:
            items.append(f"脂肪肝（程度：{severity}）")
        else:
            items.append("脂肪肝")

    ckd = health_status.get("chronic_kidney_disease", {})
    if ckd.get("has_ckd") is True:
        stage_group = ckd.get("stage_group")
        if stage_group:
            items.append(f"慢性肾病（分期组：{stage_group}）")
        else:
            items.append("慢性肾病")

    if health_status.get("hypertension", {}).get("has_hypertension") is True:
        items.append("高血压")

    if (
        health_status.get("hyperuricemia_or_gout", {}).get("has_hyperuricemia_or_gout")
        is True
    ):
        items.append("高尿酸或痛风")

    if health_status.get("hyperthyroidism", {}).get("has_hyperthyroidism") is True:
        items.append("甲状腺功能亢进")

    return "；".join(items) if items else "未提供明确健康状态信息"


def summarize_food_allergy(user_data: dict[str, Any]) -> str:
    food_allergy = user_data["food_allergy"]
    if not food_allergy.get("has_food_allergy"):
        return "无"

    allergy_foods = food_allergy.get("allergy_foods") or []
    if not allergy_foods:
        return "有食物过敏史，但未提供具体过敏食物"
    return "食物过敏：" + "、".join(str(item) for item in allergy_foods)


def get_display_label(raw_value: Any, mapping: dict[str, str]) -> str:
    if raw_value is None:
        return "未提供"
    return mapping.get(str(raw_value), str(raw_value))


def calculate_bmi(user_data: dict[str, Any]) -> float:
    height_cm = float(user_data["basic_info"]["height_cm"])
    weight_kg = float(user_data["basic_info"]["weight_kg"])
    height_m = height_cm / 100
    if height_m <= 0:
        raise InputDataError("身高必须大于 0，无法计算 BMI。")
    return round(weight_kg / (height_m * height_m), 2)


def select_guideline_files(
    user_data: dict[str, Any], knowledge_base: Optional[dict[str, GuidelineMetadata]] = None
) -> dict[str, Any]:
    """根据 knowledge.py 中的可配置映射规则选择指南。"""

    goal_type = str(user_data["goal"]["goal_type"])
    bmi = calculate_bmi(user_data)
    health_status = user_data["health_status"]

    return select_guidelines_for_user(
        goal_type=goal_type,
        bmi=bmi,
        health_status=health_status,
        registry=knowledge_base,
    )


def build_base_prompt(user_data: dict[str, Any]) -> str:
    """生成供 LLM 使用的基础 prompt。"""

    basic_info = user_data["basic_info"]
    physical_activity = user_data["physical_activity"]
    goal = user_data["goal"]

    prompt_lines = [
        "你是一名生活方式干预助手。请根据以下用户信息，生成 1 天方案，包括每日食谱和运动建议。",
        "",
        "用户核心信息：",
        f"- 年龄：{basic_info['age_years']} 岁",
        f"- 性别：{get_display_label(basic_info['sex'], SEX_LABELS)}",
        f"- 身高：{basic_info['height_cm']} cm",
        f"- 体重：{basic_info['weight_kg']} kg",
        f"- 腰围：{basic_info['waist_cm']} cm",
        f"- 体力劳动强度：{get_display_label(physical_activity['labor_intensity'], LABOR_INTENSITY_LABELS)}",
        f"- 目标类型：{get_display_label(goal['goal_type'], GOAL_TYPE_LABELS)}",
        f"- 过敏信息：{summarize_food_allergy(user_data)}",
        f"- 健康状态：{summarize_health_status(user_data)}",
        "",
        "请完成以下任务：",
        "1. 生成 1 天饮食方案，包括早餐、午餐、晚餐。",
        "2. 每餐给出简洁的食物建议、搭配方式和份量描述，要明确写出具体用到的食材和份量。",
        "3. 要明确写出每天使用烹调油、糖和盐的份量。",
        "4. 提供 1 天运动建议，说明运动类型、建议时长、强度和注意事项。",
        "5. 如存在疾病状态或食物过敏，请在建议中体现规避或适配原则。",
    ]

    return "\n".join(prompt_lines)


def build_base_prompt_from_data(user_data: dict[str, Any]) -> dict[str, Any]:
    validate_user_data(user_data)
    return {
        "user_data": user_data,
        "prompt": build_base_prompt(user_data),
        "route_result": route_user_to_guideline(user_data),
    }


def build_base_prompt_from_file(input_path: str | Path) -> dict[str, Any]:
    """从输入文件生成基础 prompt 与路由结果。"""

    users_data = ensure_user_ids(normalize_user_inputs(load_user_input(input_path)))
    if len(users_data) != 1:
        raise InputDataError("build_base_prompt_from_file() 仅支持单用户输入。")
    return build_base_prompt_from_data(users_data[0])


def route_user_to_guideline(
    user_data: dict[str, Any], knowledge_base: Optional[dict[str, GuidelineMetadata]] = None
) -> dict[str, Any]:
    """根据用户标签和映射规则返回指南路由结果。"""

    profile_tags = extract_user_profile_tags(user_data)
    registry = (
        get_guideline_registry(enabled_only=False)
        if knowledge_base is None
        else knowledge_base
    )

    candidate_guidelines = find_candidate_guidelines(
        profile_tags,
        enabled_only=False,
        registry=registry,
    )
    mapped_guideline_result = select_guideline_files(user_data, knowledge_base=registry)

    return {
        "user_id": user_data.get("user_id"),
        "profile_tags": profile_tags,
        "bmi": mapped_guideline_result["bmi"],
        "mapping_rule": mapped_guideline_result["base_rule"],
        "selected_guidelines": mapped_guideline_result["selected_guidelines"],
        "candidate_guidelines": [item.to_dict() for item in candidate_guidelines],
        "selected_guideline": mapped_guideline_result["selected_guidelines"][0]
        if len(mapped_guideline_result["selected_guidelines"]) == 1
        else None,
        "reason": "已根据 knowledge.py 中配置的基础映射和疾病附加规则完成路由。",
        "disease_reasons": mapped_guideline_result["disease_reasons"],
    }


def save_text_output(content: str, output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(content, encoding="utf-8")


def save_json_output(content: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据标准化用户输入 JSON 生成基础 prompt，并输出指南路由结果。"
    )
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--output_prompt", help="可选：将生成的 prompt 写入文件")
    parser.add_argument("--output_route", help="可选：将路由结果写入 JSON 文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_base_prompt_from_file(args.input)
    prompt = result["prompt"]
    route_result = result["route_result"]

    print("===== 基础 Prompt =====")
    print(prompt)
    print()
    print("===== 路由结果 =====")
    print(json.dumps(route_result, ensure_ascii=False, indent=2))

    if args.output_prompt:
        save_text_output(prompt, args.output_prompt)

    if args.output_route:
        save_json_output(route_result, args.output_route)


if __name__ == "__main__":
    main()
