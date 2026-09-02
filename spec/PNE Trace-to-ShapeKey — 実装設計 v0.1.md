# PNE Trace-to-ShapeKey — 実装設計 v0.1

## 0. 文書状態

- 状態：実装着手用ドラフト
- 対象：顔パーツ画像から、View Stateへ割り当て可能な同一トポロジMesh／Shape Keyを生成する
- 統合先：PNE 2.5D View State Editor
- 最初の検証対象：開眼／閉眼の上瞼ラインから`Basis`／`Blink`を生成する

---

## 1. 実現性

実装可能である。

ただし、次の方法は採用しない。

```text
open.png   → 独立SVG → 独立Mesh
closed.png → 独立SVG → 独立Mesh
                     ↓
               そのままShape Key化
```

独立トレースでは頂点数、頂点順、始点、方向、面構成が一致しないためである。

採用方式：

```text
Open Image ──→ Trace ──→ Open Guide Path ──┐
                                            ├→ Pair Alignment
Closed Image → Trace ──→ Closed Guide Path ┘
                                                  ↓
                                      共通N点へ弧長Resample
                                                  ↓
                                      Eyelid Ribbon TemplateへFit
                                                  ↓
                                      1個の同一Topology Mesh
                                      ├─ Basis = Open
                                      ├─ BlinkHalf = Half optional
                                      └─ Blink = Closed
```

トレース結果は最終Meshではなく、共通テンプレートを変形するためのガイドとして使う。

---

## 2. 現行環境での方針

確認時点のローカル環境：

```text
Blender   5.2.0 LTS
SVG Import API  available
NumPy     available in Blender Python
Inkscape  1.4.4 installed
Potrace   not installed
OpenCV    not installed in Blender Python
Pillow    not installed in Blender Python
```

このためv0.1は、外部ツールを必須にしない。

### 標準Backend

```text
NATIVE_ALPHA
```

Blender Image APIとNumPyでAlpha／輝度Maskを作り、Marching Squaresまたは走査ベースの輪郭抽出を行う。

### 任意Backend

```text
SVG_FILE
POTRACE_CLI
INKSCAPE_CLI
```

- `SVG_FILE`は外部で作成済みのSVGを入力する
- `POTRACE_CLI`は実行ファイルPathが設定されている場合だけ有効化する
- `INKSCAPE_CLI`はSVG変換、簡略化、確認用途を中心に使う
- Backendの出力はすべて共通の`TracePath`へ変換し、後段処理を共通化する

Blender標準のSVG Import→Curve→MeshはPreviewには利用できるが、Shape Key Pairの最終Mesh生成には直接使わない。SVGごとにSpline分割数や頂点数が変わる可能性があるためである。

---

## 3. NパネルUI

```text
Trace-to-ShapeKey
────────────────────────
Mode
[ Single Part / ShapeKey Pair ]

View State
[ front_0 ▼ ]

Role
[ Brow / Upper Eyelid / Mouth Line / Nose ]

Side
[ Left / Right / Center ]

Basis Image
[ open_upper_lid.png      ... ]

Target Image
[ closed_upper_lid.png    ... ]

Half Image optional
[ half_upper_lid.png      ... ]

Trace Backend
[ Native Alpha ▼ ]

Trace Mode
[ Alpha / Threshold / Edge ]

Threshold        [0.62]
Min Area px      [24]
Simplify px      [0.35]
Smooth           [0.20]
Stations         [32]
Stroke Width     [Auto]

[ Preview Masks ]
[ Preview Paths ]

Landmarks
[ Auto Detect Corners ]
[ Set Inner Corner ] [ Set Outer Corner ]
[ Reverse Direction ]

[ Build ShapeKey Pair ]
[ Assign To Current View ]
```

Roleが`Upper Eyelid`の場合は、`Basis Image`をOpen、`Target Image`をClosedとして表示する。

失敗時に手修正へ移れるよう、Inner Corner／Outer Cornerの手動指定を必須のFallbackとして持つ。

---

## 4. 内部データ

```python
TracePath:
    points_px: list[Vector2]
    closed: bool
    area_px: float
    winding: CW | CCW
    source_island: int

PathLandmarks:
    start_px: Vector2
    end_px: Vector2
    start_kind: inner_corner | outer_corner
    direction: inner_to_outer

NormalizedPath:
    stations: list[Vector2]
    half_widths: list[float]
    station_count: int
    source_bounds_px: Rect

TemplateFitResult:
    vertices_open: list[Vector3]
    vertices_half: list[Vector3] | None
    vertices_closed: list[Vector3]
    faces: list[tuple[int, int, int, int]]
    uv: list[Vector2]
```

