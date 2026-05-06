# models/weather_classifier/train.py
# 基于自有数据集（data/02_preprocessed/images/）的天气分类训练脚本
# 图片命名规范：YYYYMMDD_天气_序号.png（如 20240315_sunny_001.png）
# 天气字段取值：sunny / cloudy / hazy

import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms, models
from PIL import Image
from tqdm import tqdm

# ================== 配置区 ==================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "02_preprocessed", "images")

# 天气类别（必须与 inference.py 中 TRAIN_CLASS_NAMES 顺序完全一致）
WEATHER_CLASSES = ["cloudy", "hazy", "sunny"]
NUM_CLASSES = len(WEATHER_CLASSES)

BATCH_SIZE = 32
EPOCHS = 20
LEARNING_RATE = 1e-4
NUM_WORKERS = 4
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# ===========================================


class WeatherDataset(Dataset):
    """按项目命名规范 YYYYMMDD_天气_序号.png 解析天气标签的 Dataset"""

    def __init__(self, image_dir, class_names, transform=None):
        self.image_dir = image_dir
        self.class_names = class_names
        self.transform = transform

        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
        all_files = [
            f for f in os.listdir(image_dir)
            if f.lower().endswith(valid_exts)
        ]

        self.samples = []
        skipped = []
        for fname in sorted(all_files):
            label = self._extract_label(fname)
            if label is not None:
                self.samples.append((fname, label))
            else:
                skipped.append(fname)

        if skipped:
            print(f"警告：以下文件未提取到天气标签，已跳过 ({len(skipped)} 个):")
            for s in skipped:
                print(f"  - {s}")

        if not self.samples:
            raise RuntimeError(
                f"在 {image_dir} 中没有找到符合命名规范的图片。"
                f"请确保文件名格式为 YYYYMMDD_天气_序号.png，天气取值为: {class_names}"
            )

        print(f"从 {image_dir} 加载了 {len(self.samples)} 张带标签图片")

    def _extract_label(self, fname):
        """按 YYYYMMDD_天气_序号 解析天气字段，返回类别索引"""
        stem = os.path.splitext(fname)[0]
        parts = stem.split('_')
        # 文件名格式：YYYYMMDD_天气_序号 → 至少 3 段，天气在第 2 段（索引 1）
        if len(parts) < 3:
            return None
        weather_raw = parts[1].lower()
        if weather_raw not in self.class_names:
            return None
        return self.class_names.index(weather_raw)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        fname, label = self.samples[idx]
        path = os.path.join(self.image_dir, fname)
        image = Image.open(path).convert('RGB')
        if self.transform:
            image = self.transform(image)
        return image, label


def prepare_data():
    """准备训练和验证 DataLoader"""
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])

    if not os.path.exists(DATA_DIR):
        print(f"错误：数据目录 {DATA_DIR} 不存在！")
        return None, None

    full_dataset = WeatherDataset(DATA_DIR, WEATHER_CLASSES, transform=train_transform)
    val_dataset = WeatherDataset(DATA_DIR, WEATHER_CLASSES, transform=val_transform)

    # 划分训练/验证集（80%/20%）
    n_total = len(full_dataset)
    train_size = int(0.8 * n_total)
    val_size = n_total - train_size
    print(f"训练集: {train_size} 张, 验证集: {val_size} 张")

    train_dataset, _ = random_split(full_dataset, [train_size, val_size])
    _, val_dataset = random_split(val_dataset, [train_size, val_size])

    train_loader = DataLoader(
        train_dataset, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=True,
        persistent_workers=True if NUM_WORKERS > 0 else False
    )
    val_loader = DataLoader(
        val_dataset, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True,
        persistent_workers=True if NUM_WORKERS > 0 else False
    )

    # 打印类别分布
    label_counts = {}
    for _, lbl in full_dataset.samples:
        cls = WEATHER_CLASSES[lbl]
        label_counts[cls] = label_counts.get(cls, 0) + 1
    print(f"各类别样本数: {label_counts}")

    return train_loader, val_loader


def build_model():
    """构建 ResNet18 三分类模型"""
    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    return model.to(DEVICE)


def train():
    train_loader, val_loader = prepare_data()
    if train_loader is None:
        return

    # 验证标签映射
    images, labels = next(iter(train_loader))
    print("训练 batch 标签示例:", labels[:10].tolist())
    print("对应类别:", [WEATHER_CLASSES[l] for l in labels[:10].tolist()])

    model = build_model()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.1)

    best_acc = 0.0
    save_path = os.path.join(os.path.dirname(__file__), "best_weather_model.pth")

    for epoch in range(EPOCHS):
        # 训练阶段
        model.train()
        total_loss = 0.0
        correct = total = 0
        loop = tqdm(train_loader, desc=f"Epoch {epoch+1}/{EPOCHS} [Train]")
        for imgs, lbls in loop:
            imgs, lbls = imgs.to(DEVICE), lbls.to(DEVICE)
            optimizer.zero_grad()
            outs = model(imgs)
            loss = criterion(outs, lbls)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            _, preds = torch.max(outs, 1)
            total += lbls.size(0)
            correct += (preds == lbls).sum().item()
            loop.set_postfix(loss=total_loss/(total//BATCH_SIZE + 1), acc=100*correct/total)
        train_acc = 100 * correct / total

        # 验证阶段
        model.eval()
        val_correct = val_total = 0
        with torch.no_grad():
            for imgs, lbls in tqdm(val_loader, desc=f"Epoch {epoch+1}/{EPOCHS} [Val]"):
                imgs, lbls = imgs.to(DEVICE), lbls.to(DEVICE)
                outs = model(imgs)
                _, preds = torch.max(outs, 1)
                val_total += lbls.size(0)
                val_correct += (preds == lbls).sum().item()
        val_acc = 100 * val_correct / val_total
        print(f"Epoch {epoch+1}: Train Acc={train_acc:.2f}%, Val Acc={val_acc:.2f}%")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), save_path)
            print(f"已保存最佳模型至 {save_path}，准确率: {val_acc:.2f}%")

        scheduler.step()

    print(f"训练完成！最佳验证准确率: {best_acc:.2f}%")


if __name__ == "__main__":
    train()
