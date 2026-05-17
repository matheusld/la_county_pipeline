import argparse
import json
from pathlib import Path


def estimate_tokens(obj, chars_per_token: float = 4.0) -> int:
    # Estimate from request body text payload length plus a small fixed overhead.
    body = obj.get('body', {})
    try:
        s = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        s = str(body)
    return max(1, int(len(s) / chars_per_token) + 50)


def main():
    ap = argparse.ArgumentParser(description='Split OpenAI Batch JSONL into token-safe shards.')
    ap.add_argument('--input-jsonl', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--max-tokens-per-shard', type=int, default=1600000,
                    help='Target max estimated input tokens per shard. Stay below org enqueued limit.')
    ap.add_argument('--chars-per-token', type=float, default=4.0)
    ap.add_argument('--max-requests-per-shard', type=int, default=50000)
    args = ap.parse_args()

    in_path = Path(args.input_jsonl)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    shard_idx = 1
    shard_lines = []
    shard_tokens = 0
    shard_reqs = 0
    total_tokens = 0
    total_reqs = 0
    manifest_rows = []

    def flush():
        nonlocal shard_idx, shard_lines, shard_tokens, shard_reqs
        if not shard_lines:
            return
        fname = out_dir / f"{in_path.stem}.part{shard_idx:03d}.jsonl"
        with open(fname, 'w', encoding='utf-8') as f:
            for line in shard_lines:
                f.write(line)
                if not line.endswith('\n'):
                    f.write('\n')
        manifest_rows.append({
            'shard': shard_idx,
            'filename': str(fname),
            'requests': shard_reqs,
            'estimated_tokens': shard_tokens,
        })
        print(f"[shard] Wrote {fname.name}: requests={shard_reqs:,} est_tokens={shard_tokens:,}")
        shard_idx += 1
        shard_lines = []
        shard_tokens = 0
        shard_reqs = 0

    with open(in_path, 'r', encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f'Invalid JSON on line {lineno}: {e}')
            tok = estimate_tokens(obj, args.chars_per_token)
            total_tokens += tok
            total_reqs += 1

            if shard_lines and (
                shard_tokens + tok > args.max_tokens_per_shard
                or shard_reqs + 1 > args.max_requests_per_shard
            ):
                flush()

            shard_lines.append(line + '\n')
            shard_tokens += tok
            shard_reqs += 1

    flush()

    manifest_path = out_dir / f"{in_path.stem}.shards_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({
            'input_jsonl': str(in_path),
            'total_requests': total_reqs,
            'total_estimated_tokens': total_tokens,
            'max_tokens_per_shard': args.max_tokens_per_shard,
            'chars_per_token': args.chars_per_token,
            'shards': manifest_rows,
        }, f, ensure_ascii=False, indent=2)

    print(f"[done] Total requests={total_reqs:,} total_est_tokens={total_tokens:,}")
    print(f"[done] Shards manifest: {manifest_path}")


if __name__ == '__main__':
    main()
