#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无人机参数解析脚本 (parse_drone_metadata.py)
==============================================
提供两种解析方式：
1. parse_drone_metadata_from_image(image_path) → 直接从 RAW/DNG 图像中提取元数据（依赖 exiftool）
2. parse_drone_metadata(json_path) → 从 JSON 参数文件中解析（备用）

输出统一结构 StandardizedMetadata，供 orthorectify.py 调用。
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import shutil

def find_exiftool() -> str:
    """查找 exiftool 可执行文件路径"""
    path = os.environ.get("EXIFTOOL_PATH")
    if path and os.path.isfile(path):
        return path
    path = shutil.which("exiftool")
    if path:
        return path
    common_paths = [
        r"C:\exiftool\exiftool.exe",
        r"C:\Program Files\exiftool\exiftool.exe",
        r"C:\tools\exiftool.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    raise RuntimeError(
        "找不到 exiftool，请将 exiftool.exe 所在目录加入系统 PATH，"
        "或设置环境变量 EXIFTOOL_PATH 指向它的完整路径。"
    )

logger = logging.getLogger("parse_drone_metadata")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(ch)

# ==================== 标准数据结构 ====================
@dataclass
class CameraInfo:
    make: Optional[str] = None
    model: Optional[str] = None
    focal_length: Optional[float] = None
    sensor_width: Optional[float] = None
    sensor_height: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    white_balance: str = "Unknown"
    dewarp_data: Optional[str] = None

@dataclass
class GPSInfo:
    latitude: float = 0.0
    longitude: float = 0.0
    absolute_altitude: float = 0.0
    relative_altitude: float = 0.0

@dataclass
class AttitudeInfo:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

@dataclass
class GimbalInfo:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

@dataclass
class StandardizedMetadata:
    reference_brand: str = "Unknown"
    image_name: Optional[str] = None
    capture_datetime: Optional[str] = None
    camera: CameraInfo = field(default_factory=CameraInfo)
    gps: GPSInfo = field(default_factory=GPSInfo)
    attitude: AttitudeInfo = field(default_factory=AttitudeInfo)
    gimbal: GimbalInfo = field(default_factory=GimbalInfo)

    def to_dict(self):
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

