### 无人机浮游植物识别项目 - AI视觉（吴天宇）专属 README

#### 一、核心定位
作为项目 AI 视觉算法负责人，我负责浮游植物识别全流程算法开发，并**为预测可视化提供空间仿真工具**。核心职责：基于公开数据集训练天气分类模型；基于贺一冉交付的标注数据集训练**三个天气专用的 DeepLabV3+ 语义分割模型**，同时训练**一个不区分天气的统一 DeepLabV3+ 模型作为对比基线**；开发推理管道，输出实测掩码与基于元数据的量化结果；**提供增强版空间仿真脚本及规律提取工具，供数模组（刘俊辉）调用，以生成未来浮游植物分布图**。模型本身绝不直接输出面积，只做像素级分割。

#### 二、绝对清晰的工作边界
✅ **核心负责（天气自适应AI视觉全流程 + 对比实验 + 仿真工具）**
1. 天气分类模型：使用公开数据集（存放于 `data/weather_public/`）训练，无需贺一冉提供标注。
2. 分割模型训练：
   - 从 `data/03_labeled/` 读取贺一冉交付的标注数据，按文件名中的天气标签划分三个子数据集，分别训练 DeepLabV3+ 模型（sunny / cloudy / hazy）。
   - **额外使用全部标注数据（不区分天气）训练一个统一的 DeepLabV3+ 模型，作为对比基线。**
3. 推理链路：输入图像 + 元数据 → 天气分类 → 调用对应分割模型 → 输出掩码图与量化结果。面积计算通过读取元数据中的 GSD 完成。
4. 量化计算：浮游植物覆盖面积、占比、浓度等级写入 `outputs/quantifications/`。
5. **空间仿真脚本开发（增强版）**：
   - 编写 `utils/simulation/generate_prediction_mask.py`，接收基准掩码路径、面积变化率以及**空间生长规则参数**（扩张方向偏好、边缘权重等），生成预测分布图。
   - 编写 `utils/simulation/extract_growth_pattern.py`，从两次实测掩码中提取斑块变化的统计特征（扩张速率、方向分布等），供数模组调用。
   - 附带详细调用说明，交付刘俊辉使用。
6. **轻量正射校正脚本开发与交付**：
   - 编写 `utils/preprocess/orthorectify.py`，功能简化为：
     * 校验垂直姿态（pitch、roll）和焦距一致性；
     * 当满足垂直拍摄、焦距固定的条件时，基于理论 GSD 将原始图像等比缩放、居中填充至 1024×1024，输出 PNG 图像及包含有效 GSD、有效区域边界的元数据文件；
     * 若垂直度或焦距偏差超出阈值，则终止处理并提示原因。
   - 交付数据模块（贺一冉）执行。
7. 数据格式规范制定：约定 `outputs/masks/` 的命名规则和 `outputs/quantifications/` 的 JSON 字段。
8. **对比实验与评估报告**：完成四种分割模型训练后，在相同测试标准下计算 mIoU、Accuracy，产出两个对比表格（宏观对比与分天气细节），附于模型评估报告。

❌ **绝不涉及**
- 不参与任何原始图像采集、预处理。
- 不使用 LabelMe 开展初始像素级标注（仅复核）。
- 不进行时序分析、预测建模。
- 不开发前端展示界面。

#### 三、分步执行任务（含路径约定）

**1. 数据接收与核验**
- 读取路径：`../data/02_preprocessed/images/`、`../data/02_preprocessed/meta/`、`../data/03_labeled/`。
- 核验数据完整性，特别是元数据中 GSD 的有效性。

**2. 天气分类模型训练**
- 数据来源：`../../data/weather_public/`
- 脚本位置：`models/weather_classifier/train.py`
- 模型保存：`models/weather_classifier/best_weather_model.pth`

**3. 多条件分割模型训练（含对比模型）**
- 专属模型：`models/deeplabv3plus/sunny/train.py`、`cloudy/train.py`、`hazy/train.py`
- 对比模型：`models/deeplabv3plus/combined/train.py`（读取全部数据，混合训练）
- 每个训练脚本需保存评估指标（mIoU, Accuracy, F1）至模型目录下的 `metrics.json`。

**4. 模型推理与量化计算**
- 脚本：`models/predict_pipeline.py`
- 执行逻辑：天气分类 → 路由分割模型 → 输出掩码图 + 量化 JSON。
- 输出：`outputs/masks/` 和 `outputs/quantifications/`

**5. 对比模型评估与指标统计**
- 汇总四个模型的最佳指标，生成两份表格：
  - 表格1：统一模型 vs. 天气自适应模型的平均指标。
  - 表格2：晴天、阴天、雾天专属模型在各自测试集上的指标。
- 写入模型评估报告，附简要分析。

**6. 空间仿真脚本开发与交付**
- `generate_prediction_mask.py`：接收基准掩码、面积变化率及生长规则参数。
- `extract_growth_pattern.py`：输入两次实测掩码，输出统计特征。
- 交付刘俊辉，提供详细使用说明。

**7. 格式核验与交付**
- 检查 `outputs/` 下所有文件格式，与乔梓阁对齐。

#### 四、模块分工（一句话界定）
- 航拍组：采集多天气原始图像 → `data/01_raw/`
- 贺一冉：预处理与标注 → `data/02_preprocessed/`、`data/03_labeled/`
- **本人（吴天宇）**：公开数据集 → 天气分类；标注数据集 → 训练四套分割模型；推理 + 量化 + 仿真脚本 + 对比评估 → 输出至 `outputs/`
- 刘俊辉：读取 `outputs/quantifications/` 进行预测，调用我的仿真脚本生成预测掩码
- 乔梓阁：读取 `outputs/` 构建展示 Demo

#### 五、最终交付物
1. 天气分类模型权重及代码。
2. 三个天气专属 DeepLabV3+ 模型权重及训练脚本。
3. 一个统一 DeepLabV3+ 对比模型权重及训练脚本。
4. 总推理脚本 `predict_pipeline.py`。
5. 空间仿真脚本 `generate_prediction_mask.py` 及 `extract_growth_pattern.py`。
6. 轻量标准化脚本 `orthorectify.py`（基于垂直拍摄假设的缩放填充 + 校验）及使用说明。
7. 实测分割掩码图与量化数据。
8. `outputs/` 数据格式规范文档。
9. 模型评估报告（含对比表格及天气自适应必要性分析）。