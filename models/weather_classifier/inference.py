# models/weather_classifier/inference.py
import os
import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
from torchvision import models

# ================== 配置（与训练完全一致）==================
TRAIN_CLASS_NAMES = ["cloudy", "hazy", "sunny"]
OUTPUT_CLASS_NAMES = ["sunny", "cloudy", "hazy"]
TRAIN_TO_OUTPUT_IDX = [OUTPUT_CLASS_NAMES.index(cls) for cls in TRAIN_CLASS_NAMES]
IMG_SIZE = 224
# ========================================================

def load_model(model_path, device='cpu'):
    """加载天气分类模型"""
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(TRAIN_CLASS_NAMES))
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model

def preprocess_image(image_path):
    """图像预处理（与训练一致）"""
    transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    image = Image.open(image_path).convert('RGB')
    return transform(image).unsqueeze(0)

def predict_weather(model, image_path, device='cpu'):
    """
    对外统一推理接口。

    参数:
        model: 已加载的 PyTorch 模型
        image_path: 图片路径
        device: 设备

    返回:
        (predicted_class, confidence, probs_dict)
        - predicted_class: str，项目约定类别 ('sunny'/'cloudy'/'hazy')
        - confidence: float，置信度
        - probs_dict: dict，包含三个类别的概率，键为项目约定类别名
    """
    img_tensor = preprocess_image(image_path).to(device)
    with torch.no_grad():
        outputs = model(img_tensor)
        probs_train = torch.nn.functional.softmax(outputs, dim=1).cpu().numpy()[0]

    # 重排概率顺序
    probs_output = [0.0] * len(OUTPUT_CLASS_NAMES)
    for train_idx, output_idx in enumerate(TRAIN_TO_OUTPUT_IDX):
        probs_output[output_idx] = probs_train[train_idx]

    pred_idx = probs_output.index(max(probs_output))
    pred_class = OUTPUT_CLASS_NAMES[pred_idx]
    confidence = probs_output[pred_idx]
    probs_dict = dict(zip(OUTPUT_CLASS_NAMES, probs_output))

    return pred_class, confidence, probs_dict

# 可选：默认模型加载快捷函数
def get_default_model(device='cpu'):
    """加载默认路径下的模型（best_weather_model.pth）"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "best_weather_model.pth")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"默认模型未找到: {model_path}")
    return load_model(model_path, device)