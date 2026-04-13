from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from generate_prompt_from_input import (
    GOAL_TYPE_LABELS,
    LABOR_INTENSITY_LABELS,
    SEX_LABELS,
    calculate_bmi,
    get_display_label,
    load_user_input,
    summarize_food_allergy,
    summarize_health_status,
    validate_user_data,
)


KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
DEFAULT_RESTRICTION_FILE = KNOWLEDGE_DIR / "限制信息汇总_V2.0.json"
DEFAULT_NUTRITION_FILE = KNOWLEDGE_DIR / "食物营养成分明细-V1.0.json"

RECIPE_GROUPS = {
    "breakfast_staple": {"全谷物", "精制谷物", "薯类", "杂豆"},
    "breakfast_protein": {"液态奶", "酸奶", "豆浆"},
    "breakfast_vegetable": {
        "叶菜类",
        "十字花科蔬菜",
        "根茎类蔬菜",
        "瓜菜类",
        "茄果类",
        "菌菇类",
        "豆荚类蔬菜",
        "葱蒜类",
    },
    "breakfast_fruit": {"常见水果", "浆果类水果", "瓜果类水果", "热带水果"},
    "lunch_dinner_staple": {"全谷物", "精制谷物", "薯类", "杂豆"},
    "lunch_dinner_protein": {
        "鱼类",
        "虾贝类",
        "禽肉类",
        "畜肉类",
        "蛋类",
        "豆腐",
        "其他豆制品",
        "整豆类",
    },
    "lunch_dinner_vegetable": {
        "叶菜类",
        "十字花科蔬菜",
        "根茎类蔬菜",
        "瓜菜类",
        "茄果类",
        "菌菇类",
        "豆荚类蔬菜",
        "葱蒜类",
    },
    "lunch_dinner_fruit": {"常见水果", "浆果类水果", "瓜果类水果", "热带水果"},
    "dinner_protein_soy": {"豆腐", "其他豆制品"},
    "dinner_fruit": {"常见水果", "浆果类水果", "瓜果类水果", "热带水果"},
}

FIXED_SLOT_DEFINITIONS = [
    {
        "slot_id": "breakfast_slot_1",
        "meal_name": "早餐",
        "slot_index": 1,
        "slot_label": "主食",
        "candidate_source": "breakfast_staple",
        "amount": 70,
        "unit": "g",
    },
    {
        "slot_id": "breakfast_slot_2",
        "meal_name": "早餐",
        "slot_index": 2,
        "slot_label": "蛋白来源",
        "candidate_source": "breakfast_protein",
        "amount": 300,
        "unit": "mL",
    },
    {
        "slot_id": "breakfast_slot_3",
        "meal_name": "早餐",
        "slot_index": 3,
        "slot_label": "蔬菜",
        "candidate_source": "breakfast_vegetable",
        "amount": 150,
        "unit": "g",
    },
    {
        "slot_id": "breakfast_slot_4",
        "meal_name": "早餐",
        "slot_index": 4,
        "slot_label": "水果",
        "candidate_source": "breakfast_fruit",
        "amount": 150,
        "unit": "g",
    },
    {
        "slot_id": "lunch_slot_1",
        "meal_name": "午餐",
        "slot_index": 1,
        "slot_label": "主食",
        "candidate_source": "lunch_dinner_staple",
        "amount": 80,
        "unit": "g",
    },
    {
        "slot_id": "lunch_slot_2",
        "meal_name": "午餐",
        "slot_index": 2,
        "slot_label": "蛋白来源",
        "candidate_source": "lunch_dinner_protein",
        "amount": 100,
        "unit": "g",
    },
    {
        "slot_id": "lunch_slot_3",
        "meal_name": "午餐",
        "slot_index": 3,
        "slot_label": "蔬菜",
        "candidate_source": "lunch_dinner_vegetable",
        "amount": 200,
        "unit": "g",
    },
    {
        "slot_id": "lunch_slot_4",
        "meal_name": "午餐",
        "slot_index": 4,
        "slot_label": "水果",
        "candidate_source": "lunch_dinner_fruit",
        "amount": 150,
        "unit": "g",
    },
    {
        "slot_id": "dinner_slot_1",
        "meal_name": "晚餐",
        "slot_index": 1,
        "slot_label": "主食",
        "candidate_source": "lunch_dinner_staple",
        "amount": 70,
        "unit": "g",
    },
    {
        "slot_id": "dinner_slot_2",
        "meal_name": "晚餐",
        "slot_index": 2,
        "slot_label": "蛋白来源",
        "candidate_source": "dinner_protein_soy",
        "amount": 60,
        "unit": "g",
    },
    {
        "slot_id": "dinner_slot_3",
        "meal_name": "晚餐",
        "slot_index": 3,
        "slot_label": "蔬菜",
        "candidate_source": "lunch_dinner_vegetable",
        "amount": 180,
        "unit": "g",
    },
    {
        "slot_id": "dinner_slot_4",
        "meal_name": "晚餐",
        "slot_index": 4,
        "slot_label": "水果",
        "candidate_source": "dinner_fruit",
        "amount": 100,
        "unit": "g",
    },
]