画像座標は左上原点のPixel座標で保持し、Mesh生成直前にBlenderローカル座標へ変換する。

---

## 5. 共通Pipeline

```text
1. Source Load
2. Mask Build
3. Connected Component検出
4. 小Island除去
5. Contour／Guide Path抽出
6. Path Cleanup
7. Landmark検出または手動指定
8. Path方向統一
9. Pair Alignment
10. 弧長Resample
11. Role Template Fit
12. Mesh生成
13. Shape Key生成
14. UV／Material生成
15. Custom Property設定
16. Current Viewへ割り当て
17. Validation
```

各段階の結果を再利用できるよう、Preview TraceとBuildの間で中間データをScene設定または一時Text datablockへ保持する。

---

## 6. 上瞼Shape Key Pair

### 6.1 最終Topology

上瞼の黒線は、閉じた輪郭Polygonではなく、中心線に沿うRibbon Meshにする。

`Stations = 32`の場合：

```text
centerline samples : 32
vertices           : 64
faces              : 31 quads

inner corner
v00_top ── v01_top ── ... ── v31_top
   │          │                   │
v00_bottom─v01_bottom─ ... ── v31_bottom
                                      outer corner
```

すべてのShape Keyで64頂点、31 Quad、同一頂点順を維持する。

### 6.2 Guide Path抽出

Alpha Maskから単純に外周を取ると、黒線の上辺と下辺を含む閉じた輪郭になる。そのままShape Keyへ使うと、開眼と閉眼で対応点がねじれやすい。

上瞼では次を行う。

1. 対象Islandの主軸を求める
2. Inner→Outer方向へMaskを走査する
3. 各断面のAlpha重心をCenterlineとする
4. 各断面の幅をStroke Widthとして記録する
5. CenterlineをSmoothする
6. 弧長で32点へ再サンプリングする

大きく折り返す線や主軸方向に単調でない線は、自動走査を中止してManual Guide Modeへ切り替える。

### 6.3 Open／Closedの対応付け

```text
Open v00   = inner corner
Open v31   = outer corner

Closed v00 = inner corner
Closed v31 = outer corner
```

Closed PathをOpen Pathへ合わせるため、両端を使って平行移動、回転、等方Scaleを求める。最終的に両端は共通Corner Anchorへ固定できる。

左右反転時も、頂点順は常にキャラクター本人基準の`inner_to_outer`とする。画像上の左→右へ固定しない。

### 6.4 Mesh生成

各Centerline Stationで接線と法線を計算し、上下2頂点を作る。

```text
top_i    = center_i + normal_i × half_width_i
bottom_i = center_i - normal_i × half_width_i
```

急な角でRibbonが自己交差しないよう、Miter Lengthに上限を設ける。

### 6.5 Shape Key

```text
Basis       Open座標
BlinkHalf   Half座標 optional
Blink       Closed座標
```

OpenとClosedの2枚だけでも生成可能である。ただしBlink中間形状が不自然な場合に備え、Half画像を任意入力できる。

### 6.6 BlinkHalfのRuntime Weight

`t = blink`として、Half画像がある場合は2つのMorph Targetを区分線形で駆動する。

```text
0.0 ≤ t < 0.5
BlinkHalf = 2t
Blink     = 0

0.5 ≤ t ≤ 1.0
BlinkHalf = 2(1 - t)
Blink     = 2t - 1
```

これにより、

```text
t = 0.0  Open
t = 0.5  Half
t = 1.0  Closed
```

を通る。

---

## 7. 上瞼線だけではBlinkは完成しない

目全体を自然に閉じるには、少なくとも次を同期する。

```text
eye_*_lid_upper_line   Ribbon Shape Key
eye_*_lid_upper_fill   白目を隠す肌色Mask
eye_*_highlight        opacity fade
eye_*_core             必要時opacity fadeまたは遮蔽
```

上瞼線だけをOpen→Closedへ動かすと、閉眼時にも白目や虹彩が見える可能性がある。

v0.1では上瞼Ribbonの生成を先に完成させ、次段階で同じBlink Channelに連動する`lid_upper_fill`を自動生成する。

---

## 8. Role別Template

### 8.1 Brow

```text
方式：Closed silhouetteまたはRibbon
自動化：高
既定Stations：24
Shape Key例：Basis / Up / Down / InnerUp / Angry
```

細い眉はRibbon、太い眉は固定境界数のClosed TemplateへFitする。

### 8.2 Upper Eyelid

