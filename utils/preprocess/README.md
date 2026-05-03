# 无人机航拍正射校正预处理脚本 — 使用说明

## 一、功能概述

本脚本实现 **一键式正射校正预处理**：  
- 直接从 **RAW / DNG** 图像内嵌的 EXIF 和 XMP 元数据中提取无人机飞行参数（品牌、姿态、GPS、焦距、白平衡等），**无需任何额外的 JSON 参数文件**。  
- **智能白平衡识别**：自动适配不同相机/无人机写入路径（`EXIF:WhiteBalance`、`EXIF:WhitePoint`、`XMP-drone-dji:WhiteBalance` 等），并将 `Auto`、`AWB`、数字代码 `0` 等自动白平衡变体统一标记为 `Auto`，方便后续校验。  
- **图像尺寸自动修正**：RAW/DNG 解码后使用真实像素尺寸覆盖 EXIF 中可能错误的缩略图尺寸，确保地面采样距离（GSD）计算准确。  
- **自动校验**：姿态（云台俯仰、横滚）、白平衡、可选焦距一致性、可选空间位置（GPS/高度）校验，并计算理论 GSD。  
- **标准化输出**：将 RAW 图像解码、等比缩放至长边 ≤1024（不放大）、居中黑边填充为 1024×1024 PNG，同步生成包含 GSD、有效区域、原始尺寸等信息的元数据 JSON。

支持 **“用户端”** 和 **“训练数据”** 两种处理模式，适配不同的校验强度。
- 注：已对大部分主流机型进行适配，过时机型可能由于参数字段缺失或无法识别而无法上传
---

## 二、环境要求