MAX_CANDIDATE_SLOT_REUSE = 2


class CandidateGenerationError(ValueError):
    """候选食材脚本输入异常。"""


def load_json_file(file_path: str | Path) -> Any:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateGenerationError(
            f"JSON 解析失败：{path}，第 {exc.lineno} 行第 {exc.colno} 列附近格式有误。"
        ) from exc


def normalize_user_inputs(raw_data: Any) -> list[dict[str, Any]]:
    if isinstance(raw_data, dict):
        return [raw_data]
    if isinstance(raw_data, list) and all(isinstance(item, dict) for item in raw_data):
        return raw_data
    raise CandidateGenerationError("输入用户 JSON 必须是单个对象或对象数组。")


def build_user_summary(user_data: dict[str, Any], index: int) -> dict[str, Any]:
    basic_info = user_data["basic_info"]
    physical_activity = user_data["physical_activity"]
    goal = user_data["goal"]
    return {
        "user_id": f"user_{index + 1}",
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


def get_matching_rule_key(user_data: dict[str, Any]) -> str:
    goal_type = str(user_data["goal"].get("goal_type"))
    bmi = calculate_bmi(user_data)

    if goal_type == "healthy_lifestyle":
        return "healthy_lifestyle_bmi_lt_28" if bmi < 28 else "healthy_lifestyle_bmi_gte_28"
    if goal_type == "weight_loss":
        return "weight_loss_bmi_gt_28" if bmi > 28 else "weight_loss_bmi_gt_18_5_lte_28"
    raise CandidateGenerationError(f"暂不支持的 goal_type：{goal_type}")


def select_restriction_profile(
    user_data: dict[str, Any],
    restriction_data: dict[str, Any],
    user_index: int,
) -> dict[str, Any]:
    """兼容两种限制信息结构：
    1. user_rule_sets: 通用规则集，需要按 goal_type + BMI 匹配
    2. generated_for_users: LLM 已经输出的用户级限制信息
    """

    if "generated_for_users" in restriction_data:
        target_user_id = f"user_{user_index + 1}"
        for item in restriction_data["generated_for_users"]:
            if item.get("user_id") == target_user_id:
                return item
        raise CandidateGenerationError(
            f"限制信息文件中未找到 {target_user_id} 对应的用户级限制信息。"
        )

    if "user_rule_sets" in restriction_data:
        rule_key = get_matching_rule_key(user_data)
        rule = restriction_data["user_rule_sets"].get(rule_key)
        if rule is None:
            raise CandidateGenerationError(f"限制信息文件中未找到规则：{rule_key}")
        return {
            "user_id": f"user_{user_index + 1}",
            "rule_key": rule_key,
            "label": rule.get("label"),
            "diet_restrictions": rule.get("diet_restrictions", {}),
            "exercise_restrictions": rule.get("exercise_restrictions", []),
            "special_weight_loss_targets": rule.get("special_weight_loss_targets", []),
        }

    raise CandidateGenerationError("限制信息文件缺少可识别结构：未找到 user_rule_sets 或 generated_for_users。")


def parse_daily_energy_limit(restriction_profile: dict[str, Any], user_data: dict[str, Any]) -> Optional[int]:
    """从通用规则文本中提取每日能量上限。

    当前只解析现有 `user_rule_sets` 结构中的平衡类文本。
    若未来改为用户级结构，可直接在限制信息中放标准化字段替代该逻辑。
    """

    if "diet_restrictions" not in restriction_profile:
        return None

    balance_items = restriction_profile.get("diet_restrictions", {}).get("balance", [])
    if not isinstance(balance_items, list):
        return None

    sex = str(user_data["basic_info"]["sex"])
    labor = str(user_data["physical_activity"]["labor_intensity"])
    text = " ".join(str(item) for item in balance_items)

    energy_map = {
        ("male", "light"): ["2250", "1900", "1800"],
        ("male", "moderate"): ["2600", "2200", "2100"],
        ("male", "heavy"): ["3000", "2550", "2400"],
        ("female", "light"): ["1800", "1500", "1450"],
        ("female", "moderate"): ["2100", "1800", "1700"],
        ("female", "heavy"): ["2400", "2000", "1900"],
    }

    candidates = energy_map.get((sex, labor), [])
    for value in candidates:
        if value in text:
            return int(value)
    return None


def derive_filter_policy(user_data: dict[str, Any], restriction_profile: dict[str, Any]) -> dict[str, Any]:
    """把用户状态和限制规则转成食材筛选策略。

    说明：
    - 当前是第一版启发式规则，优先保证“可扩展”和“可解释”
    - 后续可以把更多限制信息标准化成结构字段，再替换掉这里的启发式逻辑
    """

    health_status = user_data["health_status"]
    goal_type = str(user_data["goal"]["goal_type"])
    allergy_foods = {str(item).lower() for item in user_data["food_allergy"].get("allergy_foods", [])}

    policy = {
        "exclude_recipe_groups": set(),
        "avoid_food_keywords": set(allergy_foods),
        "prefer_whole_grains": True,
        "prefer_low_sodium": True,
        "prefer_low_fat": True,
        "prefer_high_fiber": True,
        "max_sodium_mg": 200.0,
        "max_cholesterol_mg": 120.0,
        "max_fat_g": 12.0,
        "max_sfa_g": 3.0,
        "max_energy_kcal": 250.0,
        "min_protein_g": 3.0,
        "min_fiber_g": 1.0,
        "min_vitamin_c_mg": 6.0,
        "daily_energy_limit_kcal": parse_daily_energy_limit(restriction_profile, user_data),
    }

    if goal_type == "weight_loss":
        policy["max_energy_kcal"] = 220.0
        policy["max_fat_g"] = 10.0
        policy["max_sfa_g"] = 2.5

    if health_status.get("hypertension", {}).get("has_hypertension") is True:
        policy["max_sodium_mg"] = 120.0

    if health_status.get("chronic_kidney_disease", {}).get("has_ckd") is True:
        policy["max_sodium_mg"] = min(policy["max_sodium_mg"], 100.0)
        policy["max_protein_g_for_general"] = 20.0

    if health_status.get("hyperuricemia_or_gout", {}).get("has_hyperuricemia_or_gout") is True:
        policy["exclude_recipe_groups"].update({"虾贝类"})
        policy["avoid_food_keywords"].update({"动物内脏"})

    if health_status.get("diabetes", {}).get("has_diabetes") is True:
        policy["prefer_whole_grains"] = True
        policy["exclude_recipe_groups"].update({"精制谷物"})

    if user_data["food_allergy"].get("has_food_allergy") is True:
        for food in user_data["food_allergy"].get("allergy_foods", []):
            policy["avoid_food_keywords"].add(str(food).lower())

    return policy


def is_food_allowed(food: dict[str, Any], slot_name: str, policy: dict[str, Any]) -> bool:
    recipe_group = str(food.get("recipe_group", ""))
    food_name = str(food.get("food_name", "")).lower()

    if recipe_group not in RECIPE_GROUPS[slot_name]:
        return False

    if recipe_group in policy["exclude_recipe_groups"]:
        return False

    if any(keyword and keyword in food_name for keyword in policy["avoid_food_keywords"]):
        return False

    sodium_mg = float(food.get("sodium_mg") or 0)
    fat_g = float(food.get("fat_g") or 0)
    sfa_g = float(food.get("sfa_g") or 0)
    cholesterol_mg = float(food.get("cholesterol_mg") or 0)
    energy_kcal = float(food.get("energy_kcal") or 0)

    if slot_name in {"breakfast_protein", "lunch_dinner_protein", "dairy_or_soy"}:
        if sodium_mg > policy["max_sodium_mg"]:
            return False
        if fat_g > policy["max_fat_g"]:
            return False
        if sfa_g > policy["max_sfa_g"]:
            return False
        if cholesterol_mg > policy["max_cholesterol_mg"]:
            return False

    if slot_name in {"breakfast_staple", "lunch_dinner_staple"} and policy["prefer_whole_grains"]:
        if recipe_group == "精制谷物":
            return False

    if slot_name in {"breakfast_fruit", "snack_fruit"}:
        if energy_kcal > 80:
            return False

    if slot_name == "lunch_dinner_vegetable":
        if sodium_mg > policy["max_sodium_mg"]:
            return False

    return True


def score_food(food: dict[str, Any], slot_name: str, policy: dict[str, Any]) -> float:
    sodium_mg = float(food.get("sodium_mg") or 0)
    fat_g = float(food.get("fat_g") or 0)
    sfa_g = float(food.get("sfa_g") or 0)
    cholesterol_mg = float(food.get("cholesterol_mg") or 0)
    protein_g = float(food.get("protein_g") or 0)
    fiber_g = float(food.get("insoluble_fiber_g") or 0)
    vitamin_c_mg = float(food.get("vitamin_c_mg") or 0)
    energy_kcal = float(food.get("energy_kcal") or 0)

    score = 100.0
    score -= sodium_mg / 10
    score -= fat_g * 2
    score -= sfa_g * 3
    score -= cholesterol_mg / 20
    score -= energy_kcal / 30

    if slot_name in {"breakfast_protein", "lunch_dinner_protein", "dairy_or_soy"}:
        score += protein_g * 2.5
    if slot_name in {"breakfast_staple", "lunch_dinner_staple"}:
        score += fiber_g * 4
    if slot_name in {"lunch_dinner_vegetable", "breakfast_fruit", "snack_fruit"}:
        score += vitamin_c_mg / 5
        score += fiber_g * 3

    return round(score, 2)


def serialize_food_candidate(food: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "food_name": food.get("food_name"),
        "category_lv1": food.get("category_lv1"),
        "recipe_group": food.get("recipe_group"),
        "energy_kcal": food.get("energy_kcal"),
        "protein_g": food.get("protein_g"),
        "fat_g": food.get("fat_g"),
        "carbohydrate_g": food.get("carbohydrate_g"),
        "insoluble_fiber_g": food.get("insoluble_fiber_g"),
        "cholesterol_mg": food.get("cholesterol_mg"),
        "vitamin_c_mg": food.get("vitamin_c_mg"),
        "calcium_mg": food.get("calcium_mg"),
        "sodium_mg": food.get("sodium_mg"),
        "iron_mg": food.get("iron_mg"),
        "score": score,
    }


def build_slot_candidates(
    foods: list[dict[str, Any]],
    slot_name: str,
    policy: dict[str, Any],
    top_k: int = 12,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for food in foods:
        if is_food_allowed(food, slot_name, policy):
            selected.append(serialize_food_candidate(food, score_food(food, slot_name, policy)))

    selected.sort(key=lambda item: item["score"], reverse=True)
    return selected[:top_k]


def build_candidate_pool_for_user(
    user_data: dict[str, Any],
    restriction_profile: dict[str, Any],
    foods: list[dict[str, Any]],
) -> dict[str, Any]:
    policy = derive_filter_policy(user_data, restriction_profile)
    meal_candidates = {
        "breakfast_staple": build_slot_candidates(foods, "breakfast_staple", policy),
        "breakfast_protein": build_slot_candidates(foods, "breakfast_protein", policy),
        "breakfast_vegetable": build_slot_candidates(foods, "breakfast_vegetable", policy),
        "breakfast_fruit": build_slot_candidates(foods, "breakfast_fruit", policy),
        "lunch_dinner_staple": build_slot_candidates(foods, "lunch_dinner_staple", policy),
        "lunch_dinner_protein": build_slot_candidates(foods, "lunch_dinner_protein", policy),
        "lunch_dinner_vegetable": build_slot_candidates(foods, "lunch_dinner_vegetable", policy),
        "lunch_dinner_fruit": build_slot_candidates(foods, "lunch_dinner_fruit", policy),
        "dinner_protein_soy": build_slot_candidates(foods, "dinner_protein_soy", policy),
        "dinner_fruit": build_slot_candidates(foods, "dinner_fruit", policy),
    }

    fixed_slots = build_fixed_slots_with_reuse_cap(meal_candidates)

    return {
        "policy": {
            "prefer_whole_grains": policy["prefer_whole_grains"],
            "prefer_low_sodium": policy["prefer_low_sodium"],
            "prefer_low_fat": policy["prefer_low_fat"],
            "prefer_high_fiber": policy["prefer_high_fiber"],
            "max_sodium_mg_per_100g": policy["max_sodium_mg"],
            "max_cholesterol_mg_per_100g": policy["max_cholesterol_mg"],
            "max_fat_g_per_100g": policy["max_fat_g"],
            "max_sfa_g_per_100g": policy["max_sfa_g"],
            "daily_energy_limit_kcal": policy["daily_energy_limit_kcal"],
            "max_candidate_slot_reuse": MAX_CANDIDATE_SLOT_REUSE,
        },
        "meal_candidates": meal_candidates,
        "fixed_slots": fixed_slots,
    }


def build_fixed_slots_with_reuse_cap(
    meal_candidates: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """为 12 个固定槽位分配候选食材。

    约束：
    - 每个槽位保留 4 个候选食材
    - 同一食材在全天所有槽位候选中最多出现 2 次
    """

    food_slot_usage_count: dict[str, int] = defaultdict(int)
    fixed_slots: list[dict[str, Any]] = []

    for definition in FIXED_SLOT_DEFINITIONS:
        source_candidates = select_candidates_for_slot(
            meal_candidates[definition["candidate_source"]],
            food_slot_usage_count,
            limit=4,
            max_reuse=MAX_CANDIDATE_SLOT_REUSE,
        )
        fixed_slots.append(
            {
                "slot_id": definition["slot_id"],
                "meal_name": definition["meal_name"],
                "slot_index": definition["slot_index"],
                "slot_label": definition["slot_label"],
                "amount": definition["amount"],
                "unit": definition["unit"],
                "candidates": source_candidates,
            }
        )

    return fixed_slots


def select_candidates_for_slot(
    ranked_candidates: list[dict[str, Any]],
    food_slot_usage_count: dict[str, int],
    limit: int,
    max_reuse: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for candidate in ranked_candidates:
        food_name = str(candidate["food_name"])
        if food_slot_usage_count[food_name] >= max_reuse:
            continue
        selected.append(candidate)
        food_slot_usage_count[food_name] += 1
        if len(selected) == limit:
            return selected

    # 若严格限制下不够 4 个候选，则回退补齐，但优先保持尽量少重复。
    for candidate in ranked_candidates:
        food_name = str(candidate["food_name"])
        if any(item["food_name"] == food_name for item in selected):
            continue
        selected.append(candidate)
        food_slot_usage_count[food_name] += 1
        if len(selected) == limit:
            return selected

    return selected


def build_payload(
    users_data: list[dict[str, Any]],
    restriction_data: dict[str, Any],
    nutrition_data: list[dict[str, Any]],
) -> dict[str, Any]:
    users_payload: list[dict[str, Any]] = []

    for index, user_data in enumerate(users_data):
        validate_user_data(user_data)
        user_summary = build_user_summary(user_data, index)
        restriction_profile = select_restriction_profile(user_data, restriction_data, index)
        candidate_pool = build_candidate_pool_for_user(user_data, restriction_profile, nutrition_data)

        users_payload.append(
            {
                "user_summary": user_summary,
                "restriction_profile": restriction_profile,
                "candidate_pool": candidate_pool,
            }
        )

    return {
        "task_name": "meal_candidate_generation",
        "version": "0.1",
        "restriction_source": str(DEFAULT_RESTRICTION_FILE),
        "nutrition_source": str(DEFAULT_NUTRITION_FILE),
        "users": users_payload,
    }


def build_llm_prompt(payload: dict[str, Any]) -> str:
    sections: list[str] = []

    for user in payload["users"]:
        user_summary = user["user_summary"]
        fixed_slots = user["candidate_pool"]["fixed_slots"]

        breakfast_slots = [slot for slot in fixed_slots if slot["meal_name"] == "早餐"]
        lunch_slots = [slot for slot in fixed_slots if slot["meal_name"] == "午餐"]
        dinner_slots = [slot for slot in fixed_slots if slot["meal_name"] == "晚餐"]

        goal_text = user_summary["goal_type"]
        sections.extend(
            [
                f"===== {user_summary['user_id']} =====",
                "你是一名生活方式干预助手。请根据以下用户信息，生成 1 天方案，包括每日食谱和运动建议。",
                "",
                "【用户信息】",
                f"- 年龄：{user_summary['age_years']} 岁",
                f"- 性别：{user_summary['sex']}",
                f"- 身高：{user_summary['height_cm']} cm",
                f"- 体重：{user_summary['weight_kg']} kg",
                f"- 腰围：{user_summary['waist_cm']} cm",
                f"- BMI：{user_summary['bmi']}",
                f"- 体力劳动强度：{user_summary['labor_intensity']}",
                f"- 食物过敏：{user_summary['food_allergy']}",
                f"- 健康状态：{user_summary['health_status']}",
                f"- 目标：{goal_text}",
                "",
                "【输出要求】",
                "1. 生成 1 天方案，包括：",
                "- 每日食谱",
                "- 运动建议",
                "",
                "2. 生成食谱时只能使用下列固定食材槽位中的食材与固定数量。",
                "- breakfast.foods、lunch.foods、dinner.foods 必须各输出 4 项，且顺序与对应餐次的槽位1到槽位4一致。",
                "- 每个槽位只能从该槽位给出的候选食材中 4 选 1，不允许跨槽位替换。",
                "- 12 个槽位总共必须输出 12 种不同食材；同一个食材名称不能在两个槽位中重复出现。",
                "- 固定数量不得改写；不要新增额外食材，也不要删掉任何槽位。",
                "",
                "【固定食材槽位】",
                "全天固定 12 个食材槽位；每个槽位必须且只能选择 1 种食材，不允许新增槽位、不允许删除槽位、不允许重复使用同一食材。",
                "早餐：",
                *render_slot_lines(breakfast_slots),
                "",
                "午餐：",
                *render_slot_lines(lunch_slots),
                "",
                "晚餐：",
                *render_slot_lines(dinner_slots),
                "",
                "【输出内容补充约束】",
                "- name 只能写单个食材或单个调味品名称，不要写复合菜名或做法名。",
                "- amount 必须是数值，不得使用“适量”“少许”“若干”等模糊表述。",
                "- unit 仅使用 g、mL、个。若候选食材给的是 g 或 mL，输出时不要改成其他单位。",
                "",
                "【运动建议要求】",
                "- 结合该用户的体力劳动强度给出可执行的运动建议。",
                "- 说明运动类型、建议时长、强度和注意事项。",
                "- 输出内容使用中文，表达清晰、实用、不过度冗长。",
                "",
            ]
        )

    return "\n".join(sections).strip()


def render_slot_lines(slots: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for slot in sorted(slots, key=lambda item: item["slot_index"]):
        candidate_names = " / ".join(item["food_name"] for item in slot["candidates"])
        lines.append(
            f"- 槽位{slot['slot_index']}（{slot['slot_label']}）：{candidate_names}；固定数量 {slot['amount']}{slot['unit']}"
        )
    return lines


def save_json_output(content: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text_output(content: str, output_path: str | Path) -> None:
    Path(output_path).write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据用户信息、限制信息和食物营养库，生成候选食材池及 LLM prompt。"
    )
    parser.add_argument("--input", required=True, help="用户输入 JSON，支持单用户或多用户")
    parser.add_argument(
        "--restrictions",
        default=str(DEFAULT_RESTRICTION_FILE),
        help="限制信息 JSON 文件路径",
    )
    parser.add_argument(
        "--nutrition",
        default=str(DEFAULT_NUTRITION_FILE),
        help="食物营养成分 JSON 文件路径",
    )
    parser.add_argument("--output_payload", help="可选：输出结构化候选食材载荷 JSON")
    parser.add_argument("--output_prompt", help="可选：输出给 LLM 的 prompt 文本")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    raw_users = load_user_input(args.input)
    users_data = normalize_user_inputs(raw_users)
    restriction_data = load_json_file(args.restrictions)
    nutrition_data = load_json_file(args.nutrition)

    if not isinstance(nutrition_data, list):
        raise CandidateGenerationError("食物营养成分文件必须是数组结构。")

    payload = build_payload(users_data, restriction_data, nutrition_data)
    prompt = build_llm_prompt(payload)

    print("===== Candidate Payload =====")
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
