import os
import glob
import cv2
import numpy as np
import random
from skimage.morphology import skeletonize
from model import build_encoder, compute_embeddings, build_faiss_index, query_faiss
import torch
import time
import os

def seed_everything(seed=42):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def load_image_gray(path):
    try:
        with open(path, "rb") as _f:
            data = _f.read()
        if not data:
            return None
        b = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(b, cv2.IMREAD_GRAYSCALE)
        if img is None:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        return img
    except Exception as e:
        with open(os.path.join(os.path.dirname(__file__), "run_debug.log"), "a", encoding="utf-8") as _f:
            _f.write(f"LOAD_FAIL {time.ctime()} path={path} err={e}\n")
        return None

def binarize_mask(img, th=127):
    if img is None:
        return None
    _, m = cv2.threshold(img, th, 255, cv2.THRESH_BINARY)
    return m

def gallery_load_paths(folder):
    exts = ('*.png','*.jpg','*.jpeg','*.bmp','*.tif','*.tiff')
    files=[]
    for e in exts:
        files += glob.glob(os.path.join(folder, e))
    files = sorted(files)
    return files

def make_gallery_embeddings(model, gallery_paths, device='cpu', batch_size=256):
    embs_list = []
    valid_paths = []
    for i in range(0, len(gallery_paths), batch_size):
        batch_paths = gallery_paths[i:i+batch_size]
        imgs_batch = []
        paths_batch = []
        for p in batch_paths:
            im = load_image_gray(p)
            im = binarize_mask(im) if im is not None else None
            if im is None:
                with open(os.path.join(os.path.dirname(__file__), "run_debug.log"), "a", encoding="utf-8") as _f:
                    _f.write(f"SKIP_UNREADABLE {time.ctime()} path={p}\n")
                continue
            imgs_batch.append(im)
            paths_batch.append(p)
        if not imgs_batch:
            continue
        embs_batch = compute_embeddings(model, imgs_batch, device=device, batch_size=batch_size)
        embs_list.append(np.asarray(embs_batch))
        valid_paths.extend(paths_batch)
    if len(embs_list) == 0:
        raise RuntimeError("gallery 为空或所有图片无法读取")
    embs = np.vstack(embs_list)
    return embs, valid_paths

def skeleton_sequence(mask, out_len=200):
    if mask is None or mask.sum()==0:
        return None
    binm = (mask>127).astype(np.uint8)
    sk = skeletonize(binm>0).astype(np.uint8)
    ys, xs = np.where(sk>0)
    if len(xs) < 5:
        # fallback: per-column median
        h,w = binm.shape
        xs_list=[]; ys_list=[]
        for c in range(w):
            rows = np.where(binm[:,c]>0)[0]
            if rows.size:
                xs_list.append(c); ys_list.append(np.median(rows))
        if not xs_list:
            return None
        xs = np.array(xs_list); ys = np.array(ys_list)
    order = np.argsort(xs)
    xs_s = xs[order].astype(float); ys_s = ys[order].astype(float)
    uniq_x, idx = np.unique(xs_s, return_index=True)
    xs_s = xs_s[idx]; ys_s = ys_s[idx]
    if len(xs_s) < 3:
        return None
    grid = np.linspace(xs_s.min(), xs_s.max(), out_len)
    ys_interp = np.interp(grid, xs_s, ys_s)
    h = mask.shape[0]
    return (1.0 - ys_interp / max(1.0, h-1)).astype(np.float32)

def dtw_distance(s1, s2):
    if s1 is None or s2 is None:
        return float('inf')
    n, m = len(s1), len(s2)
    D = np.full((n+1, m+1), np.inf, dtype=np.float32)
    D[0,0] = 0.0
    for i in range(1,n+1):
        for j in range(1,m+1):
            cost = abs(float(s1[i-1]) - float(s2[j-1]))
            D[i,j] = cost + min(D[i-1,j], D[i,j-1], D[i-1,j-1])
    return float(D[n,m] / (n+m))

def search(query_path, gallery_dir, topk=10, device='cpu'):
    seed_everything(42)
    model = build_encoder(device=device, pretrained=True)
    
    model.eval()

    # load gallery paths
    gallery_paths = gallery_load_paths(gallery_dir)
    if len(gallery_paths) == 0:
        raise RuntimeError("gallery 为空")
    embs, valid_paths = make_gallery_embeddings(model, gallery_paths, device=device, batch_size=256)
    # build faiss index
    index = build_faiss_index(embs, nlist=max(8, int(np.sqrt(len(embs)))), m_pq=8)
    # query embed
    q_img = load_image_gray(query_path)
    if q_img is None:
        with open(os.path.join(os.path.dirname(__file__), "run_debug.log"), "a", encoding="utf-8") as _f:
            _f.write(f"QUERY_LOAD_FAIL {time.ctime()} path={query_path}\n")
        raise RuntimeError(f"无法读取查询图像: {query_path}")
    q_mask = binarize_mask(q_img)
    if q_mask is None:
        raise RuntimeError(f"查询图像二值化失败: {query_path}")
    q_embs = compute_embeddings(model, [q_mask], device=device)
    q_embs = np.asarray(q_embs)
    if q_embs.size == 0:
        raise RuntimeError("查询特征计算失败")
    q_emb = q_embs[0]
    idxs, dists = query_faiss(index, q_emb, topk=topk)
    q_seq = skeleton_sequence(q_mask)
    refined = []
    for i, dist in zip(idxs, dists):
        try:
            cand_path = valid_paths[int(i)]
        except Exception:
            continue
        cand_img = load_image_gray(cand_path)
        cand_mask = binarize_mask(cand_img)
        cand_seq = skeleton_sequence(cand_mask)
        d = dtw_distance(q_seq, cand_seq)
        refined.append((int(i), float(dist), d, cand_path))
    refined = sorted(refined, key=lambda x: (x[2], x[1]))
    return refined

def main():
    import argparse
    import traceback
    import sys
    p = argparse.ArgumentParser()
    p.add_argument("gallery", help="图库目录路径")
    p.add_argument("query", help="查询图像路径")
    p.add_argument("--topk", type=int, default=5, help="返回的最相似结果数量")
    args = p.parse_args()
    try:
        res = search(args.query, args.gallery, topk=args.topk, device='cpu')
        for rank, (idx, faiss_d, dtw_d, path) in enumerate(res[:args.topk], 1):
            print(f"{rank}. {os.path.basename(path)}  faiss:{faiss_d:.4f}  dtw:{dtw_d:.4f}")
    except Exception:
        print("Script failed with exception:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()