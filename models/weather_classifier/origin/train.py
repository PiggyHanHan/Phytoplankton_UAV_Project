# models/weather_classifier/train.py
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms, models
from tqdm import tqdm

# ================== 配置区 ==================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_ROOT = os.path.join(PROJECT_ROOT, "data", "weather_public")

# 训练时类别顺序与文件夹字母序完全一致（cloudy, hazy, sunny）
TRAIN_CLASS_NAMES = ["cloudy", "hazy", "sunny"]
NUM_CLASSES = len(TRAIN_CLASS_NAMES)

BATCH_SIZE = 32
EPOCHS = 20
LEARNING_RATE = 1e-4
NUM_WORKERS = 4
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# ===========================================

def prepare_data():
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

    if not os.path.exists(DATA_ROOT):
        print(f"错误：数据目录 {DATA_ROOT} 不存在！")
        return None, None

    # 直接加载，不人为调整标签顺序
    full_train = datasets.ImageFolder(root=DATA_ROOT, transform=train_transform)
    full_val = datasets.ImageFolder(root=DATA_ROOT, transform=val_transform)

    # 检查文件夹类别是否与预期一致
    print(f"检测到文件夹类别（按字母序）: {full_train.classes}")
    if full_train.classes != TRAIN_CLASS_NAMES:
        print(f"警告：实际文件夹类别 {full_train.classes} 与代码中 TRAIN_CLASS_NAMES 不一致，请修改 TRAIN_CLASS_NAMES。")
        return None, None

    print(f"共 {len(full_train)} 张图片，类别: {TRAIN_CLASS_NAMES}")

    # 划分训练/验证集（80%/20%）
    train_size = int(0.8 * len(full_train))
    val_size = len(full_train) - train_size
    train_dataset, _ = random_split(full_train, [train_size, val_size])
    _, val_dataset = random_split(full_val, [train_size, val_size])

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

    print(f"训练集样本数: {len(train_dataset)}")
    print(f"验证集样本数: {len(val_dataset)}")
    return train_loader, val_loader

def build_model():
    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, NUM_CLASSES)
    return model.to(DEVICE)

def train():
    train_loader, val_loader = prepare_data()
    if train_loader is None:
        return

    # 验证标签映射（可选打印）
    images, labels = next(iter(train_loader))
    print("训练 batch 标签示例:", labels[:10].tolist())
    print("对应训练时类别:", [TRAIN_CLASS_NAMES[l] for l in labels[:10].tolist()])

    model = build_model()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.1)

    best_acc = 0.0
    save_path = os.path.join(os.path.dirname(__file__), "best_weather_model.pth")

    for epoch in range(EPOCHS):
        # 训练
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

        # 验证
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