#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无人机飞行参数解析脚本 (parse_drone_metadata.py)
==============================================
功能：
    1. 读取各品牌无人机的飞行参数 JSON 文件。
    2. 自动识别品牌（DJI / Autel / Parrot / Skydio / Custom）。
    3. 使用映射表 `brand_mapping.json` 提取关键字段，
       输出统一的 StandardizedMetadata 类实例。
    4. 对缺失的关键字段进行容错处理（焦距缺失则报错终止）。
    5. 为后续正射校正脚本提供一键式接口。

使用方式：
    from parse_drone_metadata import parse_drone_metadata
    meta = parse_drone_metadata("path/to/drone_params.json")
    print(meta.camera.focal_length)
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

# ────────────────────── 日志配置 ──────────────────────
logger = logging.getLogger("parse_drone_metadata")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(ch)

# ─────────── 标准输出数据结构定义 ───────────
@dataclass
class CameraInfo:
    make: Optional[str] = None               # 相机制造商
    model: Optional[str] = None              # 相机型号
    focal_length: Optional[float] = None     # 实际焦距 (mm) —— 必须字段
    sensor_width: Optional[float] = None     # 传感器宽度 (mm)
    sensor_height: Optional[float] = None    # 传感器高度 (mm)
    image_width: Optional[int] = None        # 原始图像像素宽度
    image_height: Optional[int] = None       # 原始图像像素高度
    white_balance: str = "Unknown"           # 白平衡模式
    dewarp_data: Optional[str] = None        # 畸变参数序列（逗号分隔）

@dataclass
class GPSInfo:
    latitude: float = 0.0
    longitude: float = 0.0
    absolute_altitude: float = 0.0           # 椭球高 (m)
    relative_altitude: float = 0.0           # 相对起飞点高度 (m)

@dataclass
class AttitudeInfo:
    roll: float = 0.0                        # 度
    pitch: float = 0.0
    yaw: float = 0.0

@dataclass
class GimbalInfo:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

@dataclass
class StandardizedMetadata:
    """统一标准元数据结构"""
    reference_brand: str = "Unknown"
    image_name: Optional[str] = None
    capture_datetime: Optional[str] = None
    camera: CameraInfo = field(default_factory=CameraInfo)
    gps: GPSInfo = field(default_factory=GPSInfo)
    attitude: AttitudeInfo = field(default_factory=AttitudeInfo)
    gimbal: GimbalInfo = field(default_factory=GimbalInfo)

    def to_dict(self) -> Dict[str, Any]:
        """将标准化对象转换为字典（方便序列化）"""
        return {
            "reference_brand": self.reference_brand,
            "image_name": self.image_name,
            "capture_datetime": self.capture_datetime,
            "camera": {
                "make": self.camera.make,
                "model": self.camera.model,
                "focal_length": self.camera.focal_length,
                "sensor_width": self.camera.sensor_width,
                "sensor_height": self.camera.sensor_height,
                "image_width": self.camera.image_width,
                "image_height": self.camera.image_height,
                "white_balance": self.camera.white_balance,
                "dewarp_data": self.camera.dewarp_data,
            },
            "gps": {
                "latitude": self.gps.latitude,
                "longitude": self.gps.longitude,
                "absolute_altitude": self.gps.absolute_altitude,
                "relative_altitude": self.gps.relative_altitude,
            },
            "attitude": {
                "roll": self.attitude.roll,
                "pitch": self.attitude.pitch,
                "yaw": self.attitude.yaw,
            },
            "gimbal": {
                "roll": self.gimbal.roll,
                "pitch": self.gimbal.pitch,
                "yaw": self.gimbal.yaw,
            }
        }

