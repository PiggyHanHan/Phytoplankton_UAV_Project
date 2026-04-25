### 无人机浮游植物识别项目 - AI视觉（吴天宇）专属 README

#### 一、核心定位
作为项目 AI 视觉算法负责人，我负责浮游植物识别全流程算法开发，并**为预测可视化提供空间仿真工具**。核心职责：基于公开数据集训练天气分类模型，基于贺一冉交付的标注数据集训练三个专用的 DeepLabV3+ 语义分割模型；开发推理管道，输出实测掩码与基于元数据的量化结果；**提供空间仿真脚本，供数模组（刘俊辉）调用，以生成未来浮游植物分布图**。模型本身绝不直接输出面积，只做像素级分割。

#### 二、绝对清晰的工作边界
✅ **核心负责（天气自适应AI视觉全流程 + 仿真工具）**
1. 天气分类模型：使用公开数据集（存放于 `data/weather_public/`）训练，无需贺一冉提供标注。
2. 分割模型训练：从 `data/03_labeled/` 读取贺一冉交付的标注数据，按文件名中的天气标签划分三个子数据集，分别训练 DeepLabV3+ 模型。
3. 推理链路：输入图像 + 元数据 → 天气分类 → 调用对应分割模型 → 输出掩码图与量化结果。面积计算通过读取元数据中的 GSD 完成，不在模型内部进行。
4. 量化计算：浮游植物覆盖面积、占比、浓度等级，这些数值写入 `outputs/quantifications/`。
5. **空间仿真脚本开发**：编写 `utils/simulation/generate_prediction_mask.py`，实现基于基准掩码和面积变化率（如 +30%）的形态学膨胀/腐蚀，生成预测分布图。附带详细调用说明，交付刘俊辉使用。
6. **正射校正脚本开发与交付**：编写 `utils/preprocess/orthorectify.py`，基于无人机飞行参数对原始RAW图像进行几何校正，输出正射PNG图像及含GSD的元数据文件。该脚本交付数据模块（贺一冉）执行，需附带使用说明。
7. 数据格式规范制定：约定 `outputs/masks/` 的命名规则和 `outputs/quantifications/` 的 JSON 字段，保证展示组可无障碍读取。

❌ **绝不涉及**
- 不参与任何原始图像采集、预处理。
- 不使用 LabelMe 开展初始像素级标注（仅复核）。
- 不进行时序分析、预测建模。
- 不开发前端展示界面。

#### 三、分步执行任务（含路径约定）

**1. 数据接收与核验**
- 读取路径：`../data/02_preprocessed/images/`（预处理图像）、`../data/02_preprocessed/meta/`（校正元数据）、`../data/03_labeled/`（标注 JSON 与掩码）。
- 文件名格式：`YYYYMMDD_天气_序号.png`，从中解析天气标签与日期。
- 核验数据完整性，特别是元数据中 GSD 的有效性，反馈异常至贺一冉修正。

**2. 天气分类模型训练**
- 数据来源：`../../data/weather_public/`，需自行下载公开数据集（推荐 FlyAwareV2、Weather Detection Image Dataset），按 `sunny/`、`cloudy/`、`hazy/` 分文件夹存放。
- 脚本位置：`models/weather_classifier/train.py`
- 模型保存路径：`models/weather_classifier/best_weather_model.pth`

**3. 多条件分割模型训练**
- 脚本位置：
  - `models/deeplabv3plus/sunny/train.py`
  - `models/deeplabv3plus/cloudy/train.py`
  - `models/deeplabv3plus/hazy/train.py`
- 数据集划分：每个训练脚本读取 `../../../data/03_labeled/` 下对应天气的图像与掩码（通过文件名过滤）。
- 模型保存路径：各天气目录下的 `best_model.pth`

**4. 模型推理与量化计算**
- 脚本位置：`models/predict_pipeline.py`
- 输入：单张预处理图像路径 + 对应的元数据 JSON 路径
- 执行逻辑：
  1. 加载天气分类模型 `models/weather_classifier/best_weather_model.pth`，预测天气。
  2. 根据预测结果动态加载对应 DeepLabV3+ 模型（`models/deeplabv3plus/{weather}/best_model.pth`）。
  3. 执行分割推理，生成掩码图。
  4. 读取元数据中的 GSD，计算实际面积、占比、浓度等级。
- 输出路径：
  - 掩码可视化图 → `outputs/masks/输入文件名_mask.png`
  - 量化数据 → `outputs/quantifications/输入文件名.json`

**5. 空间仿真脚本开发与交付**
- 脚本位置：`utils/simulation/generate_prediction_mask.py`
- 功能：接收基准掩码路径、面积变化率（如 +0.3 表示增长 30%），使用形态学膨胀/腐蚀操作，逐步变换直至掩码总面积与目标面积一致，输出预测掩码图。
- 输出路径：由调用方（刘俊辉）决定，建议统一输出至 `outputs/masks/`，命名遵循约定规范（如 `YYYYMMDD_predicted_mask.png`）。
- 交付物：脚本本身 + 详细使用说明（包含参数格式、调用示例、依赖库）。

**6. 格式核验与交付**
- 检查 `outputs/` 下所有文件是否符合格式规范，确保展示组可直接读取。
- 与刘俊辉交接仿真脚本，与乔梓阁对齐数据格式。

#### 四、模块分工（一句话界定）
- 航拍组：采集多天气原始图像 → `data/01_raw/`
- 贺一冉：预处理与标注 → `data/02_preprocessed/`、`data/03_labeled/`
- **本人（吴天宇）**：公开数据集 → 训练天气分类模型；标注数据集 → 训练分割模型；推理 + 量化 + 仿真脚本 → 输出至 `outputs/`
- 刘俊辉：读取 `outputs/quantifications/` 进行预测，调用我的仿真脚本生成预测掩码
- 乔梓阁：读取 `outputs/` 构建展示 Demo

#### 五、最终交付物
1. 天气分类模型权重（`models/weather_classifier/best_weather_model.pth`）及训练推理代码。
2. 三个 DeepLabV3+ 分割模型权重（`models/deeplabv3plus/{weather}/best_model.pth`）及训练脚本。
3. 总推理脚本 `models/predict_pipeline.py`。
4. 空间仿真脚本 `utils/simulation/generate_prediction_mask.py` 及详细使用说明。
5. 正射校正脚本（`utils/preprocess/orthorectify.py`）及使用说明。
6. 实测分割掩码图（`outputs/masks/`）与量化数据（`outputs/quantifications/`）。
7. outputs/` 数据格式规范文档。
8. 模型评估报告。