```text
方式：Open Ribbon
自動化：中〜高
既定Stations：32
Shape Key例：Basis / BlinkHalf / Blink / Wide / Squint
```

最初の実装対象とする。

### 8.3 Mouth Line

```text
方式：Open Ribbon
自動化：中
既定Stations：32
Shape Key例：Basis / Smile / Frown
```

単純な口線は上瞼と同じ方式を使える。

口を開けて内部の穴が生まれる形は、Open Ribbonと同じTemplateにしない。Topologyが変わるため、次のいずれかを使う。

- 外周＋内周を最初から持つ固定Mouth Template
- 口内を別Mesh／Spriteとしてopacity制御
- 離散的な口Texture切替

v0.1では、口線のNeutral→Smile／Frownまでを対象にし、Closed→Openの口腔生成は別Phaseとする。

### 8.4 Eye Full

眼球、白目、上瞼、下瞼を一枚のTrace Meshへ統合しない。

```text
sclera
core
highlight
lid_upper_line
lid_upper_fill
lid_lower_line
```

へ分ける。Trace-to-ShapeKeyは最初に`lid_upper_line`を担当する。

### 8.5 Nose

標準ではBASEへ焼き込む。独立させる場合も単一画像のTrace／配置補助までとし、v0.1のShape Key Template対象外とする。

---

## 9. PNE Role／ID拡張

現行PNEは`eye_l`や`eye_r`を1個のMesh Roleとして扱っている。複数レイヤー化のため、`pne_subrole`と`pne_expression_channel`を追加する。

例：

```text
pne_id                 = eye_l_lid_upper_line.front_30
pne_role               = eye_l
pne_subrole            = lid_upper_line
pne_view_id             = front_30
pne_expression_channel = blink_l
pne_template_id        = eyelid_ribbon_v1_32
pne_topology_hash      = <stable hash>
pne_trace_source_basis = open_upper_lid.png
pne_trace_source_key   = closed_upper_lid.png
```

親Empty：

```text
EYE_L_front_30
├─ eye_l_sclera_front_30
├─ eye_l_core_front_30
├─ eye_l_highlight_front_30
├─ eye_l_lid_upper_line_front_30
└─ eye_l_lid_upper_fill_front_30
```

Validatorは`pne_role=eye_l`の全Meshへ一律にBlink Shape Keyを要求せず、`pne_expression_channel=blink_l`を宣言した変形Meshだけを検査する。

---

## 10. UV／Material

### v0.1標準

上瞼、眉、口線は単色Materialを使う。線形状そのものをMeshで表現するため、Source画像をそのままTextureとして貼る必要はない。

### Textureを使う場合

RibbonのUVはTopologyに固定する。

```text
U = station index / (N - 1)
V = top 1.0 / bottom 0.0
```

Shape Keyで座標だけが変わり、UVは変えない。OpenとClosedで異なる描き込みを完全再現したい場合は、Shape KeyだけでなくTexture Blendを併用する。

---

## 11. Preview／Manual Correction

Preview用Collection：

```text
PNE_TRACE_PREVIEW
├─ basis_mask_plane
├─ target_mask_plane
├─ basis_path
├─ target_path
├─ landmark_inner
├─ landmark_outer
└─ resampled_points
```

表示色：

```text
Basis Path  green
Target Path magenta
Landmarks   yellow
Invalid     red
```

最低限の手修正：

- Island選択
- Inner／Outer Corner指定
- Path反転
- 不要Path削除
- Guide Point移動
- Stroke Width上書き

手修正後も、最終MeshはTemplateから再生成する。

---

## 12. ログ

Blender Text datablock：

```text
PNE_TRACE_LOG
```

成功例：

```yaml
[TRACE LOG]
role: upper_eyelid
side: left
view_id: front_30
basis: open_upper_lid.png
target: closed_upper_lid.png
backend: native_alpha
mode: alpha
threshold: 0.58
islands_detected: 3
islands_removed: 2
basis_path_points: 146
target_path_points: 121
stations: 32
mesh_vertices: 64
mesh_faces: 31
shape_keys: [Basis, Blink]
endpoint_error_px: 0.42
status: OK
```

失敗例：

```yaml
[TRACE ERROR]
role: upper_eyelid
stage: landmark_detection
reason: ambiguous_endpoints
suggestion: set inner and outer corner manually
```

---

## 13. Validator

