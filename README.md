# New_Workflow_0408

这个目录目前是一套“用户输入 -> 指南路由 -> Prompt 生成 -> 可选 LLM 调用”的工作流。

## 目录结构

- `main.py`
  - workflow 总入口
- `tools/User_Profiling.py`
  - 读取标准化用户输入
  - 校验字段
  - 计算 BMI
  - 按 `tools/knowledge.py` 的内置规则完成指南路由
  - 生成 `base_prompt`
- `tools/frameworks.py`
  - 接收用户输入和路由结果
  - 生成约束抽取用的 `framework payload`
  - 生成 `framework_prompt`
- `tools/lifestyle.py`
  - 接收用户输入和对应用户约束文件
  - 默认从 `knowledge/{user_id}_constraints.json` 读取用户约束
  - 生成生活方式建议用的 `lifestyle_prompt`
- `tools/knowledge.py`
  - 维护指南注册表
  - 内置目标类型 + BMI 的基础映射规则
  - 内置疾病附加规则
  - 维护用户约束文件的默认路径规则
- `tools/llm_runner.py`
  - 独立的 LLM 调用工具层
- `knowledge/`
  - PDF 指南与营养数据等知识文件

## 当前流程

`main.py` 固定执行 workflow：

1. 读取用户输入 JSON
2. 调用 `tools/User_Profiling.py` 对应逻辑生成 `base_prompt`
3. 使用 `tools/knowledge.py` 的内置映射规则完成指南路由
4. 把路由结果写到根目录 `route_output.json`
5. 调用 `tools/frameworks.py` 生成 `framework_prompt`
6. 调用 `tools/lifestyle.py`，结合用户信息和用户约束生成 `lifestyle_prompt`
7. 如果不是 `--dry-run`，再调用 `tools/llm_runner.py` 请求模型

## knowledge.py 规则

`tools/knowledge.py` 不再依赖运行时解析 `knowledge/指南映射信息.txt`。

当前已内置这些基础规则：

- `healthy_lifestyle + BMI<24 -> 一般饮食 + 一般体重管理`
- `healthy_lifestyle + 24<=BMI<32.5 -> 一般饮食 + 一般体重管理 + 肥胖饮食`
- `healthy_lifestyle + BMI>=32.5 -> 一般饮食 + 一般体重管理 + 肥胖饮食`
- `weight_loss + 18.5<=BMI<24 -> 一般饮食 + 一般体重管理 + 肥胖饮食`
- `weight_loss + 24<=BMI<32.5 -> 一般饮食 + 一般体重管理 + 肥胖饮食`
- `weight_loss + BMI>=32.5 -> 一般饮食 + 一般体重管理 + 肥胖饮食`

当前已内置这些疾病附加规则：

- `糖尿病 -> 糖尿病饮食 + 糖尿病运动`
- `高血压 -> 高血压饮食`
- `慢性肾病 -> 慢性肾病饮食`
- `高尿酸血症与痛风 -> 高尿酸血症与痛风饮食`

## 输入要求

输入 JSON 当前依赖这些顶层字段：

- `basic_info`
- `physical_activity`
- `goal`
- `food_allergy`
- `health_status`

其中核心字段包括：

- `basic_info.age_years`
- `basic_info.sex`
- `basic_info.height_cm`
- `basic_info.weight_kg`
- `basic_info.waist_cm`
- `physical_activity.labor_intensity`
- `goal.goal_type`

`health_status` 当前支持：

- `healthy`
- `diabetes`
- `fatty_liver`
- `chronic_kidney_disease`
- `hypertension`
- `hyperuricemia_or_gout`
- `hyperthyroidism`

## 运行方式

### 1. 只生成 base prompt 和 route result

```bash
python -m tools.User_Profiling --input test_input_healthy_lifestyle.json
```

如果同时写出文件：

```bash
python -m tools.User_Profiling --input test_input_healthy_lifestyle.json --output_prompt prompt_output.txt --output_route route_output.json
```

### 2. 只生成 framework prompt

`tools/frameworks.py` 现在要求显式传入路由结果文件。

```bash
python -m tools.frameworks --input test_input_healthy_lifestyle.json --route route_output.json --output_prompt framework_prompt.txt --output_payload framework_payload.json
```

### 3. 跑完整 workflow

只生成流程结果，不调用 LLM：

```bash
python main.py --input test_input_healthy_lifestyle.json --provider kimi --dry-run --output-json workflow_dry_run.json
```
默认会把约束结果保存到 `knowledge/{user_id}_constraints.json`，例如 `knowledge/user_1_constraints.json`。

生成 prompt 并调用 LLM：

```bash
python main.py --input test_input_healthy_lifestyle.json --provider kimi --output-json workflow_output.json
```
如果需要覆盖默认路径，可以显式传入：
```bash
python main.py --input test_input_healthy_lifestyle.json --provider kimi --constraints-file knowledge/user_1_constraints.json --output-json workflow_output.json
```

### 4. 单独调用 LLM 工具层

```bash
python -m tools.llm_runner --provider kimi --prompt "请只回复一句测试信息"
```

### 5. 生成生活方式建议 prompt

```bash
python -m tools.lifestyle --input test_input_healthy_lifestyle.json --output_prompt lifestyle_prompt.txt --output_payload lifestyle_payload.json
```

如果需要显式指定用户约束文件，可以传入：

```bash
python -m tools.lifestyle --input test_input_healthy_lifestyle.json --constraints knowledge/user_1_constraints.json --output_prompt lifestyle_prompt.txt
```

## main.py 参数

`main.py` 当前只保留最小参数集合：

- `--provider`
  - 模型提供方，默认 `kimi`
- `--input`
  - 用户输入 JSON 路径，必填
- `--model`
  - 可选，覆盖默认模型名
- `--base-url`
  - 可选，覆盖默认接口地址
- `--dry-run`
  - 只跑流程，不调用 LLM
- `--print-prompt`
  - 打印生成的 prompt
- `--output-json`
  - 把 workflow 输出写到 JSON 文件
- `--constraints-file`
  - 可选：指定 `framework_prompt` 的 LLM 回复保存路径；未传时默认写入 `knowledge/{user_id}_constraints.json`

## workflow 输出结构

`main.py` 的输出 JSON 结构大致如下：

```json
{
  "generated_at": "...",
  "mode": "workflow",
  "provider": "kimi",
  "model": "...",
  "base_url": "...",
  "system_prompt": null,
  "constraints_file": "...",
  "lifestyle_prompt_file": "...",
  "results": {
    "base_prompt": {
      "prompt": "..."
    },
    "framework_prompt": {
      "prompt": "..."
    },
    "lifestyle_prompt": {
      "prompt": "..."
    }
  },
  "normalized_input_file": "..."
}
```

如果不是 `--dry-run`，每个阶段还会附带：

- `response_text`
- `raw_response`

如果调用失败，会附带：

- `error`

## 说明

- `route_output.json` 是 workflow 运行时生成的中间文件，位于项目根目录
- `knowledge/user_1_constraints.json` 是默认约束输出文件路径示例；实际命名规则为 `knowledge/{user_id}_constraints.json`
- `tools/frameworks.py` 不会自动跑路由，它只消费已有的路由结果
- `main.py` 现在会串联生成 `base_prompt.txt`、`framework_prompt.txt`、`lifestyle_prompt.txt`
- `tools/llm_runner.py` 负责调用模型，不负责业务编排
