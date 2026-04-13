from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"


@dataclass
class GuidelineMetadata:
    """指南元数据。"""

    guideline_id: str
    guideline_name: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    target_population_tags: list[str] = field(default_factory=list)
    description: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolve_file_path(self) -> Optional[Path]:
        if not self.file_path:
            return None
        return Path(self.file_path).expanduser()


@dataclass(frozen=True)
class BaseGuidelineRule:
    """按目标类型和 BMI 选择基础指南。"""

    goal_type: str
    bmi_min: Optional[float]
    bmi_max: Optional[float]
    bmi_label: str
    guideline_ids: list[str]
    enabled: bool = True

    def to_dict(self, registry: dict[str, GuidelineMetadata]) -> dict[str, Any]:
        return {
            "goal_type": self.goal_type,
            "bmi_label": self.bmi_label,
            "guideline_files": [
                _get_guideline_file_name(guideline_id, registry)
                for guideline_id in self.guideline_ids
            ],
        }


@dataclass(frozen=True)
class DiseaseGuidelineRule:
    """按疾病状态附加指南。"""

    condition_key: str
    reason_label: str
    health_flag_path: tuple[str, ...]
    guideline_ids: list[str]
    enabled: bool = True


GUIDELINE_CATALOG = [
    GuidelineMetadata(
        guideline_id="general_diet",
        guideline_name="一般饮食",
        file_name="一般饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "一般饮食.pdf"),
        target_population_tags=[
            "healthy",
            "healthy_lifestyle",
            "weight_loss",
            "bmi_lt_24",
            "bmi_24_to_32_5",
            "bmi_ge_32_5",
        ],
        description="一般人群饮食指导。",
    ),
    GuidelineMetadata(
        guideline_id="general_weight_management",
        guideline_name="一般体重管理",
        file_name="一般体重管理.pdf",
        file_path=str(KNOWLEDGE_DIR / "一般体重管理.pdf"),
        target_population_tags=[
            "healthy_lifestyle",
            "weight_loss",
            "bmi_lt_24",
            "bmi_24_to_32_5",
            "bmi_ge_32_5",
        ],
        description="一般人群体重管理指导。",
    ),
    GuidelineMetadata(
        guideline_id="obesity_diet",
        guideline_name="肥胖饮食",
        file_name="肥胖饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "肥胖饮食.pdf"),
        target_population_tags=["weight_loss", "bmi_24_to_32_5", "bmi_ge_32_5"],
        description="超重和肥胖相关饮食指导。",
    ),
    GuidelineMetadata(
        guideline_id="diabetes_diet",
        guideline_name="糖尿病饮食",
        file_name="糖尿病饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "糖尿病饮食.pdf"),
        target_population_tags=["diabetes"],
        description="糖尿病饮食指导。",
    ),
    GuidelineMetadata(
        guideline_id="diabetes_exercise",
        guideline_name="糖尿病运动",
        file_name="糖尿病运动.pdf",
        file_path=str(KNOWLEDGE_DIR / "糖尿病运动.pdf"),
        target_population_tags=["diabetes", "uses_insulin"],
        description="糖尿病运动指导。",
    ),
    GuidelineMetadata(
        guideline_id="hypertension_diet",
        guideline_name="高血压饮食",
        file_name="高血压饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "高血压饮食.pdf"),
        target_population_tags=["hypertension"],
        description="高血压饮食指导。",
    ),
    GuidelineMetadata(
        guideline_id="ckd_diet",
        guideline_name="慢性肾病饮食",
        file_name="慢性肾病饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "慢性肾病饮食.pdf"),
        target_population_tags=["chronic_kidney_disease"],
        description="慢性肾病饮食指导。",
    ),
    GuidelineMetadata(
        guideline_id="hyperuricemia_or_gout_diet",
        guideline_name="高尿酸血症与痛风饮食",
        file_name="高尿酸血症与痛风饮食.pdf",
        file_path=str(KNOWLEDGE_DIR / "高尿酸血症与痛风饮食.pdf"),
        target_population_tags=["hyperuricemia_or_gout"],
        description="高尿酸血症与痛风饮食指导。",
    ),
]