# ==================== 辅助函数 ====================
def safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def load_brand_mapping(mapping_file: str = None) -> Dict:
    if mapping_file is None:
        current_dir = Path(__file__).parent
        mapping_file = current_dir / "brand_mapping.json"
    if not Path(mapping_file).exists():
        raise FileNotFoundError(f"品牌映射文件不存在: {mapping_file}")
    with open(mapping_file, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    return mapping

def _get_value(raw: Dict, path: str):
    keys = path.split('.')
    val = raw
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val

# ==================== 从 JSON 解析（备用） ====================
def parse_drone_metadata(json_path: str, mapping_file: str = None) -> StandardizedMetadata:
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"参数文件不存在: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    mapping = load_brand_mapping(mapping_file)

    brand = _identify_brand_from_dict(raw, mapping["brands"])
    logger.info(f"从 JSON 识别品牌: {brand}")
    brand_config = mapping["brands"].get(brand)
    if not brand_config:
        raise ValueError(f"品牌 {brand} 配置缺失")

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

    field_map = brand_config.get("mapping", {})
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
    _inject_sensor_defaults(camera, brand_config)

    gps = GPSInfo(
        latitude=safe_float(_get_value(raw, field_map.get("gps_lat", ""))),
        longitude=safe_float(_get_value(raw, field_map.get("gps_lon", ""))),
        absolute_altitude=safe_float(_get_value(raw, field_map.get("gps_abs_alt", ""))),
        relative_altitude=safe_float(_get_value(raw, field_map.get("gps_rel_alt", ""))),
    )
    attitude = AttitudeInfo(
        roll=safe_float(_get_value(raw, field_map.get("att_roll", ""))),
        pitch=safe_float(_get_value(raw, field_map.get("att_pitch", ""))),
        yaw=safe_float(_get_value(raw, field_map.get("att_yaw", ""))),
    )
    gimbal = GimbalInfo(
        roll=safe_float(_get_value(raw, field_map.get("gimbal_roll", "")), default=0.0),
        pitch=safe_float(_get_value(raw, field_map.get("gimbal_pitch", "")), default=-90.0),
        yaw=safe_float(_get_value(raw, field_map.get("gimbal_yaw", "")), default=0.0),
    )

    meta = StandardizedMetadata(
        reference_brand=brand,
        image_name=raw.get("image_name"),
        capture_datetime=raw.get("capture_datetime"),
        camera=camera,
        gps=gps,
        attitude=attitude,
        gimbal=gimbal,
    )
    _validate_focal_length(meta)
    return meta

def _identify_brand_from_dict(raw: Dict, brands: Dict) -> str:
    if "drone_brand" in raw and raw["drone_brand"] in brands:
        return raw["drone_brand"]
    if "drone_type" in raw and raw["drone_type"] in brands:
        return raw["drone_type"]
    for brand, config in sorted(brands.items(), key=lambda x: x[1].get("priority", 99)):
        for field in config.get("detect_fields", []):
            if field in raw:
                val = str(raw[field]).lower()
                if brand.lower() in val:
                    return brand
    raise ValueError("无法识别品牌")

def _inject_sensor_defaults(camera: CameraInfo, brand_config: Dict):
    """注入传感器物理尺寸，优先精确匹配型号，其次尝试通用传感器描述符回退"""
    if camera.sensor_width is not None and camera.sensor_height is not None:
        return
    sensor_defaults = brand_config.get("sensor_defaults", {})
    if camera.model and camera.model in sensor_defaults:
        defaults = sensor_defaults[camera.model]
        if camera.sensor_width is None:
            camera.sensor_width = defaults.get("sensor_width")
        if camera.sensor_height is None:
            camera.sensor_height = defaults.get("sensor_height")
        logger.info(f"已注入传感器尺寸默认值（型号匹配）: {camera.model} → {camera.sensor_width}x{camera.sensor_height} mm")
        return
    # 回退：尝试从 EXIF 或 MakerNote 中提取传感器描述，匹配通用条目
    desc = None
    if camera.model:
        desc = sensor_defaults.get(camera.model)  # 已经试过，这里是 None
    if desc is None and camera.model:
        # 某些元数据可能包含传感器描述（如 "1-inch CMOS"），可在此扩展
        pass
    logger.warning("未能为当前相机型号匹配传感器尺寸，GSD 将可能为 null")

def _validate_focal_length(meta: StandardizedMetadata):
    if meta.camera.focal_length is None or meta.camera.focal_length <= 0:
        raise ValueError(f"焦距无效: {meta.camera.focal_length}")

# ─────────── 白平衡数值映射 ───────────
_WB_CODE_MAP = {
    "0": "Auto",
    "1": "Manual",
    "2": "Daylight",
    "3": "Cloudy",
    "4": "Tungsten",
    "5": "Fluorescent",
    "6": "Flash",
    "7": "Shade",
    "8": "Custom",
    "9": "Kelvin",
}

def _normalize_white_balance(wb_raw: str) -> str:
    if not wb_raw:
        return "Unknown"
    s = str(wb_raw).strip()
    if s.isdigit() and s in _WB_CODE_MAP:
        return _WB_CODE_MAP[s]
    s_lower = s.lower()
    if "auto" in s_lower or "awb" in s_lower:
        return "Auto"
    return s

# ==================== 从图像提取（主接口） ====================
def parse_drone_metadata_from_image(image_path: str,
                                    mapping_file: str = None) -> StandardizedMetadata:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图像文件不存在: {image_path}")

    exiftool_path = find_exiftool()
    cmd = [exiftool_path, "-json", "-G", "-n", image_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True,
                                timeout=30)
        metadata_list = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"exiftool 执行失败: {e.stderr}")
    except Exception as e:
        raise RuntimeError(f"解析 exiftool 输出出错: {e}")

    if not metadata_list:
        raise ValueError("exiftool 未返回元数据")

    exif = metadata_list[0]

    mapping = load_brand_mapping(mapping_file)
    brands = mapping["brands"]

    brand = _identify_brand_from_exif(exif, brands)
    logger.info(f"从图像识别品牌: {brand}")
    brand_config = brands.get(brand)
    if not brand_config:
        brand_config = {}

    def get_tag(*paths):
        for p in paths:
            if p in exif:
                return exif[p]
        return None

    # 通用相机信息
    camera = CameraInfo(
        make=get_tag("EXIF:Make", "MakerNotes:Make"),
        model=get_tag("EXIF:Model", "MakerNotes:Model"),
        focal_length=safe_float(get_tag("EXIF:FocalLength"), default=None),
        sensor_width=None,
        sensor_height=None,
        image_width=safe_int(get_tag("EXIF:ImageWidth", "File:ImageWidth")),
        image_height=safe_int(get_tag("EXIF:ImageHeight", "File:ImageHeight")),
        white_balance=_normalize_white_balance(
            str(get_tag("EXIF:WhiteBalance", "MakerNotes:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint") or "")
        ),
        dewarp_data=get_tag("XMP-drone-dji:DewarpData")
    )

    # ─────────── 品牌特有标签补充 ───────────

    if brand == "DJI":
        # 统一使用 get_tag 多路径回退，不再依赖 get_dji 的隔离逻辑
        gps = GPSInfo(
            latitude=safe_float(get_tag(
                "XMP-drone-dji:GPSLatitude", "XMP:GPSLatitude",
                "EXIF:GPSLatitude", "GPSLatitude"
            )),
            longitude=safe_float(get_tag(
                "XMP-drone-dji:GPSLongitude", "XMP:GPSLongitude",
                "EXIF:GPSLongitude", "GPSLongitude"
            )),
            absolute_altitude=safe_float(get_tag(
                "XMP-drone-dji:AbsoluteAltitude", "XMP:AbsoluteAltitude",
                "EXIF:GPSAltitude", "AbsoluteAltitude"
            )),
            relative_altitude=safe_float(get_tag(
                "XMP-drone-dji:RelativeAltitude", "XMP:RelativeAltitude",
                "RelativeAltitude"
            ))
        )
        attitude = AttitudeInfo(
            roll=safe_float(get_tag(
                "XMP-drone-dji:FlightRollDegree", "XMP:FlightRollDegree",
                "FlightRollDegree"
            )),
            pitch=safe_float(get_tag(
                "XMP-drone-dji:FlightPitchDegree", "XMP:FlightPitchDegree",
                "FlightPitchDegree"
            )),
            yaw=safe_float(get_tag(
                "XMP-drone-dji:FlightYawDegree", "XMP:FlightYawDegree",
                "FlightYawDegree"
            ))
        )
        gimbal = GimbalInfo(
            roll=safe_float(get_tag(
                "XMP-drone-dji:GimbalRollDegree", "XMP:GimbalRollDegree",
                "GimbalRollDegree"
            )),
            pitch=safe_float(get_tag(
                "XMP-drone-dji:GimbalPitchDegree", "XMP:GimbalPitchDegree",
                "GimbalPitchDegree"
            ), default=-90.0),
            yaw=safe_float(get_tag(
                "XMP-drone-dji:GimbalYawDegree", "XMP:GimbalYawDegree",
                "GimbalYawDegree"
            ))
        )
        # DJI 白平衡：优先专用标签，若有则覆盖通用值
        wb_dji = get_tag("XMP-drone-dji:WhiteBalance", "XMP:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint")
        if wb_dji:
            camera.white_balance = _normalize_white_balance(str(wb_dji))

    elif brand == "Skydio":
        # Skydio XMP 命名空间：XMP-drone-skydio
        gps = GPSInfo(
            latitude=safe_float(get_tag("XMP-drone-skydio:GPSLatitude", "EXIF:GPSLatitude")),
            longitude=safe_float(get_tag("XMP-drone-skydio:GPSLongitude", "EXIF:GPSLongitude")),
            absolute_altitude=safe_float(get_tag("XMP-drone-skydio:AbsoluteAltitude", "EXIF:GPSAltitude")),
            relative_altitude=safe_float(get_tag("XMP-drone-skydio:RelativeAltitude"))
        )
        attitude = AttitudeInfo(
            roll=safe_float(get_tag("XMP-drone-skydio:FlightRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-skydio:FlightPitchDegree")),
            yaw=safe_float(get_tag("XMP-drone-skydio:FlightYawDegree"))
        )
        gimbal = GimbalInfo(
            roll=safe_float(get_tag("XMP-drone-skydio:GimbalRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-skydio:GimbalPitchDegree"), default=-90.0),
            yaw=safe_float(get_tag("XMP-drone-skydio:GimbalYawDegree"))
        )
        wb_raw = str(get_tag("EXIF:WhiteBalance", "MakerNotes:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint") or "")
        camera.white_balance = _normalize_white_balance(wb_raw)

    elif brand == "Parrot":
        gps = GPSInfo(
            latitude=safe_float(get_tag("EXIF:GPSLatitude")),
            longitude=safe_float(get_tag("EXIF:GPSLongitude")),
            absolute_altitude=safe_float(get_tag("EXIF:GPSAltitude")),
            relative_altitude=safe_float(get_tag("XMP-drone-parrot:RelativeAltitude"))
        )
        attitude = AttitudeInfo(
            roll=safe_float(get_tag("XMP-drone-parrot:FlightRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-parrot:FlightPitchDegree")),
            yaw=safe_float(get_tag("XMP-drone-parrot:FlightYawDegree"))
        )
        gimbal = GimbalInfo(
            roll=safe_float(get_tag("XMP-drone-parrot:GimbalRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-parrot:GimbalPitchDegree"), default=-90.0),
            yaw=safe_float(get_tag("XMP-drone-parrot:GimbalYawDegree"))
        )
        wb_raw = str(get_tag("EXIF:WhiteBalance", "MakerNotes:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint") or "")
        camera.white_balance = _normalize_white_balance(wb_raw)

    elif brand == "Autel":
        gps = GPSInfo(
            latitude=safe_float(get_tag("EXIF:GPSLatitude")),
            longitude=safe_float(get_tag("EXIF:GPSLongitude")),
            absolute_altitude=safe_float(get_tag("EXIF:GPSAltitude")),
            relative_altitude=safe_float(get_tag("XMP-drone-autel:RelativeAltitude"))
        )
        attitude = AttitudeInfo(
            roll=safe_float(get_tag("XMP-drone-autel:FlightRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-autel:FlightPitchDegree")),
            yaw=safe_float(get_tag("XMP-drone-autel:FlightYawDegree"))
        )
        gimbal = GimbalInfo(
            roll=safe_float(get_tag("XMP-drone-autel:GimbalRollDegree")),
            pitch=safe_float(get_tag("XMP-drone-autel:GimbalPitchDegree"), default=-90.0),
            yaw=safe_float(get_tag("XMP-drone-autel:GimbalYawDegree"))
        )
        wb_raw = str(get_tag("EXIF:WhiteBalance", "MakerNotes:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint") or "")
        camera.white_balance = _normalize_white_balance(wb_raw)

    else:
        gps = GPSInfo(
            latitude=safe_float(get_tag("EXIF:GPSLatitude")),
            longitude=safe_float(get_tag("EXIF:GPSLongitude")),
            absolute_altitude=safe_float(get_tag("EXIF:GPSAltitude")),
            relative_altitude=safe_float(get_tag("XMP:RelativeAltitude"))
        )
        attitude = AttitudeInfo(
            roll=safe_float(get_tag("XMP:FlightRollDegree")),
            pitch=safe_float(get_tag("XMP:FlightPitchDegree")),
            yaw=safe_float(get_tag("XMP:FlightYawDegree"))
        )
        gimbal = GimbalInfo(
            roll=safe_float(get_tag("XMP:GimbalRollDegree")),
            pitch=safe_float(get_tag("XMP:GimbalPitchDegree"), default=-90.0),
            yaw=safe_float(get_tag("XMP:GimbalYawDegree"))
        )
        wb_raw = str(get_tag("EXIF:WhiteBalance", "MakerNotes:WhiteBalance", "WhiteBalance", "EXIF:WhitePoint") or "")
        camera.white_balance = _normalize_white_balance(wb_raw)

    # 使用传感器特征库补充
    _inject_sensor_defaults(camera, brand_config)

    image_name = os.path.basename(image_path)
    capture_dt = get_tag("EXIF:DateTimeOriginal", "EXIF:CreateDate")

    meta = StandardizedMetadata(
        reference_brand=brand,
        image_name=image_name,
        capture_datetime=capture_dt,
        camera=camera,
        gps=gps,
        attitude=attitude,
        gimbal=gimbal,
    )

    _validate_focal_length(meta)
    return meta

def _identify_brand_from_exif(exif: Dict, brands: Dict) -> str:
    make = exif.get("EXIF:Make") or exif.get("MakerNotes:Make") or ""
    make_lower = make.lower()
    for brand in brands:
        if brand.lower() in make_lower:
            return brand
    for key in exif:
        for brand in ["DJI", "Parrot", "Skydio", "Autel"]:
            if brand.lower() in key.lower():
                return brand
    return "Custom"