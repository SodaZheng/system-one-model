"""CPU FP32 inference with bounded prefill and persistent Qwen3.5 hybrid caches."""
import os
import time
from pathlib import Path
from .protocol import MODEL, encode, render

class Runtime:
    def __init__(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from thisthat.prompt import option_label_ids
        self.threads = int(os.getenv('THREADS', '8'))
        self.chunk_size = int(os.getenv('PREFILL_CHUNK_SIZE', '512'))
        self.max_tokens = int(os.getenv('MAX_CONTEXT_TOKENS', '32768'))
        if not 1 <= self.threads <= 256: raise ValueError('THREADS must be 1..256')
        if not 64 <= self.chunk_size <= 2048: raise ValueError('PREFILL_CHUNK_SIZE must be 64..2048')
        if not 1 <= self.max_tokens <= 32768: raise ValueError('MAX_CONTEXT_TOKENS must be 1..32768')
        torch.set_num_threads(self.threads)
        torch.set_num_interop_threads(1)
        path = Path(os.getenv('MODEL_PATH', '/app/models/this-that-1.2'))
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
        self.model, info = AutoModelForCausalLM.from_pretrained(
            path, local_files_only=True, trust_remote_code=False, use_safetensors=True,
            dtype=torch.float32, attn_implementation='sdpa', output_loading_info=True)
        if any(info.get(k) for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
            raise RuntimeError('Checkpoint architecture/tensors mismatch')
        if self.model.config.model_type != 'qwen3_5_text': raise RuntimeError('Unexpected architecture')
        self.model.eval()
        self.labels = torch.tensor(option_label_ids(self.tokenizer), dtype=torch.long)
        self.weights = self.model.get_output_embeddings().weight[self.labels].detach()
        self.completed_requests = 0

    def logits(self, built, chunk_size=None):
        import torch
        cache, rows = None, []
        chunk_size = chunk_size or self.chunk_size
        with torch.inference_mode():
            for start in range(0, len(built['ids']), chunk_size):
                end = min(start + chunk_size, len(built['ids']))
                ids = torch.tensor([built['ids'][start:end]], dtype=torch.long)
                output = self.model.model(input_ids=ids, past_key_values=cache, use_cache=True)
                cache = output.past_key_values
                for slot in built['slots']:
                    if start <= slot < end:
                        h = output.last_hidden_state[0, slot - start]
                        rows.append(torch.nn.functional.linear(h, self.weights).float())
                del output
            del cache
        return torch.stack(rows)

    def predict(self, body):
        import torch
        start = time.monotonic()
        built, keys = encode(self.tokenizer, body, self.max_tokens)
        logits = self.logits(built)
        answers = {}
        for index, (name, question) in enumerate(body.questions.items()):
            p = torch.softmax(logits[index, :len(keys[index])], dim=-1).tolist()
            answers[name] = render(question, keys[index], p)
        self.completed_requests += 1
        print(f'inference tokens={len(built["ids"])} questions={len(answers)} elapsed_s={time.monotonic()-start:.3f}', flush=True)
        return {'model': MODEL, 'answers': answers,
                'usage': {'input_tokens': len(built['ids']), 'output_tokens': len(answers)}}