BASE_GUIDELINE_RULES = [
    BaseGuidelineRule(
        goal_type="healthy_lifestyle",
        bmi_min=None,
        bmi_max=24.0,
        bmi_label="BMI<24",
        guideline_ids=["general_diet", "general_weight_management"],
    ),
    BaseGuidelineRule(
        goal_type="healthy_lifestyle",
        bmi_min=24.0,
        bmi_max=32.5,
        bmi_label="24<=BMI<32.5",
        guideline_ids=["general_diet", "general_weight_management", "obesity_diet"],
    ),
    BaseGuidelineRule(
        goal_type="healthy_lifestyle",
        bmi_min=32.5,
        bmi_max=None,
        bmi_label="BMI>=32.5",
        guideline_ids=["general_diet", "general_weight_management", "obesity_diet"],
    ),
    BaseGuidelineRule(
        goal_type="weight_loss",
        bmi_min=18.5,
        bmi_max=24.0,
        bmi_label="18.5<=BMI<24",
        guideline_ids=["general_diet", "general_weight_management", "obesity_diet"],
    ),
    BaseGuidelineRule(
        goal_type="weight_loss",
        bmi_min=24.0,
        bmi_max=32.5,
        bmi_label="24<=BMI<32.5",
        guideline_ids=["general_diet", "general_weight_management", "obesity_diet"],
    ),
    BaseGuidelineRule(
        goal_type="weight_loss",
        bmi_min=32.5,
        bmi_max=None,
        bmi_label="BMI>=32.5",
        guideline_ids=["general_diet", "general_weight_management", "obesity_diet"],
    ),
]


DISEASE_GUIDELINE_RULES = [
    DiseaseGuidelineRule(
        condition_key="diabetes",
        reason_label="糖尿病",
        health_flag_path=("diabetes", "has_diabetes"),
        guideline_ids=["diabetes_diet", "diabetes_exercise"],
    ),
    DiseaseGuidelineRule(
        condition_key="hypertension",
        reason_label="高血压",
        health_flag_path=("hypertension", "has_hypertension"),
        guideline_ids=["hypertension_diet"],
    ),
    DiseaseGuidelineRule(
        condition_key="chronic_kidney_disease",
        reason_label="慢性肾病",
        health_flag_path=("chronic_kidney_disease", "has_ckd"),
        guideline_ids=["ckd_diet"],
    ),
    DiseaseGuidelineRule(
        condition_key="hyperuricemia_or_gout",
        reason_label="高尿酸血症或痛风",
        health_flag_path=("hyperuricemia_or_gout", "has_hyperuricemia_or_gout"),
        guideline_ids=["hyperuricemia_or_gout_diet"],
    ),
]


def _build_guideline_registry() -> dict[str, GuidelineMetadata]:
    return {item.guideline_id: item for item in GUIDELINE_CATALOG}


_GUIDELINE_REGISTRY: dict[str, GuidelineMetadata] = _build_guideline_registry()


def get_guideline_registry(enabled_only: bool = False) -> dict[str, GuidelineMetadata]:
    """返回当前已注册的指南信息。"""

    if not enabled_only:
        return dict(_GUIDELINE_REGISTRY)
    return {
        guideline_id: metadata
        for guideline_id, metadata in _GUIDELINE_REGISTRY.items()
        if metadata.enabled
    }


def get_guideline_by_id(
    guideline_id: str, registry: Optional[dict[str, GuidelineMetadata]] = None
) -> Optional[GuidelineMetadata]:
    """按 guideline_id 查询单条指南。"""

    lookup = registry if registry is not None else _GUIDELINE_REGISTRY
    return lookup.get(guideline_id)


def find_candidate_guidelines(
    profile_tags: list[str],
    enabled_only: bool = True,
    registry: Optional[dict[str, GuidelineMetadata]] = None,
) -> list[GuidelineMetadata]:
    """按用户特征标签查询候选指南。"""

    if not profile_tags:
        return []

    lookup = registry if registry is not None else get_guideline_registry(enabled_only=enabled_only)
    if registry is not None and enabled_only:
        lookup = {
            guideline_id: metadata
            for guideline_id, metadata in lookup.items()
            if metadata.enabled
        }

    tag_set = set(profile_tags)
    candidates_with_score: list[tuple[int, str, GuidelineMetadata]] = []

    for metadata in lookup.values():
        score = len(tag_set.intersection(metadata.target_population_tags))
        if score > 0:
            candidates_with_score.append((score, metadata.guideline_id, metadata))

    candidates_with_score.sort(key=lambda item: (-item[0], item[1]))
    return [metadata for _, _, metadata in candidates_with_score]


def register_guideline(metadata: GuidelineMetadata, overwrite: bool = False) -> None:
    """注册新指南。"""

    if metadata.guideline_id in _GUIDELINE_REGISTRY and not overwrite:
        raise ValueError(
            f"指南 ID 已存在：{metadata.guideline_id}。如需覆盖，请设置 overwrite=True。"
        )
    _GUIDELINE_REGISTRY[metadata.guideline_id] = metadata