### 系统依赖
- **exiftool**（必须）：用于从图像中提取完整元数据  
  安装方式：
  - Ubuntu/Debian：`sudo apt install exiftool`
  - macOS：`brew install exiftool`
  - Windows：从 [exiftool.org](https://exiftool.org/) 下载 `exiftool.exe` 并放入 PATH  
  验证安装：终端执行 `exiftool -ver`，应显示版本号。

### Python 依赖
```bash
pip install rawpy Pillow
```
> `geopy` 为可选项，若需使用更高精度的 GPS 校验可安装，否则脚本自动使用简化的球面距离公式，不影响功能。

---

## 三、数据准备

将无人机航拍原图（RAW 或 DNG 格式）直接放入 `data/01_raw/` 目录，**无需**创建额外的 `drone_json` 文件夹。  
文件命名须遵循项目规范：  
```
YYYYMMDD_天气_序号.RAW (或 .DNG)
例如：20240315_sunny_001.DNG
```
天气标签取值：`sunny`、`cloudy`、`hazy`

---

## 四、两种工作模式

| 模式 | 命令参数 | 校验内容 |
|:---|:---|:---|
| **用户端** | `--mode user` | ① 云台俯仰 -90°±3° ② 横滚 ≤2° ③ 白平衡非自动（**白平衡为 `Unknown` 时拒绝**） ④ 焦距一致性（可选，通过 `--check-focal` 启用） ⑤ GPS / 高度偏差（需提供池塘基准） |
| **训练数据** | `--mode training` | ① 云台俯仰 -90°±3° ② 横滚 ≤2° ③ 白平衡非自动（**白平衡为 `Unknown` 时仅警告**） ④ 不校验焦距一致性、⑤ 不校验空间位置 |

- **用户端**：适用于“我的池塘”场景，同一水体多次飞行，需保证位置、高度、焦距一致，以确保时间序列可比。  
- **训练数据**：适用于混合多水域的标注数据批量预处理，只保证图像垂直与色彩一致，不限制拍摄位置。

---

## 五、使用方法

### 5.1 用户端单张处理（全规范校验）

```bash
python utils/preprocess/orthorectify.py \
  --raw data/01_raw/20240315_sunny_001.DNG \
  --out data/02_preprocessed \
  --mode user \
  --ref-lat 30.12345 --ref-lon 114.56789 --ref-alt 40.5 \
  --check-focal
```
- `--ref-lat`、`--ref-lon`、`--ref-alt`：池塘首次上传时记录的基准值（纬度、经度、相对高度，单位：米）。  
- `--check-focal`：强制要求焦距与首次上传的基准一致（偏差超过 0.5 mm 则拒绝）。  
- `--gps-threshold`（默认 5 米）、`--alt-threshold`（默认 10%）可自定义容差。

### 5.2 用户端批量处理（同一池塘多次飞行）

```bash
python utils/preprocess/orthorectify.py \
  --raw-dir data/01_raw \
  --out data/02_preprocessed \
  --mode user \
  --ref-lat 30.12345 --ref-lon 114.56789 --ref-alt 40.5 \
  --check-focal
```
脚本将自动遍历 `data/01_raw` 下的所有 `.RAW` 和 `.DNG` 文件，逐张处理；遇到校验失败的文件会跳过并记录日志，不会中断整体任务。

### 5.3 训练数据批量处理（放宽限制）

```bash
python utils/preprocess/orthorectify.py \
  --raw-dir data/01_raw \
  --out data/02_preprocessed \
  --mode training
```
- 不限制拍摄位置、高度、焦距，仅保证图像来自垂直俯拍且白平衡锁定。

---

## 六、输出结果

处理完成后，在 `data/02_preprocessed/` 下生成：

```
data/02_preprocessed/
├── images/
│   └── 20240315_sunny_001.png      ← 1024×1024，居中有效区域
└── meta/
    └── 20240315_sunny_001_meta.json
```

元数据 JSON 包含以下关键字段：

| 字段 | 说明 |
|:---|:---|
| `gsd_m_per_pixel` | 地面采样距离（米/像素），基于真实图像尺寸计算；若传感器尺寸未知则为 `null` |
| `valid_region` | 归一化边界（左、上、右、下），用于从 1024 画布中提取有效图像区域 |
| `camera.focal_length_mm` | 实际焦距（mm） |
| `camera.white_balance` | 白平衡模式（例如 `Daylight`、`Cloudy`、`Sunny`、`Auto` 等；若无法确定则为 `Unknown`） |
| `camera.image_width_original` / `image_height_original` | 真实解码后的原始图像尺寸（像素） |
| `gps.latitude`, `gps.longitude` | 拍摄点经纬度 |
| `gps.relative_altitude_m` | 相对起飞点高度（米） |
| `attitude.gimbal_pitch` | 云台俯仰角（°） |
| `attitude.aircraft_roll` | 机体横滚角（°） |

> **注意**：`camera.white_balance` 值为 `Auto` 表示图像使用了自动白平衡（会被校验拒绝）；`Unknown` 表示在所有已知路径中均未找到白平衡信息（用户模式下会被拒绝，训练模式下会警告）。

---

## 七、常见问题及排查

| 问题 | 可能原因 | 解决方法 |
|:---|:---|:---|
| “exiftool 未找到” | 系统未安装 exiftool | 根据操作系统安装，并确认终端可执行 `exiftool` |
| “无法识别品牌” | 图像中缺少品牌标识字段 | 暂不支持的手动品牌，可临时在脚本中指定品牌（修改 `identify_brand_from_exif`） |
| “焦距缺失” | 部分镜头/机型不在 EXIF 中记录焦距 | 请航拍组确认相机设置，或手动补充焦距值 |
| 姿态校验报错 | 云台俯仰角或横滚角超过容差 | 确保无人机以垂直 -90° 拍摄，并尽量保持水平 |
| 白平衡校验不通过（`Auto`） | 相机未锁定白平衡预设 | 修改相机设置为“日光”或“阴天”等固定模式，重新拍摄 |
| 白平衡数据缺失（`Unknown`） | 图像元数据中不存在可识别的白平衡标签 | 确认相机是否写入了白平衡信息；若确定使用了固定预设，可在标注时标记，或将 `validate_white_balance` 放宽 |
| GSD 显示为 `null` | 无法从图像元数据或 `brand_mapping.json` 获取传感器物理尺寸 | 在 `brand_mapping.json` 中补充对应相机型号的传感器默认值，或手动填入元数据 |
| GSD 值异常（过大或过小） | EXIF 图像尺寸为缩略图尺寸已被自动修正，但传感器尺寸配置错误 | 检查 `brand_mapping.json` 中对应机型的 `sensor_width/height` 是否正确 |
| 输出图像有效区域比例异常 | 原始图像长宽比特殊或 EXIF 尺寸与实际严重不符 | 检查原始 DNG 是否完整，或手动提供图像尺寸 |

---

## 八、文件清单

确保 `utils/preprocess/` 目录下包含以下文件：

- `orthorectify.py` （本正射校正脚本）
- `parse_drone_metadata.py` （无人机参数解析模块）
- `brand_mapping.json` （品牌字段映射及传感器默认尺寸库）

根据上述说明即可直接使用，无需额外配置。