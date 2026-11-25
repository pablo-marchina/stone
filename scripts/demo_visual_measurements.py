"""Read-only measurements of a caller-supplied original local draft, not corpus admission."""
import argparse
import hashlib
import json
from pathlib import Path


def measure_draft(path):
    import cv2
    import numpy as np
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 100_000_000:
        raise ValueError('VISUAL_LOCAL_DRAFT_INVALID')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError('VISUAL_DRAFT_UNREADABLE')
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not (0 < fps <= 240 and 0 < count <= 14400 and 0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError('VISUAL_DRAFT_LIMIT')
        indices = np.unique(np.linspace(0, count-1, min(24, count), dtype=int))
        samples = []
        palette = np.zeros(4096, dtype=np.int64)
        edges, changes = [], []
        previous = None
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.resize(frame, (160, 160), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            samples.append([float(np.mean(gray < 16)), float(np.mean(hsv[:,:,1])/255), float(np.std(gray)/255)])
            rgb = (frame[:,:,::-1].astype(np.int32) >> 4)
            bins = rgb[:,:,0]*256 + rgb[:,:,1]*16 + rgb[:,:,2]
            palette += np.bincount(bins.ravel(), minlength=4096)
            edges.append(float(np.mean(cv2.Canny(gray, 60, 120) > 0)))
            if previous is not None:
                changes.append(float(np.mean(cv2.absdiff(gray, previous))/255))
            previous = gray
        if not samples:
            raise ValueError('VISUAL_DRAFT_NO_FRAMES')
        values = np.mean(samples, axis=0)
        return dict(schema_version='tapi-demo-visual-measurements.v2', sha256=digest,
                    scope='operator_supplied_original_local_draft_only', width=width, height=height,
                    fps=fps, duration_seconds=count/fps, sampled_frames=len(samples),
                    requested_samples=len(indices), near_black_pixel_share=round(float(values[0]),6),
                    mean_saturation=round(float(values[1]),6), luminance_std=round(float(values[2]),6),
                    palette_quantized_rgb=[{'hex': '#%02X%02X%02X' % (int(i//256)*16+8,int(i//16%16)*16+8,int(i%16)*16+8),
                                            'share': round(float(palette[i]/palette.sum()),6)}
                                           for i in np.argsort(-palette, kind='stable')[:5] if palette[i]],
                    mean_edge_pixel_share=round(float(np.mean(edges)),6),
                    mean_sampled_luma_change=round(float(np.mean(changes)),6) if changes else None,
                    sample_pairs=len(changes), temporal_proxy_not_cut_rate=True,
                    aesthetic_effectiveness_validated=False, corpus_admission=False, publication_allowed=False)
    finally:
        cap.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--confirm-original-local-draft', action='store_true', required=True)
    args = parser.parse_args()
    print(json.dumps(measure_draft(args.path), ensure_ascii=False, indent=2))