def clear_guideline_registry() -> None:
    """清空注册表。"""

    _GUIDELINE_REGISTRY.clear()


def list_base_guideline_rules() -> list[dict[str, Any]]:
    """返回基础映射规则，便于查看或外部配置校验。"""

    registry = get_guideline_registry(enabled_only=False)
    return [rule.to_dict(registry) for rule in BASE_GUIDELINE_RULES if rule.enabled]


def list_disease_guideline_rules() -> list[dict[str, Any]]:
    """返回疾病附加规则，便于查看或外部配置校验。"""

    registry = get_guideline_registry(enabled_only=False)
    return [
        {
            "condition_key": rule.condition_key,
            "reason_label": rule.reason_label,
            "health_flag_path": list(rule.health_flag_path),
            "guideline_files": [
                _get_guideline_file_name(guideline_id, registry)
                for guideline_id in rule.guideline_ids
            ],
        }
        for rule in DISEASE_GUIDELINE_RULES
        if rule.enabled
    ]


def select_guidelines_for_user(
    *,
    goal_type: str,
    bmi: float,
    health_status: dict[str, Any],
    registry: Optional[dict[str, GuidelineMetadata]] = None,
) -> dict[str, Any]:
    """根据可配置规则选择基础指南和疾病附加指南。"""

    lookup = registry if registry is not None else get_guideline_registry(enabled_only=False)

    matched_base_rule: Optional[BaseGuidelineRule] = None
    for rule in BASE_GUIDELINE_RULES:
        if not rule.enabled or rule.goal_type != goal_type:
            continue
        if _is_bmi_in_range(bmi, rule.bmi_min, rule.bmi_max):
            matched_base_rule = rule
            break

    base_ids = matched_base_rule.guideline_ids if matched_base_rule else []
    disease_ids: list[str] = []
    disease_reasons: list[str] = []

    for rule in DISEASE_GUIDELINE_RULES:
        if not rule.enabled:
            continue
        if _health_flag_is_true(health_status, rule.health_flag_path):
            disease_ids.extend(rule.guideline_ids)
            disease_reasons.append(rule.reason_label)

    selected_ids = _deduplicate_ids([*base_ids, *disease_ids])

    return {
        "bmi": bmi,
        "goal_type": goal_type,
        "base_rule": matched_base_rule.to_dict(lookup) if matched_base_rule else None,
        "disease_reasons": disease_reasons,
        "selected_guideline_ids": selected_ids,
        "selected_guidelines": [
            resolve_guideline_reference(guideline_id, lookup) for guideline_id in selected_ids
        ],
    }


def resolve_guideline_reference(
    guideline_id: str, registry: Optional[dict[str, GuidelineMetadata]] = None
) -> dict[str, Any]:
    """把 guideline_id 解析成文件引用信息。"""

    lookup = registry if registry is not None else get_guideline_registry(enabled_only=False)
    metadata = get_guideline_by_id(guideline_id, registry=lookup)
    if metadata is None:
        return {
            "guideline_id": guideline_id,
            "guideline_name": guideline_id,
            "file_name": guideline_id,
            "file_path": str(KNOWLEDGE_DIR / guideline_id),
            "exists": False,
            "enabled": False,
        }

    resolved_path = metadata.resolve_file_path()
    return {
        "guideline_id": metadata.guideline_id,
        "guideline_name": metadata.guideline_name,
        "file_name": metadata.file_name or metadata.guideline_name,
        "file_path": str(resolved_path) if resolved_path is not None else None,
        "exists": resolved_path.exists() if resolved_path is not None else False,
        "enabled": metadata.enabled,
    }


def _get_guideline_file_name(
    guideline_id: str, registry: dict[str, GuidelineMetadata]
) -> str:
    metadata = get_guideline_by_id(guideline_id, registry=registry)
    if metadata is None:
        return guideline_id
    return metadata.file_name or metadata.guideline_name


def _is_bmi_in_range(bmi: float, bmi_min: Optional[float], bmi_max: Optional[float]) -> bool:
    if bmi_min is not None and bmi < bmi_min:
        return False
    if bmi_max is not None and bmi >= bmi_max:
        return False
    return True


def _health_flag_is_true(health_status: dict[str, Any], path: tuple[str, ...]) -> bool:
    current: Any = health_status
    for key in path:
        if not isinstance(current, dict):
            return False
        current = current.get(key)
    return current is True


def _deduplicate_ids(guideline_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for guideline_id in guideline_ids:
        if guideline_id not in seen:
            deduplicated.append(guideline_id)
            seen.add(guideline_id)
    return deduplicated
