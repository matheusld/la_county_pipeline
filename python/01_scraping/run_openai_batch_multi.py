import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except Exception:
    print('[error] Missing openai package. Install with: pip install openai', file=sys.stderr)
    raise


TERMINAL_STATUSES = {'completed', 'failed', 'expired', 'cancelled'}


def require_api_key() -> str:
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY is not set in the environment.')
    return key


def load_shard_files(input_dir: Path, pattern: str = '*.jsonl'):
    files = sorted([p for p in input_dir.glob(pattern) if p.is_file()])
    if not files:
        raise FileNotFoundError(f'No shard files found in {input_dir} matching {pattern}')
    return files


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        for line in lines:
            f.write(line)
            if not line.endswith('\n'):
                f.write('\n')


def wait_for_batch(client: OpenAI, batch_id: str, poll_seconds: int, status_path: Path | None = None):
    while True:
        batch = client.batches.retrieve(batch_id)
        status = getattr(batch, 'status', None)
        req = getattr(batch, 'request_counts', None)
        completed = getattr(req, 'completed', 0) if req else 0
        failed = getattr(req, 'failed', 0) if req else 0
        total = getattr(req, 'total', 0) if req else 0
        print(f"[status] batch_id={batch_id} status={status} | completed={completed} failed={failed} total={total}")
        if status_path:
            save_json(status_path, batch.model_dump() if hasattr(batch, 'model_dump') else json.loads(batch.model_dump_json()))
        if status in TERMINAL_STATUSES:
            return batch
        time.sleep(poll_seconds)


def download_file_text(client: OpenAI, file_id: str) -> str:
    content = client.files.content(file_id)
    # SDK may return text or bytes depending on version.
    text = getattr(content, 'text', None)
    if callable(text):
        return text()
    if isinstance(content, (bytes, bytearray)):
        return content.decode('utf-8')
    if hasattr(content, 'content'):
        c = content.content
        if isinstance(c, (bytes, bytearray)):
            return c.decode('utf-8')
    return str(content)


def main():
    ap = argparse.ArgumentParser(description='Run multiple OpenAI batch shard files sequentially.')
    ap.add_argument('--input-dir', required=True, help='Directory with shard JSONL files')
    ap.add_argument('--pattern', default='*.jsonl')
    ap.add_argument('--completion-window', default='24h')
    ap.add_argument('--endpoint', default='/v1/responses')
    ap.add_argument('--poll-seconds', type=int, default=30)
    ap.add_argument('--metadata-name', default='batch_multi_run')
    ap.add_argument('--status-dir', default='./batch_status')
    ap.add_argument('--output-dir', default='./batch_outputs')
    ap.add_argument('--start-at', type=int, default=1, help='1-based shard index to start from')
    ap.add_argument('--stop-after', type=int, default=0, help='Stop after N shards; 0 = all')
    args = ap.parse_args()

    require_api_key()
    client = OpenAI()

    input_dir = Path(args.input_dir)
    status_dir = Path(args.status_dir)
    output_dir = Path(args.output_dir)
    status_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    shard_files = load_shard_files(input_dir, args.pattern)
    selected = shard_files[args.start_at - 1:]
    if args.stop_after > 0:
        selected = selected[:args.stop_after]

    run_manifest = []

    for idx, shard in enumerate(selected, start=args.start_at):
        print(f"\n=== SHARD {idx} / {len(shard_files)} :: {shard.name} ===")

        print(f"[upload] Uploading {shard}")
        up = client.files.create(file=open(shard, 'rb'), purpose='batch')
        file_id = up.id
        print(f"[upload] Uploaded file_id={file_id}")

        print('[batch] Creating batch job')
        batch = client.batches.create(
            input_file_id=file_id,
            endpoint=args.endpoint,
            completion_window=args.completion_window,
            metadata={'name': args.metadata_name, 'input_filename': shard.name, 'shard_index': str(idx)},
        )
        batch_id = batch.id
        print(f"[batch] Created batch_id={batch_id} status={batch.status}")

        status_path = status_dir / f"{shard.stem}.status.json"
        final_batch = wait_for_batch(client, batch_id, args.poll_seconds, status_path)
        status = getattr(final_batch, 'status', None)

        record = {
            'shard_index': idx,
            'shard_file': str(shard),
            'upload_file_id': file_id,
            'batch_id': batch_id,
            'final_status': status,
        }

        if status == 'completed':
            output_file_id = getattr(final_batch, 'output_file_id', None)
            error_file_id = getattr(final_batch, 'error_file_id', None)
            if output_file_id:
                print(f"[download] Downloading output_file_id={output_file_id}")
                text = download_file_text(client, output_file_id)
                out_path = output_dir / f"{shard.stem}.output.jsonl"
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                record['output_file_id'] = output_file_id
                record['output_path'] = str(out_path)
                print(f"[download] Wrote {out_path}")
            if error_file_id:
                print(f"[download] Downloading error_file_id={error_file_id}")
                text = download_file_text(client, error_file_id)
                err_path = output_dir / f"{shard.stem}.error.jsonl"
                with open(err_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                record['error_file_id'] = error_file_id
                record['error_path'] = str(err_path)
        else:
            print(f"[warn] Shard {shard.name} ended with status={status}")
            errors = getattr(final_batch, 'errors', None)
            if errors:
                record['errors'] = errors.model_dump() if hasattr(errors, 'model_dump') else str(errors)
            # Stop on failure so you can inspect before continuing.
            run_manifest.append(record)
            save_json(status_dir / 'multi_run_manifest.json', run_manifest)
            print('[stop] Stopping after failed shard.')
            sys.exit(1)

        run_manifest.append(record)
        save_json(status_dir / 'multi_run_manifest.json', run_manifest)

    print('\n[done] All selected shards processed successfully.')
    print(f"[done] Run manifest: {status_dir / 'multi_run_manifest.json'}")


if __name__ == '__main__':
    main()
