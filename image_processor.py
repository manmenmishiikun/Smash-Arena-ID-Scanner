"""
image_processor.py
画像前処理・テンプレートマッチング・ROI切り出しモジュール

設計ポイント:
  - arenahere.png (1080p) と arenahere_720p.png (720p) の2枚のテンプレートを使い分ける
  - まず 1920x1080 に合わせた画面で 1080p テンプレを照合（`find_and_extract_roi`）
  - 失敗かつ 720p テンプレがあり入力幅が 1280 以下のとき、ネイティブ解像度で 720p テンプレを照合（フォールバック）
  - 二値化後に反転 (WinRT OCRは白背景・黒文字が高精度)
  - 画像平滑化は使わず、ROI の上部・左側を軽くトリミングしてから固定閾値二値化
    （斜線ノイズや "ID:" プレフィックスの影響を減らす）
  - CHAR_CORRECTION_MAP で OCR誤認識しやすい文字を補正（O→0 は列挙時に分岐）
  - ROI は前処理の先頭で整数倍拡大（細字・局所二値化の解像度確保）
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

MATCH_THRESHOLD: float = 0.6       # テンプレートマッチング合否スコア閾値
# 粗い照合（1/2解像度）がこの値未満ならフル解像度の matchTemplate を省略（負荷削減）
# 低すぎると見逃しが増えるため、誤って高スコアが出にくい範囲に寄せている
COARSE_EARLY_EXIT_THRESHOLD: float = 0.14
# O の Q/0 分岐列挙で扱う最大位置数（2^N。長いノイズ文字列での爆発を防ぐ）
MAX_O_BRANCH_POSITIONS: int = 6
BINARIZE_THRESHOLD: int = 160      # 固定二値化の輝度閾値
# ROI を OCR 用に拡大する倍率（先頭で適用。負荷は ROI 面積に比例）
OCR_ROI_SCALE: float = 2.0
# OCRノイズ低減のため、ROI上部と左側を軽くトリミングする比率
OCR_TOP_CROP_RATIO: float = 0.20
OCR_LEFT_CROP_RATIO: float = 0.20

# ROI計算の相対比率 (arenahere.png の w, h を 1.0 として表現)
ROI_X_RATIO: float = 0.1
ROI_Y_RATIO: float = 0.9
ROI_W_RATIO: float = 1.3
ROI_H_RATIO: float = 1.2

# スマブラSPの部屋IDに使える文字:
# - 数字: 0-9
# - アルファベット大文字: I・O・Z を除く (キーボード上でグレーアウトされており選択不可)
# つまり有効文字は [A-HJ-NP-Y0-9] の計33種
#
# CHAR_CORRECTION_MAP:
# WinRT OCRは日本語対応が強いため、ゲームフォントを日本語文字と誤認識することがある。
# 代表例: 「 J 」 → 」 (右持弧・角カッコ)、「 Q 」 → 「 0 」と誤認識することが確認された。
# 「O」 は extract_room_id_from_text 内で Q/0 分岐と併用するためマップに含めない。
CHAR_CORRECTION_MAP: dict[str, str] = {
    # ── IDから排除されている文字の誤認識補正 (I/O/Z はグレーアウト) ──
    "I": "1",   # 大文字アイ   → 数字１ (I はグレーアウトで使用不可)
    "Z": "2",   # 大文字ゼット → 数字２ (Z はグレーアウトで使用不可)
    # ── WinRT OCRによる日本語文字誤認識の補正 ──
    # ゲームフォントの J が右持弧系文字に誤認識されることが実評で確認された。
    "」": "J",  # 右攖括弧 (全角) → J
    "》": "J",  # 右二重角》    → J
    "］": "J",  # ］全角右」    → J (布指定パターン)
    "]": "J",   # 半角角括弧閉じ  → J (一部環境で出る場合がある)
    # ── 全角数字の補正 ──
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
}

# 有効文字のみにマッチする正規表現 (I・O・Z を除く)
# 補正マップ適用後のテキストに対して使用するため、I/O/Z が残っていたとしても
# マッチせず誤ったIDを返さない安全弁としても機能する。
ROOM_ID_PATTERN = re.compile(r"[A-HJ-NP-Y0-9]{5}")


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    score: float
    x: int
    y: int
    w: int
    h: int


# ---------------------------------------------------------------------------
# ImageProcessor クラス
# ---------------------------------------------------------------------------

class ImageProcessor:
    """
    スマブラSP 画面から部屋IDを抽出する画像処理クラス。

    処理フロー:
      1. 入力解像度を判定し、720pテンプレート or 1080pテンプレートで照合
      2. アイコン基準の相対座標でIDテキスト領域(ROI)を切り出し
      3. グレースケール → 二値化 → 反転（白背景・黒文字化）
      4. WinRT OCR → 文字補正 → 5桁ID抽出
    """

    def __init__(
        self,
        template_1080p_path: str,
        template_720p_path: Optional[str] = None,
        debug: bool = False,
    ):
        self.debug = debug
        self._template_gray = self._load_template(template_1080p_path)
        self._template_gray_coarse = self._make_coarse_template(self._template_gray)
        self._template_720p_gray: Optional[np.ndarray] = None
        if template_720p_path:
            try:
                self._template_720p_gray = self._load_template(template_720p_path)
                logger.info("720p テンプレートを読み込みました")
            except FileNotFoundError:
                logger.info("720p テンプレートが見つかりません。1080p のみで動作します。")

    # -----------------------------------------------------------------------
    # 内部ヘルパー
    # -----------------------------------------------------------------------

    @staticmethod
    def _load_template(path: str) -> np.ndarray:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"テンプレート画像が見つかりません: {path}")
        return img

    @staticmethod
    def _make_coarse_template(template_gray: np.ndarray) -> Optional[np.ndarray]:
        """1/2 サイズのテンプレ（粗い照合用）。極小テンプレは粗い段をスキップする。"""
        th, tw = template_gray.shape[:2]
        if th < 12 or tw < 12:
            return None
        return cv2.resize(
            template_gray,
            (max(8, tw // 2), max(8, th // 2)),
            interpolation=cv2.INTER_AREA,
        )

    def _coarse_match_score(
        self, screen_gray: np.ndarray, template_coarse: Optional[np.ndarray]
    ) -> float:
        """粗い解像度での最大相関。template_coarse が None のときは照合しない前提で 1.0。"""
        if template_coarse is None:
            return 1.0
        th, tw = template_coarse.shape[:2]
        h, w = screen_gray.shape[:2]
        if h < th or w < tw:
            return 0.0
        sg = cv2.resize(
            screen_gray,
            (max(1, w // 2), max(1, h // 2)),
            interpolation=cv2.INTER_AREA,
        )
        if sg.shape[0] < th or sg.shape[1] < tw:
            return 0.0
        res = cv2.matchTemplate(sg, template_coarse, cv2.TM_CCOEFF_NORMED)
        return float(cv2.minMaxLoc(res)[1])

    def _match_template_with(
        self, screen_gray: np.ndarray, template: np.ndarray
    ) -> Optional[MatchResult]:
        """指定テンプレートでマッチングを行い、結果を返す。"""
        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < MATCH_THRESHOLD:
            return None
        th, tw = template.shape
        return MatchResult(score=score, x=loc[0], y=loc[1], w=tw, h=th)

    @staticmethod
    def _clip_roi(x: int, y: int, w: int, h: int, img_w: int, img_h: int) -> tuple:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)
        return x1, y1, x2, y2

    def _extract_roi_from_match(
        self, screen_bgr: np.ndarray, match: MatchResult
    ) -> np.ndarray:
        """MatchResult をもとにROIを切り出す。"""
        roi_x = int(match.x + match.w * ROI_X_RATIO)
        roi_y = int(match.y + match.h * ROI_Y_RATIO)
        roi_w = int(match.w * ROI_W_RATIO)
        roi_h = int(match.h * ROI_H_RATIO)
        img_h, img_w = screen_bgr.shape[:2]
        x1, y1, x2, y2 = self._clip_roi(roi_x, roi_y, roi_w, roi_h, img_w, img_h)
        return screen_bgr[y1:y2, x1:x2]

    def _preprocess(self, roi_bgr: np.ndarray) -> np.ndarray:
        """
        ROI画像をOCR用の白背景・黒文字画像に変換する。
        拡大 → グレースケール → ノイズ帯トリミング →
        固定閾値二値化 → 白黒反転
        """
        work = roi_bgr
        if OCR_ROI_SCALE != 1.0:
            # 拡大は INTER_LINEAR（CUBIC より軽量。ROI は小さめのため画質差は小さい）
            work = cv2.resize(
                work,
                None,
                fx=OCR_ROI_SCALE,
                fy=OCR_ROI_SCALE,
                interpolation=cv2.INTER_LINEAR,
            )

        gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        crop_y = int(h * OCR_TOP_CROP_RATIO)
        crop_x = int(w * OCR_LEFT_CROP_RATIO)
        # 余白帯・斜線ノイズ・IDプレフィックス("ID:")の影響を減らすために
        # OCR対象をID文字列寄りに限定する。
        cropped = gray[crop_y:, crop_x:]
        # ROI が極端に小さい場合、比率トリミングで空配列になることがあるため安全側に倒す。
        if cropped.size > 0:
            gray = cropped

        _, binary = cv2.threshold(gray, BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY)
        inverted = cv2.bitwise_not(binary)

        if self.debug:
            cv2.imwrite("debug_1_roi_original.png", roi_bgr)
            cv2.imwrite("debug_2_binary.png", binary)
            cv2.imwrite("debug_3_morphed.png", gray)  # 後方互換: 既存のデバッグ名を維持
            cv2.imwrite("debug_3_cropped_gray.png", gray)
            cv2.imwrite("debug_4_inverted.png", inverted)

        return cv2.cvtColor(inverted, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _correct_text_base(text: str) -> str:
        """O→0 を含まない補正（O は Q/0 列挙で扱う）。"""
        result = text.upper()
        result = re.sub(r"\s+", "", result)
        for wrong, correct in CHAR_CORRECTION_MAP.items():
            result = result.replace(wrong, correct)
        return result

    @staticmethod
    def _correct_text_legacy(text: str) -> str:
        """従来どおり O→0 も含めた補正（フォールバック用）。"""
        result = ImageProcessor._correct_text_base(text)
        result = result.replace("O", "0")
        return result

    @staticmethod
    def _expand_o_variants(s: str) -> list[str]:
        """O を Q または 0 に置いた文字列の組み合わせを列挙。"""
        if "O" not in s:
            return [s]
        idxs = [i for i, c in enumerate(s) if c == "O"]
        if len(idxs) > MAX_O_BRANCH_POSITIONS:
            idxs = idxs[:MAX_O_BRANCH_POSITIONS]
        out: list[str] = []
        for mask in range(1 << len(idxs)):
            chars = list(s)
            for bit, pos in enumerate(idxs):
                chars[pos] = "Q" if (mask >> bit) & 1 else "0"
            out.append("".join(chars))
        return out

    @staticmethod
    def _neighbor_flip_pairs(s: str) -> list[str]:
        """0↔Q および 6↔G の1文字入れ替え候補。"""
        out: list[str] = []
        for i, c in enumerate(s):
            if c == "0":
                out.append(s[:i] + "Q" + s[i + 1 :])
            elif c == "Q":
                out.append(s[:i] + "0" + s[i + 1 :])
            elif c == "6":
                out.append(s[:i] + "G" + s[i + 1 :])
            elif c == "G":
                out.append(s[:i] + "6" + s[i + 1 :])
        return out

    @staticmethod
    def _collect_room_ids_from_string(s: str) -> set[str]:
        return set(ROOM_ID_PATTERN.findall(s))

    @classmethod
    def _bfs_ambiguous_ids(cls, starts: list[str], max_depth: int = 2) -> set[str]:
        """O 展開済み文字列から、0/Q・6/G の反転を最大 max_depth 段試す。"""
        ids: set[str] = set()
        seen: set[str] = set()
        frontier = [s for s in starts if s not in seen]
        for s in frontier:
            seen.add(s)
        for depth in range(max_depth + 1):
            next_frontier: list[str] = []
            for t in frontier:
                ids |= cls._collect_room_ids_from_string(t)
                if depth < max_depth:
                    for n in cls._neighbor_flip_pairs(t):
                        if n not in seen:
                            seen.add(n)
                            next_frontier.append(n)
            frontier = next_frontier
        return ids

    @staticmethod
    def _pick_room_id_by_text_order(s: str, candidates: set[str]) -> Optional[str]:
        """
        複数の有効ID候補があるとき、補正後テキスト s 上で左から最初に現れるものを採用する。
        辞書順やハードコード特例は使わない（ランダムIDのため恣意的な順序は危険）。
        s 内に候補のどれも現れない場合は None（呼び出し側で legacy 等へ）。
        """
        if not candidates:
            return None
        if len(candidates) == 1:
            return next(iter(candidates))
        for m in ROOM_ID_PATTERN.finditer(s):
            hit = m.group(0)
            if hit in candidates:
                return hit
        return None

    @staticmethod
    def _extract_room_id(text: str) -> Optional[str]:
        m = ROOM_ID_PATTERN.search(text)
        return m.group(0) if m else None

    @staticmethod
    def _resize_to_1080p(screen_bgr: np.ndarray) -> np.ndarray:
        """OBS 解像度を 1920×1080 へ合わせる。縮小は INTER_AREA、拡大は INTER_LINEAR（LANCZOS4 より低負荷）。"""
        h, w = screen_bgr.shape[:2]
        if w == 1920 and h == 1080:
            return screen_bgr
        # いずれかの辺がターゲットより大きいときは縮小寄り
        down = w > 1920 or h > 1080
        interp = cv2.INTER_AREA if down else cv2.INTER_LINEAR
        return cv2.resize(screen_bgr, (1920, 1080), interpolation=interp)

    # -----------------------------------------------------------------------
    # 公開インターフェース
    # -----------------------------------------------------------------------

    def find_and_extract_roi(self, screen_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        画面全体 (BGR) からアイコンを検出し、前処理済み ROI 画像を返す。

        照合戦略（常に1080pを優先し、失敗時のみ720pで再試行）:
          1. 1920x1080 にリサイズして1080pテンプレートで照合
          2. 失敗 かつ 720pテンプレートあり かつ 入力が1280px以下
              → ネイティブサイズのまま720pテンプレートで照合
        """
        h, w = screen_bgr.shape[:2]

        # ── 1080p テンプレート（常に最初に試みる）──
        screen_1080 = screen_bgr
        if w != 1920 or h != 1080:
            screen_1080 = self._resize_to_1080p(screen_bgr)

        screen_gray_1080 = cv2.cvtColor(screen_1080, cv2.COLOR_BGR2GRAY)
        coarse_1080 = self._coarse_match_score(screen_gray_1080, self._template_gray_coarse)
        # 小さい入力は後段の 720p テンプレへ任せ、ここでフル1080を省略できる
        skip_1080_fine = coarse_1080 < COARSE_EARLY_EXIT_THRESHOLD and w <= 1280
        if not skip_1080_fine:
            match = self._match_template_with(screen_gray_1080, self._template_gray)
            if match is not None:
                roi_img = self._extract_roi_from_match(screen_1080, match)
                return self._preprocess(roi_img)

        # ── 720p テンプレート（フォールバック: 入力が720p以下の場合のみ）──
        # ネイティブ解像度が小さいためフル照合のコストが比較的軽いので粗い段の省略は行わない
        if self._template_720p_gray is not None and w <= 1280:
            screen_gray_native = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            match = self._match_template_with(screen_gray_native, self._template_720p_gray)
            if match is not None:
                if self.debug:
                    logger.debug("720p テンプレートで検出 (score=%.3f)", match.score)
                roi_img = self._extract_roi_from_match(screen_bgr, match)
                return self._preprocess(roi_img)

        return None

    def extract_room_id_from_text(self, raw_text: str) -> Optional[str]:
        base = self._correct_text_base(raw_text)
        direct_candidates = self._collect_room_ids_from_string(base)
        if len(direct_candidates) == 1:
            return next(iter(direct_candidates))
        if len(direct_candidates) > 1:
            picked = self._pick_room_id_by_text_order(base, direct_candidates)
            if picked is not None:
                return picked

        o_variants = self._expand_o_variants(base)
        candidates = self._bfs_ambiguous_ids(o_variants, max_depth=2)
        legacy = self._correct_text_legacy(raw_text)
        legacy_id = self._extract_room_id(legacy)

        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            picked = self._pick_room_id_by_text_order(base, candidates)
            if picked is not None:
                return picked
        if legacy_id:
            return legacy_id
        if base:
            safe_raw = raw_text.strip().replace("\n", " / ")
            logger.debug("OCR no match raw=%r corrected=%r", safe_raw, base)
        return None

