"""Turn a clean digital PDF into a scanned, faxed or phone photo copy with realistic damage."""
from __future__ import annotations

import random
from pathlib import Path

import cv2
import numpy as np
import pymupdf

PROFILES = {
    # dpi, max skew in degrees, blur kernels, speckle rate, binarize, chance of a page turn, jpeg quality
    "scan": dict(dpi=200, skew=2.0, blur=[1, 3], speckle=0.0005, binarize=False, turn=0.0, jpeg=70, photo=False),
    "fax": dict(dpi=200, skew=2.5, blur=[1, 3], speckle=0.0015, binarize=True, turn=0.06, jpeg=60, photo=False),
    "phone": dict(dpi=200, skew=3.0, blur=[1, 3], speckle=0.0, binarize=False, turn=0.0, jpeg=55, photo=True),
}


def _photo(img: np.ndarray, rng: random.Random) -> np.ndarray:
    """A phone picture of a page on a table: slight perspective, uneven light."""
    h, w = img.shape
    d = int(min(h, w) * 0.03)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[rng.randint(0, d), rng.randint(0, d)], [w - rng.randint(0, d), rng.randint(0, d)],
                      [w - rng.randint(0, d), h - rng.randint(0, d)], [rng.randint(0, d), h - rng.randint(0, d)]])
    img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=200)
    gx = np.linspace(rng.uniform(0.75, 0.9), 1.0, w)[None, :]
    gy = np.linspace(1.0, rng.uniform(0.8, 0.95), h)[:, None]
    return np.clip(img.astype(np.float32) * gx * gy, 0, 255).astype(np.uint8)


def _damage(img: np.ndarray, prof: dict, rng: random.Random, page_no: int, total: int) -> np.ndarray:
    h, w = img.shape[:2]
    if prof["photo"]:
        img = _photo(img, rng)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-prof["skew"], prof["skew"]), 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=255)
    k = rng.choice(prof["blur"])
    if k > 1:
        img = cv2.GaussianBlur(img, (k, k), 0)
    noise = np.random.default_rng(rng.randint(0, 2**31)).random(img.shape) < prof["speckle"]
    img = img.copy()
    img[noise] = 0
    if prof["binarize"]:
        img = np.where(img > rng.randint(150, 190), 255, 0).astype(np.uint8)
        for _ in range(rng.randint(0, 3)):
            yy = rng.randint(0, h - 3)
            img[yy:yy + rng.randint(1, 2), :] = 0
        cv2.putText(img, f"FAX  {rng.randint(10, 12)}:{rng.randint(10, 59)}  P.{page_no:03d}/{total:03d}",
                    (40, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 1)
    if rng.random() < prof["turn"]:
        img = cv2.rotate(img, rng.choice([cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180]))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, prof["jpeg"]])
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


def degrade_pdf(src: Path, dst: Path, profile: str, rng: random.Random) -> None:
    prof = PROFILES[profile]
    doc = pymupdf.open(src)
    out = pymupdf.open()
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=prof["dpi"], colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        img = _damage(img, prof, rng, i + 1, len(doc))
        ok, png = cv2.imencode(".png", img)
        h, w = img.shape
        newp = out.new_page(width=w * 72 / prof["dpi"], height=h * 72 / prof["dpi"])
        newp.insert_image(newp.rect, stream=png.tobytes())
    out.save(dst, deflate=True)
    out.close()
    doc.close()