# ─────────── 品牌映射表加载 ───────────
def load_brand_mapping(mapping_file: str = None) -> Dict:
    """加载品牌映射配置文件，若未指定则在同目录下查找 brand_mapping.json"""
    if mapping_file is None:
        current_dir = Path(__file__).parent
        mapping_file = current_dir / "brand_mapping.json"

    if not Path(mapping_file).exists():
        raise FileNotFoundError(f"品牌映射文件不存在: {mapping_file}")

    with open(mapping_file, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    logger.info(f"已加载品牌映射文件: {mapping_file}")
    return mapping

# ─────────── 品牌自动识别 ───────────
def identify_brand(raw_json: Dict, mapping: Dict) -> str:
    """
    根据原始 JSON 中的特定字段自动判定无人机品牌。
    返回品牌名称字符串。
    """
    brands = mapping.get("brands", {})

    # 优先使用字段 drone_brand 或 drone_type
    if "drone_brand" in raw_json and raw_json["drone_brand"] in brands:
        return raw_json["drone_brand"]
    if "drone_type" in raw_json and raw_json["drone_type"] in brands:
        return raw_json["drone_type"]

    # 按优先级检测特征字段
    for brand, config in sorted(brands.items(), key=lambda x: x[1].get("priority", 99)):
        detect_fields = config.get("detect_fields", [])
        if not detect_fields:
            continue
        for field in detect_fields:
            if field in raw_json:
                return brand
    raise ValueError("无法识别无人机品牌，请检查参数JSON中是否包含品牌标识字段 (drone_brand / Make 等)")

# ─────────── 字段提取辅助函数 ───────────
def _get_value(raw: Dict, path: str):
    """根据点号分隔的路径从嵌套字典中取值，如 GPS.Latitude"""
    keys = path.split('.')
    val = raw
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val

def safe_float(value, default=0.0):
    """安全转换为浮点数"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """安全转换为整数"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# ─────────── 主解析函数 ───────────
def parse_drone_metadata(json_path: str, mapping_file: str = None) -> StandardizedMetadata:
    """
    解析无人机参数 JSON 文件，返回标准元数据对象。

    参数:
        json_path: 无人机参数 JSON 文件的路径。
        mapping_file: 品牌映射配置文件路径，默认使用同目录下的 brand_mapping.json。

    返回:
        StandardizedMetadata 实例。
    """
    # 1. 加载原始 JSON
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"无人机参数文件不存在: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    logger.info(f"开始解析参数文件: {json_path}")

    # 2. 加载品牌映射表
    mapping = load_brand_mapping(mapping_file)

    # 3. 识别品牌
    brand = identify_brand(raw, mapping)
    logger.info(f"识别到品牌: {brand}")

    brand_config = mapping["brands"].get(brand)
    if not brand_config:
        raise ValueError(f"品牌 {brand} 的配置未在映射表中定义")

    # 4. 处理 Custom 格式（直接映射为标准结构）
    if brand == "Custom":
        meta = StandardizedMetadata(
            reference_brand="Custom",
            image_name=raw.get("image_name"),
            capture_datetime=raw.get("capture_datetime"),
            camera=CameraInfo(
                make=raw.get("camera", {}).get("make"),
                model=raw.get("camera", {}).get("model"),
                focal_length=float(raw["camera"]["focal_length"]),
                sensor_width=raw.get("camera", {}).get("sensor_width"),
                sensor_height=raw.get("camera", {}).get("sensor_height"),
                image_width=raw.get("camera", {}).get("image_width"),
                image_height=raw.get("camera", {}).get("image_height"),
                white_balance=raw.get("camera", {}).get("white_balance", "Unknown"),
                dewarp_data=raw.get("camera", {}).get("dewarp_data"),
            ),
            gps=GPSInfo(
                latitude=raw.get("gps", {}).get("latitude", 0.0),
                longitude=raw.get("gps", {}).get("longitude", 0.0),
                absolute_altitude=raw.get("gps", {}).get("absolute_altitude", 0.0),
                relative_altitude=raw.get("gps", {}).get("relative_altitude", 0.0),
            ),
            attitude=AttitudeInfo(
                roll=raw.get("attitude", {}).get("roll", 0.0),
                pitch=raw.get("attitude", {}).get("pitch", 0.0),
                yaw=raw.get("attitude", {}).get("yaw", 0.0),
            ),
            gimbal=GimbalInfo(
                roll=raw.get("gimbal", {}).get("roll", 0.0),
                pitch=raw.get("gimbal", {}).get("pitch", 0.0),
                yaw=raw.get("gimbal", {}).get("yaw", 0.0),
            )
        )
        _validate_focal_length(meta)
        return meta

    # 5. 使用映射表提取字段
    field_map = brand_config.get("mapping", {})

    # 提取相机信息
    camera = CameraInfo(
        make=_get_value(raw, field_map.get("camera_make", "")),
        model=_get_value(raw, field_map.get("camera_model", "")),
        focal_length=safe_float(_get_value(raw, field_map.get("focal_length", "")), default=None),
        sensor_width=safe_float(_get_value(raw, field_map.get("sensor_width", "")), default=None),
        sensor_height=safe_float(_get_value(raw, field_map.get("sensor_height", "")), default=None),
        image_width=safe_int(_get_value(raw, field_map.get("image_width", "")), default=None),
        image_height=safe_int(_get_value(raw, field_map.get("image_height", "")), default=None),
        white_balance=str(_get_value(raw, field_map.get("white_balance", "")) or "Unknown"),
        dewarp_data=_get_value(raw, field_map.get("dewarp_data", "")) or None,
    )

    # 对缺失传感器尺寸的品牌尝试使用型号默认值
    if (camera.sensor_width is None or camera.sensor_height is None) and camera.model:
        sensor_defaults = brand_config.get("sensor_defaults", {})
        if camera.model in sensor_defaults:
            defaults = sensor_defaults[camera.model]
            if camera.sensor_width is None:
                camera.sensor_width = defaults.get("sensor_width")
            if camera.sensor_height is None:
                camera.sensor_height = defaults.get("sensor_height")
            logger.info(f"使用型号 {camera.model} 的默认传感器尺寸: "
                        f"{camera.sensor_width}x{camera.sensor_height} mm")

    # 提取 GPS
    gps = GPSInfo(
        latitude=safe_float(_get_value(raw, field_map.get("gps_lat", ""))),
        longitude=safe_float(_get_value(raw, field_map.get("gps_lon", ""))),
        absolute_altitude=safe_float(_get_value(raw, field_map.get("gps_abs_alt", ""))),
        relative_altitude=safe_float(_get_value(raw, field_map.get("gps_rel_alt", ""))),
    )

    # 提取姿态
    attitude = AttitudeInfo(
        roll=safe_float(_get_value(raw, field_map.get("att_roll", ""))),
        pitch=safe_float(_get_value(raw, field_map.get("att_pitch", ""))),
        yaw=safe_float(_get_value(raw, field_map.get("att_yaw", ""))),
    )

    # 提取云台 (对缺失字段置0)
    gimbal = GimbalInfo(
        roll=safe_float(_get_value(raw, field_map.get("gimbal_roll", "")), default=0.0),
        pitch=safe_float(_get_value(raw, field_map.get("gimbal_pitch", "")), default=0.0),
        yaw=safe_float(_get_value(raw, field_map.get("gimbal_yaw", "")), default=0.0),
    )

    # 提取通用字段
    image_name = raw.get("image_name") or raw.get("image_name")
    capture_dt = raw.get("capture_datetime") or _get_value(raw, field_map.get("capture_datetime", ""))

    # 组装标准对象
    meta = StandardizedMetadata(
        reference_brand=brand,
        image_name=image_name,
        capture_datetime=capture_dt,
        camera=camera,
        gps=gps,
        attitude=attitude,
        gimbal=gimbal,
    )

    # 6. 必须字段校验
    _validate_focal_length(meta)

    logger.info("参数解析完成。")
    return meta

def _validate_focal_length(meta: StandardizedMetadata):
    """校验焦距是否为有效数值"""
    if meta.camera.focal_length is None or meta.camera.focal_length <= 0:
        raise ValueError(f"焦距 focal_length 缺失或无效（当前值: {meta.camera.focal_length}），无法进行后续处理。")