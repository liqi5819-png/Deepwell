# New_Workflow_0408

这是一个面向“结构化健康用户输入 -> 基础 Prompt -> 用户路由”的 Python 小型工作流初版。

当前版本只完成以下能力：

- 读取标准化用户输入 JSON
- 做最基本的关键字段检查
- 生成供 LLM 使用的中文基础 prompt
- 提取用户特征标签并输出指南路由结果
- 提供独立的指南注册与查询框架

当前版本明确不包含以下能力：

- 不读取 PDF 指南正文
- 不调用 LLM
- 不写死正式的“用户类型 -> 指南”映射规则

## 文件说明

- `generate_prompt_from_input.py`
  - 主脚本
  - 负责输入读取、基础校验、用户标签提取、Prompt 组装、路由结果输出、CLI 入口

- `knowledge.py`
  - 指南知识注册与管理层
  - 负责指南元数据的数据结构、注册表、候选查询、按 ID 查询
  - 当前只放 placeholder 数据，后续可以替换为真实指南配置

- `test_input_healthy_lifestyle.json`
  - 健康生活方式场景的标准化输入样例

- `prompt_output.txt`
  - 使用测试样例运行后输出的基础 prompt

- `route_output.json`
  - 使用测试样例运行后输出的结构化路由结果

## 输入结构

顶层字段：

- `basic_info`
- `physical_activity`
- `goal`
- `food_allergy`
- `health_status`

其中 `goal` 当前仅使用：

- `goal_type`

没有使用以下字段：

- `duration_weeks`
- `target_change_kg`

`health_status` 当前支持的子结构：

- `healthy`
- `diabetes`
- `fatty_liver`
- `chronic_kidney_disease`
- `hypertension`
- `hyperuricemia_or_gout`
- `hyperthyroidism`

## 运行方式

在当前目录下运行：

```bash
python generate_prompt_from_input.py --input test_input_healthy_lifestyle.json
```

如果希望把输出写入文件：

```bash
python generate_prompt_from_input.py --input test_input_healthy_lifestyle.json --output_prompt prompt_output.txt --output_route route_output.json
```

## 当前测试结果

已使用以下命令完成测试：

```bash
python generate_prompt_from_input.py --input test_input_healthy_lifestyle.json --output_prompt prompt_output.txt --output_route route_output.json
```

测试结果摘要：

- 成功读取 `test_input_healthy_lifestyle.json`
- 成功生成中文基础 prompt
- 成功输出结构化路由结果
- 当前样例的 `profile_tags` 为：
  - `healthy`
  - `healthy_lifestyle`
- 当前命中的候选指南为占位项：
  - `placeholder_general_nutrition`
- 当前 `selected_guideline` 仍为 `null`
  - 原因：正式映射表尚未配置

## 模块协作关系

### 1. generate_prompt_from_input.py

主流程如下：

1. 读取 JSON 文件
2. 校验关键字段
3. 提取用户 profile tags
4. 生成基础 prompt
5. 调用 `knowledge.py` 查询候选指南
6. 输出 prompt 和路由结果

### 2. knowledge.py

当前职责如下：

1. 定义 `GuidelineMetadata`
2. 维护指南注册表
3. 提供候选指南查询接口
4. 提供按 ID 查询接口

后续建议继续保持这个职责边界，不要把 PDF 解析或 LLM 调用塞进这个模块。

## 后续扩展建议

建议优先补下面两层：

1. 用户分流规则表
   - 将“用户标签 -> 指南选择”做成独立配置或规则模块

2. 指南资源配置
   - 在 `knowledge.py` 或单独配置文件中维护真实的 `guideline_id`、`guideline_name`、`file_path`、`target_population_tags`

后续如果需要，也可以继续增加：

- PDF 内容读取模块
- 指南规则抽取模块
- Prompt 注入指南约束模块
- LLM 调用模块
