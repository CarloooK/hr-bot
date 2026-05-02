"""
自定义 ONNX embedding 函数（用于 ChromaDB）
使用 onnxruntime 直接加载 all-MiniLM-L6-v2，无需 PyTorch，内存极低。
"""
import os
import numpy as np
import onnxruntime
from tokenizers import Tokenizer
from chromadb.api.types import EmbeddingFunction, Embeddings

# ONNX 模型文件路径
ONNX_MODEL_DIR = os.path.expanduser(
    "~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx"
)

MAX_SEQ_LEN = 256
EMBEDDING_DIM = 384


class MiniLMEmbeddingFunction(EmbeddingFunction):
    """基于 onnxruntime 的 MiniLM embedding 函数"""

    def __init__(self):
        tok_path = os.path.join(ONNX_MODEL_DIR, "tokenizer.json")
        model_path = os.path.join(ONNX_MODEL_DIR, "model.onnx")

        if not os.path.exists(tok_path) or not os.path.exists(model_path):
            raise RuntimeError(
                f"ONNX 模型文件缺失。请确认以下文件存在：\n"
                f"  - {model_path}\n"
                f"  - {tok_path}\n"
                f"  - {os.path.join(ONNX_MODEL_DIR, 'config.json')}"
            )

        self.tokenizer = Tokenizer.from_file(tok_path)
        self.session = onnxruntime.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name

    def __call__(self, texts: list[str]) -> Embeddings:
        outputs = []
        for text in texts:
            encoded = self.tokenizer.encode(text, add_special_tokens=True)
            ids = encoded.ids[:MAX_SEQ_LEN]
            mask = [1] * len(ids)
            tt_ids = [0] * len(ids)

            pad_len = MAX_SEQ_LEN - len(ids)
            input_ids = np.array(ids + [0] * pad_len, dtype=np.int64).reshape(1, MAX_SEQ_LEN)
            attention_mask = np.array(mask + [0] * pad_len, dtype=np.int64).reshape(1, MAX_SEQ_LEN)
            token_type_ids = np.array(tt_ids + [0] * pad_len, dtype=np.int64).reshape(1, MAX_SEQ_LEN)

            result = self.session.run(None, {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            })

            # Mean pooling
            token_emb = result[0][0]  # (256, 384)
            mask_arr = attention_mask.astype(np.float32).T  # (256, 1)
            sum_emb = np.sum(token_emb * mask_arr, axis=0)
            sum_mask = np.clip(np.sum(mask_arr), a_min=1e-9, a_max=None)
            embedding = sum_emb / sum_mask

            # L2 normalize
            embedding = embedding / np.linalg.norm(embedding)
            outputs.append(embedding.tolist())

        return outputs