```text
Source画像不存在
Source画像解像度0
Maskが空
Island数過多
Min Area以下のみ
Open Path抽出失敗
Inner／Outer Corner未決定
Path方向不一致
Station数不一致
Mesh頂点数不一致
Shape Key頂点数不一致
Topology Hash不一致
Ribbon自己交差
Miter Limit超過
Stroke Width 0
Endpoint Error閾値超過
Blink 0/0.25/0.5/0.75/1で自己交差
pne_id重複
pne_view_id未設定
pne_expression_channel未設定
```

Shape Keyの中間値は必ずPreviewする。OpenとClosedの両端だけが正常でも、中間でRibbonが裏返る場合があるためである。

---

## 14. モジュール構成

```text
blender_addon/pne_2_5d/
├─ trace_types.py
├─ trace_image.py
├─ trace_backends.py
├─ trace_path.py
├─ trace_landmarks.py
├─ trace_normalize.py
├─ trace_templates.py
├─ trace_mesh.py
├─ trace_shape_keys.py
├─ trace_part_assigner.py
├─ trace_validator.py
└─ trace_ui.py
```

責務：

```text
trace_image.py         Image読込、Mask、Connected Component
trace_backends.py      Native／SVG／Potrace／Inkscape Adapter
trace_path.py          Contour、Centerline、Cleanup
trace_landmarks.py     目頭、目尻、方向
trace_normalize.py     Alignment、弧長Resample
trace_templates.py     Role別Topology定義
trace_mesh.py          Mesh／UV／Material生成
trace_shape_keys.py    Basis／Target座標の登録
trace_part_assigner.py View State、Role、Custom Property設定
trace_validator.py     Pipeline／Mesh／中間Shape検査
trace_ui.py            Nパネル、Preview、Operator
```

既存`operators.py`と`ui.py`へ全処理を直接追加せず、登録Classだけを集約する。

---

## 15. Undo／非破壊性

- Build Operatorは`UNDO`対応にする
- Previewは専用Collectionへ生成する
- 再Build前に既存出力を上書きせず、`.001`を増やさない安定IDで置換候補を特定する
- 置換時は元Objectを`PNE_TRACE_BACKUP`へ退避できる
- Source画像を変更しない
- Current ViewへAssignするまで本番Collectionへ移動しない
- 外部CLIは一時Directoryだけを使用する

---

## 16. 実装順

```text
01 TracePath／NormalizedPathの純粋Pythonデータ型
↓
02 Native Alpha Mask＋単一Island抽出
↓
03 上瞼Centerline＋32点Resample
↓
04 Eyelid Ribbon Mesh生成
↓
05 Open／ClosedからBasis／Blink生成
↓
06 Blink 0〜1 Preview Slider
↓
07 Manual Corner指定
↓
08 Current View／Role割り当て
↓
09 Validator／PNE_TRACE_LOG
↓
10 lid_upper_fill生成とBlink同期
↓
11 Brow Template
↓
12 Mouth Line Template
↓
13 SVG_FILE Backend
↓
14 POTRACE_CLI／INKSCAPE_CLI Adapter
↓
15 BlinkHalf Pair／Triple入力
```

最初のGo/No-Go地点は06である。

```text
同じViewのOpen／Closed上瞼画像2枚から、
1個の64頂点Ribbon Meshを生成し、
Blink 0.0〜1.0を連続操作しても、
頂点の交差、端点の滑り、線幅の破裂がないこと。
```

---

## 17. v0.1完成条件

1. Alpha背景のOpen／Closed上瞼画像を読み込める
2. 外部ツールなしでNative Alpha Traceが動く
3. Inner／Outer Cornerを自動または手動で決められる
4. 両Pathが同じ方向、同じ32 Stationへ正規化される
5. 64頂点、31 QuadのRibbon Meshが生成される
6. `Basis`と`Blink`の頂点対応が一致する
7. Blink 0/0.25/0.5/0.75/1で自己交差しない
8. 左右の瞼で本人基準の頂点順が一致する
9. `pne_id / pne_role / pne_subrole / pne_view_id`が設定される
10. Current Viewへ割り当て後、既存Expression SliderでBlinkできる
11. GLB Export後もBlink Morph Targetが残る
12. Trace結果と失敗理由が`PNE_TRACE_LOG`へ記録される
13. 操作全体をUndoできる

---

## 18. v0.1対象外

- 複数レイヤーが混ざった目全体の完全自動分解
- 画像だけからの目頭／目尻100%自動判定
- Topologyが変わる口Closed→Openの汎用変換
- すべての絵柄へ共通する線幅推定
- AI生成画像の左右非対称や位置ずれの完全自動修復
- ワンクリック無修正での量産保証

v0.1は「自動完成」ではなく、「対応済みShape Key Meshの下地を短時間で作る」ことを完成条件とする。
