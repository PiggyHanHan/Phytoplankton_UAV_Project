# 无人机航拍正射校正脚本使用说明

## 环境要求
- Python 3.8+
- 安装依赖：`pip install rawpy Pillow geopy`  
  > `geopy` 为可选项，缺失时将自动使用简化的球面距离公式，不影响功能。

## 文件清单
确保以下三个文件位于 `utils/preprocess/` 目录下：
- `orthorectify.py`  （主脚本）
- `parse_drone_metadata.py` （无人机参数解析器）
- `brand_mapping.json` （品牌字段映射表）

## 两种工作模式

| 模式 | 命令参数 | 姿态/白平衡 | 焦距一致性 | GPS/高度 |
|:---|:---|:---:|:---:|:---:|
| 用户端 | `--mode user` | ✅ 必检 | 可选（`--check-focal`） | ✅ 必检（需提供基准） |
| 训练数据 | `--mode training` | ✅ 必检 | ❌ 不检 | ❌ 不检 |

- **用户端**：适用于“我的池塘”中用户上传新航拍图，确保与池塘基准的位置、高度、焦距一致。
- **训练数据**：适用于混合多水域的训练数据批处理，只保证图像垂直、白平衡锁定，不限制空间参数。

---

## 使用指令

### 用户端单张处理（全规范校验）
```bash
python utils/preprocess/orthorectify.py \
  --raw data/01_raw/images/20240315_sunny_001.RAW \
  --json data/01_raw/drone_json/20240315_sunny_001.json \
  --out data/02_preprocessed \
  --mode user \
  --ref-lat 30.12345 --ref-lon 114.56789 --ref-alt 40.5 \
  --check-focal --gps-threshold 5 --alt-threshold 10
```

### 用户端批量处理（同一池塘多次飞行）
```bash
python utils/preprocess/orthorectify.py \
  --raw-dir data/01_raw/images \
  --json-dir data/01_raw/drone_json \
  --out data/02_preprocessed \
  --mode user \
  --ref-lat 30.12345 --ref-lon 114.56789 --ref-alt 40.5 \
  --check-focal
```

###训练数据批量处理
```bash
python utils/preprocess/orthorectify.py \
  --raw-dir data/01_raw/images \
  --json-dir data/01_raw/drone_json \
  --out data/02_preprocessed \
  --mode training
```

## 补充说明

1. **焦距校验开关**：  
   - 用户端建议始终加 `--check-focal`，保证同一池塘 GSD 可比。  
   - 训练模式若不加该参数，即使混合不同焦距的数据也不会报错。

2. **空间基准**：第一次上传池塘图像时，应记录其 GPS 经纬度和相对高度作为基准值，此后每次上传均使用相同的 `--ref-lat`、`--ref-lon`、`--ref-alt` 进行校验。

3. **批量处理逻辑**：  
   `process_batch` 会自动匹配 `raw_dir` 下所有 `.RAW` / `.DNG` 文件与 `json_dir` 下同名 JSON，逐张处理，处理失败会跳过并记录日志，不会中断整体任务。

现在你可以直接将上述两个文件放入项目中使用。