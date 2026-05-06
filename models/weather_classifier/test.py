# models/weather_classifier/test.py
import os
import torch
import torch.nn as nn
import torchvision.transforms as transforms
from PIL import Image
from torchvision import models

# ================== 配置（与训练完全一致）==================
TRAIN_CLASS_NAMES = ["cloudy", "hazy", "sunny"]           # 训练时文件夹字母序
OUTPUT_CLASS_NAMES = ["sunny", "cloudy", "hazy"]         # 项目展示顺序
TRAIN_TO_OUTPUT_IDX = [OUTPUT_CLASS_NAMES.index(cls) for cls in TRAIN_CLASS_NAMES]

MODEL_PATH = "origin/best_weather_model.pth"  # 默认模型路径
TEST_IMG_DIR = "testimgs"                                 # 测试图片文件夹（相对于当前脚本）
IMG_SIZE = 224
# ========================================================

def load_model(model_path, device='cpu'):
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(TRAIN_CLASS_NAMES))
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model

def preprocess_image(image_path):
    transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    image = Image.open(image_path).convert('RGB')
    return transform(image).unsqueeze(0)

def predict_single(model, image_path, device):
    img_tensor = preprocess_image(image_path).to(device)
    with torch.no_grad():
        outputs = model(img_tensor)
        probs_train = torch.nn.functional.softmax(outputs, dim=1).cpu().numpy()[0]

    # 重排概率顺序为项目展示顺序
    probs_output = [0.0] * len(OUTPUT_CLASS_NAMES)
    for train_idx, output_idx in enumerate(TRAIN_TO_OUTPUT_IDX):
        probs_output[output_idx] = probs_train[train_idx]

    pred_idx = probs_output.index(max(probs_output))
    return OUTPUT_CLASS_NAMES[pred_idx], probs_output[pred_idx], probs_output

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")

    # 模型路径处理
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, MODEL_PATH)
    if not os.path.exists(model_path):
        print(f"错误：模型文件 '{model_path}' 不存在，请先训练模型。")
        return
    model = load_model(model_path, device)
    print("模型加载成功。")

    # 测试图片文件夹
    test_dir = os.path.join(script_dir, TEST_IMG_DIR)
    if not os.path.exists(test_dir):
        print(f"错误：测试文件夹 '{test_dir}' 不存在。")
        return

    exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    img_files = [f for f in os.listdir(test_dir) if f.lower().endswith(exts)]
    if not img_files:
        print(f"警告：'{test_dir}' 中没有图片文件。")
        return

    print(f"找到 {len(img_files)} 张图片，开始预测...\n")
    print("=" * 70)
    for img_file in sorted(img_files):
        img_path = os.path.join(test_dir, img_file)
        try:
            pred, conf, probs = predict_single(model, img_path, device)
            print(f"{img_file:30s} -> {pred:8s} (置信度: {conf:.4f})")
        except Exception as e:
            print(f"{img_file:30s} -> 处理出错: {e}")
    print("=" * 70)

if __name__ == "__main__":
    main()