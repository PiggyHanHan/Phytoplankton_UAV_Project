#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正射校正脚本 (orthorectify.py) —— 图像直读版
==============================================
直接从 RAW / DNG 文件中提取无人机参数（依赖 exiftool），
无需额外的 JSON 参数文件。

模式：
- 用户端（--mode user）：全规范校验（姿态、白平衡、GPS、高度、焦距一致性）
- 训练数据（--mode training）：仅校验姿态与白平衡，放宽空间与焦距限制

依赖安装：
    pip install rawpy Pillow
    # exiftool 需要系统安装：sudo apt install exiftool   (Ubuntu) 或 brew install exiftool (macOS)
"""

import os
import sys
import json
import argparse
import logging
import math
from pathlib import Path
from typing import Optional, Tuple

import rawpy
from PIL import Image

try:
    from geopy.distance import geodesic
    _USE_GEOPY = True
except ImportError:
    _USE_GEOPY = False

from parse_drone_metadata import parse_drone_metadata_from_image, StandardizedMetadata

# ─────────── 配置 ───────────
IMAGE_SIZE = 1024
MAX_LONG_EDGE = 1024
ALLOWED_PITCH_DEVIATION = 3.0
ALLOWED_ROLL_DEVIATION = 2.0
RAW_DECODE_USE_CAMERA_WB = True

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("orthorectify")

# ─────────── 辅助 ───────────
def _haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ─────────── 校验函数 ───────────
def validate_attitude(meta: StandardizedMetadata):
    if abs(meta.gimbal.pitch + 90.0) > ALLOWED_PITCH_DEVIATION:
        raise ValueError(
            f"云台俯仰角 {meta.gimbal.pitch}° 偏离垂直基准（-90°），允许 ±{ALLOWED_PITCH_DEVIATION}°"
        )
    for name, val in [("机体 Roll", meta.attitude.roll), ("云台 Roll", meta.gimbal.roll)]:
        if abs(val) > ALLOWED_ROLL_DEVIATION:
            raise ValueError(f"{name} {val}° 超出允许范围（±{ALLOWED_ROLL_DEVIATION}°）")

def validate_white_balance(meta: StandardizedMetadata, mode: str = "training"):
    """禁止自动白平衡（已归一化为 'Auto' 或原始值），对 Unknown 按模式区别处理"""
    wb = meta.camera.white_balance or ""
    if wb == "Auto" or "auto" in wb.lower():
        raise ValueError(f"白平衡模式为 '{wb}'，项目规范要求锁定预设，禁止自动模式")
    if wb == "Unknown":
        msg = "白平衡数据缺失（Unknown），无法确认是否锁定预设"
        if mode == "user":
            raise ValueError(msg)
        else:
            logger.warning(msg)

def validate_focal_consistency(meta: StandardizedMetadata,
                               baseline_focal: Optional[float]) -> Optional[float]:
    current = meta.camera.focal_length
    if current is None or current <= 0:
        raise ValueError("焦距数据无效")
    if baseline_focal is None:
        return current
    if abs(current - baseline_focal) > 0.5:
        raise ValueError(
            f"焦距不一致：基准 {baseline_focal} mm，当前 {current} mm"
        )
    return baseline_focal

def validate_spatial(meta: StandardizedMetadata,
                     ref_lat: float, ref_lon: float, ref_alt: float,
                     gps_threshold: float = 5.0,
                     alt_threshold_percent: float = 10.0):
    if ref_lat is not None and ref_lon is not None:
        if _USE_GEOPY:
            dist = geodesic((meta.gps.latitude, meta.gps.longitude),
                            (ref_lat, ref_lon)).meters
        else:
            dist = _haversine_distance(meta.gps.latitude, meta.gps.longitude,
                                       ref_lat, ref_lon)
        if dist > gps_threshold:
            raise ValueError(
                f"GPS 位置偏差 {dist:.1f} m 超过允许阈值 {gps_threshold} m"
            )
    if ref_alt is not None and ref_alt > 0:
        current_alt = meta.gps.relative_altitude
        deviation = abs(current_alt - ref_alt) / ref_alt * 100
        if deviation > alt_threshold_percent:
            raise ValueError(
                f"相对高度偏差 {deviation:.1f}%（当前 {current_alt}m，基准 {ref_alt}m），"
                f"超过允许的 {alt_threshold_percent}%"
            )

# ─────────── GSD 计算 ───────────
def compute_gsd(meta: StandardizedMetadata) -> Optional[float]:
    rel_alt = meta.gps.relative_altitude
    if rel_alt is None or rel_alt <= 0:
        raise ValueError("相对高度缺失或无效，无法计算 GSD")
    focal_m = meta.camera.focal_length / 1000.0
    sensor_w = meta.camera.sensor_width
    sensor_h = meta.camera.sensor_height
    img_w = meta.camera.image_width
    img_h = meta.camera.image_height

    if sensor_w is not None and img_w is not None:
        return (sensor_w / 1000.0 / img_w) * (rel_alt / focal_m)
    if sensor_h is not None and img_h is not None:
        return (sensor_h / 1000.0 / img_h) * (rel_alt / focal_m)
    logger.warning("传感器尺寸缺失，GSD 将设为 null")
    return None

# ─────────── 图像处理 ───────────
def decode_raw(raw_path: str) -> Image.Image:
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"RAW 文件不存在: {raw_path}")
    logger.info(f"解码 RAW: {raw_path}")
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(use_camera_wb=RAW_DECODE_USE_CAMERA_WB,
                              no_auto_bright=True)
    return Image.fromarray(rgb)

def resize_and_pad(image: Image.Image) -> Tuple[Image.Image, Tuple[float, float, float, float]]:
    w, h = image.size
    max_edge = max(w, h)
    if max_edge > IMAGE_SIZE:
        scale = IMAGE_SIZE / max_edge
    else:
        scale = 1.0
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    padded = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0))
    left = (IMAGE_SIZE - new_w) // 2
    top = (IMAGE_SIZE - new_h) // 2
    padded.paste(resized, (left, top))
    boundary = (left / IMAGE_SIZE, top / IMAGE_SIZE,
                (left + new_w) / IMAGE_SIZE, (top + new_h) / IMAGE_SIZE)
    logger.info(f"缩放至 {new_w}x{new_h}，填充至 {IMAGE_SIZE}x{IMAGE_SIZE}，边界: {boundary}")
    return padded, boundary

def save_outputs(image: Image.Image, image_stem: str, output_dir: str,
                 gsd: Optional[float], valid_region: Tuple[float, ...],
                 meta_obj: StandardizedMetadata):
    out_dir = Path(output_dir)
    img_dir = out_dir / "images"
    meta_dir = out_dir / "meta"
    img_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    img_path = img_dir / f"{image_stem}.png"
    image.save(img_path, "PNG")
    logger.info(f"图像已保存: {img_path}")

    meta = {
        "image_stem": image_stem,
        "gsd_m_per_pixel": gsd,
        "valid_region": {
            "left": valid_region[0], "top": valid_region[1],
            "right": valid_region[2], "bottom": valid_region[3]
        },
        "camera": {
            "focal_length_mm": meta_obj.camera.focal_length,
            "sensor_width_mm": meta_obj.camera.sensor_width,
            "sensor_height_mm": meta_obj.camera.sensor_height,
            "image_width_original": meta_obj.camera.image_width,
            "image_height_original": meta_obj.camera.image_height,
            "white_balance": meta_obj.camera.white_balance
        },
        "attitude": {
            "gimbal_pitch": meta_obj.gimbal.pitch,
            "gimbal_roll": meta_obj.gimbal.roll,
            "aircraft_roll": meta_obj.attitude.roll,
            "aircraft_pitch": meta_obj.attitude.pitch
        },
        "gps": {
            "latitude": meta_obj.gps.latitude,
            "longitude": meta_obj.gps.longitude,
            "relative_altitude_m": meta_obj.gps.relative_altitude
        }
    }
    meta_path = meta_dir / f"{image_stem}_meta.json"
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info(f"元数据已保存: {meta_path}")

# ─────────── 主处理函数 ───────────
def process_single_image(raw_image_path: str,
                         output_dir: str,
                         mode: str = "training",
                         check_focal_consistency: bool = False,
                         baseline_focal_length: Optional[float] = None,
                         ref_lat: Optional[float] = None,
                         ref_lon: Optional[float] = None,
                         ref_alt: Optional[float] = None,
                         gps_threshold: float = 5.0,
                         alt_threshold_percent: float = 10.0
                         ) -> Optional[float]:
    # 1. 提取元数据
    meta = parse_drone_metadata_from_image(raw_image_path)

    # 2. 姿态与白平衡校验（传入 mode 以决定对 Unknown 白平衡的处理）
    validate_attitude(meta)
    validate_white_balance(meta, mode)

    # 3. 解码 RAW 获取真实图像尺寸，覆盖 EXIF 中可能错误的尺寸
    image = decode_raw(raw_image_path)
    true_w, true_h = image.size
    if meta.camera.image_width is None or meta.camera.image_height is None or \
       abs(meta.camera.image_width - true_w) > 100 or abs(meta.camera.image_height - true_h) > 100:
        logger.info(f"EXIF 图像尺寸 {meta.camera.image_width}x{meta.camera.image_height} "
                    f"与解码尺寸 {true_w}x{true_h} 差异较大，使用解码尺寸")
        meta.camera.image_width = true_w
        meta.camera.image_height = true_h

    # 4. 按模式额外校验
    if mode == "user":
        if check_focal_consistency:
            new_baseline = validate_focal_consistency(meta, baseline_focal_length)
        else:
            new_baseline = baseline_focal_length
        if ref_lat is None or ref_lon is None or ref_alt is None:
            logger.warning("用户端模式缺少基准 GPS/高度，跳过空间校验")
        else:
            validate_spatial(meta, ref_lat, ref_lon, ref_alt,
                             gps_threshold, alt_threshold_percent)
    else:
        new_baseline = baseline_focal_length

    # 5. GSD 计算（此时图像尺寸已是真实值）
    gsd = compute_gsd(meta)

    # 6. 缩放填充
    processed_img, region = resize_and_pad(image)

    # 7. 保存输出
    stem = Path(raw_image_path).stem
    save_outputs(processed_img, stem, output_dir, gsd, region, meta)
    return new_baseline

def process_batch(raw_dir: str,
                  output_dir: str,
                  mode: str = "training",
                  check_focal: bool = False,
                  ref_lat: Optional[float] = None,
                  ref_lon: Optional[float] = None,
                  ref_alt: Optional[float] = None):
    raw_files = list(Path(raw_dir).glob("*.RAW")) + list(Path(raw_dir).glob("*.DNG"))
    if not raw_files:
        logger.warning(f"{raw_dir} 中未找到 RAW/DNG 文件")
        return
    baseline = None
    for raw_path in raw_files:
        try:
            baseline = process_single_image(
                raw_image_path=str(raw_path),
                output_dir=str(output_dir),
                mode=mode,
                check_focal_consistency=check_focal,
                baseline_focal_length=baseline,
                ref_lat=ref_lat, ref_lon=ref_lon, ref_alt=ref_alt
            )
        except Exception as e:
            logger.error(f"处理 {raw_path.name} 出错: {e}")
            continue
    return baseline

def main():
    parser = argparse.ArgumentParser(
        description="无人机航拍图像正射校正预处理（直接从图像读取元数据）"
    )
    parser.add_argument("--raw", help="单张 RAW / DNG 图像路径")
    parser.add_argument("--raw-dir", help="批量图像目录（自动遍历其中的 RAW/DNG）")
    parser.add_argument("--out", required=True, help="输出根目录，如 data/02_preprocessed")
    parser.add_argument("--mode", choices=["user", "training"], default="training",
                        help="处理模式：user=全规范校验，training=放宽空间与焦距")
    parser.add_argument("--check-focal", action="store_true",
                        help="启用焦距一致性校验（用户端建议开启）")
    parser.add_argument("--ref-lat", type=float, help="池塘基准纬度")
    parser.add_argument("--ref-lon", type=float, help="池塘基准经度")
    parser.add_argument("--ref-alt", type=float, help="池塘基准相对高度（米）")
    parser.add_argument("--gps-threshold", type=float, default=5.0,
                        help="GPS 允许偏差（米），默认 5m")
    parser.add_argument("--alt-threshold", type=float, default=10.0,
                        help="高度允许偏差百分比，默认 10%%")

    args = parser.parse_args()

    if args.raw_dir:
        if not os.path.isdir(args.raw_dir):
            parser.error("--raw-dir 必须是有效目录")
        process_batch(
            raw_dir=args.raw_dir,
            output_dir=args.out,
            mode=args.mode,
            check_focal=args.check_focal,
            ref_lat=args.ref_lat,
            ref_lon=args.ref_lon,
            ref_alt=args.ref_alt
        )
    elif args.raw:
        process_single_image(
            raw_image_path=args.raw,
            output_dir=args.out,
            mode=args.mode,
            check_focal_consistency=args.check_focal,
            ref_lat=args.ref_lat,
            ref_lon=args.ref_lon,
            ref_alt=args.ref_alt,
            gps_threshold=args.gps_threshold,
            alt_threshold_percent=args.alt_threshold
        )
    else:
        parser.error("请指定 --raw 或 --raw-dir")

if __name__ == "__main__":
    main()