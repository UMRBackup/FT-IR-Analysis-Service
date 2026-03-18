import faiss
import torch
from torchvision import models, transforms
from torch import nn
import numpy as np
import os

def build_encoder(backbone='resnet18', embed_dim=128, pretrained=True, device='cpu', weights_path=None):
    if backbone == 'resnet18':
        m = models.resnet18(weights='DEFAULT' if pretrained and weights_path is None else None)
        feat_dim = m.fc.in_features
        m.fc = nn.Identity()  # type: ignore
    else:
        m = models.resnet34(weights='DEFAULT' if pretrained and weights_path is None else None)
        feat_dim = m.fc.in_features
        m.fc = nn.Identity()  # type: ignore
    head = nn.Sequential(nn.Linear(feat_dim, 256), nn.ReLU(), nn.Linear(256, embed_dim))
    model = nn.Sequential(m, head).to(device)

    # 如果提供了本地权重路径，则加载
    if weights_path is not None and os.path.exists(weights_path):
        state = torch.load(weights_path, map_location=device)
        try:
            model.load_state_dict(state, strict=False)
        except Exception:
            # 兜底：尝试只加载匹配的键
            filtered = {k: v for k, v in state.items() if k in model.state_dict()}
            model.load_state_dict(filtered, strict=False)

    return model

_tform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224,224)),
    transforms.Grayscale(num_output_channels=3),
    transforms.ToTensor(),
    transforms.Normalize([0.5,0.5,0.5],[0.5,0.5,0.5])
])

def compute_embeddings(model, imgs, device='cpu', batch_size=128):
    model.eval()
    embs = []
    with torch.no_grad():
        for i in range(0, len(imgs), batch_size):
            batch = imgs[i:i+batch_size]
            ts = torch.stack([_tform(img) for img in batch]).to(device)
            out = model(ts).cpu().numpy().astype('float32')
            # L2 normalize
            norms = (out**2).sum(axis=1, keepdims=True)**0.5 + 1e-9
            out = out / norms
            embs.append(out)
    return np.vstack(embs).astype('float32')

def save_model_weights(model, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    torch.save(model.state_dict(), path)

def load_model_weights(model, path, device='cpu'):
    state = torch.load(path, map_location=device)
    model.load_state_dict(state, strict=False)
    return model

def build_faiss_index(embeddings, nlist=100, m_pq=8, use_gpu=False):
    N, D = embeddings.shape
    if N == 0:
        raise ValueError("embeddings 为空，无法构建索引")

    # 确保连续且 float32
    embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)

    # 构建索引
    quantizer = faiss.IndexFlatL2(D)
    index = faiss.IndexIVFPQ(quantizer, D, nlist, m_pq, 8)
    index.nprobe = max(1, nlist // 10)

    # 准备训练数据（必须 >= nlist * 39，建议 >= nlist * 256）
    n_train = min(N, max(nlist * 40, 10000))
    if N < n_train:
        train_data = embeddings.copy()
    else:
        train_indices = np.random.choice(N, size=n_train, replace=False)
        train_data = embeddings[train_indices].copy()

    # 确保训练数据连续
    train_data = np.ascontiguousarray(train_data, dtype=np.float32)

    # 检查训练数据是否足够
    if train_data.shape[0] < nlist * 39:
        raise ValueError(f"训练数据不足：需要至少 {nlist * 39} 个样本，但只有 {train_data.shape[0]} 个")

    # 训练与添加（FAISS 自动从数组推断 n）
    if not index.is_trained:
        index.train(train_data) # type: ignore
    index.add(embeddings) # type: ignore

    return index

def query_faiss(index, q_emb, topk=10):
    if q_emb.ndim == 1:
        q_emb = q_emb.reshape(1, -1)
    q_emb = np.ascontiguousarray(q_emb, dtype=np.float32)
    dists, idxs = index.search(q_emb, topk)
    return idxs[0], dists[0]  # 返回单个查询结果
