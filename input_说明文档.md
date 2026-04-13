# 标准化输入文件字段说明

## 1. basic_info
- `age_years`: 整数，单位岁
  - 规则：
    - 必须 **大于 18 且小于 80**
- `sex`: `male` / `female`
- `height_cm`: 数值，单位 cm
- `weight_kg`: 数值，单位 kg
- `waist_cm`: 数值，单位 cm

## 2. physical_activity
- `labor_intensity`: `light` / `moderate` / `heavy`

## 3. goal
- `goal_type`: `weight_loss` / `healthy_lifestyle`

## 4. food_allergy
- `has_food_allergy`: `true` / `false`
- `allergy_foods`: 数组
  - 规则：
    - 若 `has_food_allergy=false`，填空数组 `[]`
    - 若 `has_food_allergy=true`，填写具体过敏食物名称

## 5. health_status

### 5.0 healthy
- `healthy`: `true` / `false`
- 规则：
  - 若 `healthy=true`，则以下所有疾病字段都应为 `false`
  - 若以下任意疾病字段为 `true`，则 `healthy=false`

### 5.1 diabetes
- `has_diabetes`: `true` / `false`
- `diabetes_type`: `type_1` / `type_2` / `null`
- `uses_insulin`: `true` / `false` / `null`
- 规则：
  - 若 `has_diabetes=false`，则 `diabetes_type=null`，`uses_insulin=null`
  - 若 `has_diabetes=true`，则必须填写 `diabetes_type`
  - 若 `has_diabetes=true`，则必须填写 `uses_insulin`

### 5.2 fatty_liver
- `has_fatty_liver`: `true` / `false`
- `severity`: `mild_or_moderate` / `severe` / `null`
- 规则：
  - 若 `has_fatty_liver=false`，则 `severity=null`

### 5.3 chronic_kidney_disease
- `has_ckd`: `true` / `false`
- `stage_group`: `stage_1_2` / `stage_3_4` / `stage_5` / `null`
- 规则：
  - 若 `has_ckd=false`，则 `stage_group=null`

### 5.4 hypertension
- `has_hypertension`: `true` / `false`

### 5.5 hyperuricemia_or_gout
- `has_hyperuricemia_or_gout`: `true` / `false`

### 5.6 hyperthyroidism
- `has_hyperthyroidism`: `true` / `false`
