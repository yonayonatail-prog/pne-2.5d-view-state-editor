FIXします。以降は **この仕様を v0.1 実装基準**として扱えばOKです。

# PNE 2.5D View State Editor v0.1 — FIX仕様

## 1. 基本方式

Blenderを **2.5Dキャラクターのオーサリング／デバッグ環境**として使用する。

```text
AI生成View素材
   ↓
View State
   ↓
局所Face Mesh
   ↓
View Transition
   ↓
Blender Preview
   ↓
GLB + state.json + Runtime Texture
   ↓
Three.js
```

キャラクター全体をLive2D的に変形するのではなく、複数方向の完成絵をView Stateとして保持する。

v0.1の基本View：

```text
front_0     yaw   0°
front_30    yaw  30°
side_30     yaw  60°
side_0      yaw  90°
```

将来のPitch対応のため `pitch_deg` は最初から保持する。

---

# 2. 1 Viewの構成

```text
STATE_front_30
├─ BASE
├─ EYE_L
├─ EYE_R
├─ BROW_L
├─ BROW_R
├─ MOUTH
├─ JAW_MASK
└─ OCCLUSION
```

生成素材数は制限しない。

特に必要なら、

```text
前髪
顔
耳
顎
鼻
アクセサリー
```

などを追加レイヤーとして分離可能。

ただしRuntime Roleは固定IDで管理する。

---

# 3. Face Mesh

局所的にメッシュ変形する。

### Eye

```text
4×4 ～ 6×6 Grid

Basis
Blink
Wide
Squint
```

### Brow

```text
4×2 Grid

Basis
Up
Down
InnerUp
Angry
```

### Mouth

```text
6×4 Grid

Basis
Open
Wide
Narrow
Smile
Frown
```

将来：

```text
A / I / U / E / O
```

### Jaw

```text
Basis
JawDown
```

v0.1ではJawDownのみ必須。

---

# 4. View Transition

## Raw Alpha Crossfadeは本番方式にしない

二重像防止のためTransition Modeを持つ。

```text
STEP
SHARP
DITHER      ← v0.1標準
ALPHA       ← Debug専用
WARP_DITHER ← 将来
```

### DITHER

2 Viewを半透明で重ねるのではなく、

```text
View A pixel
↓
Dither Pattern
↓
View B pixel
```

のように画素領域を入れ替える。

これをThree.js側の標準Transitionとする。

Blender Previewでも可能な限り同じ挙動を再現する。

---

# 5. 補間

Yawから隣接Viewを取得。

例：

```text
Yaw = 15°

A = front_0
B = front_30

t = 0.5
```

補間関数：

```text
linear
smoothstep
sharp
```

Ditherでは `t` をDither Thresholdとして使用する。

---

# 6. Expression同期

Transition中の2 Viewには同じExpression値を適用する。

```text
Blink = 0.7

front_0 Blink = 0.7
front_30 Blink = 0.7
```

目・口・眉・顎がView切替境界で飛ばないことを保証する。

---

# 7. 描画順

半透明SpriteのZ-Sort事故を避けるため、物理Zと `renderOrder` の両方を使う。

標準Role：

```text
BASE         renderOrder  0
JAW          renderOrder 10
EYE          renderOrder 20
BROW         renderOrder 21
MOUTH        renderOrder 22
OCCLUSION    renderOrder 30
FOREGROUND   renderOrder 40
```

概念Z：

```text
BASE        0.000
JAW         0.001
FACE PARTS  0.002
OCCLUSION   0.003
FOREGROUND  0.004
```

Three.jsでは原則：

```js
material.transparent = true;
material.depthWrite = false;
object.renderOrder = role.renderOrder;
```

---

# 8. 前髪・遮蔽

前髪をBASEへ完全統合しない。

少なくとも

```text
OCCLUSION
```

という独立Roleを持つ。

目・眉等が前髪を貫通しないための遮蔽素材として使用する。

必要なら `FOREGROUND` として前髪そのものを独立画像化してよい。

**素材数削減は優先しない。**

---

# 9. 左右反転

データモデルは最初から左右両対応。

```json
{
  "id": "front_30_l",
  "yaw_deg": -30,
  "flip_x": true,
  "mirror_source": "front_30_r"
}
```

非対称キャラの場合：

```json
{
  "id": "front_30_l",
  "yaw_deg": -30,
  "flip_x": false,
  "mirror_source": null
}
```

として独立画像を使用可能。

v0.1サンプルのみ左右対称キャラで検証する。

---

# 10. Runtime ID

**Blender Object NameをRuntime IDとして使用しない。**

各ObjectへCustom Propertyを持たせる。

```text
pne_id
pne_role
pne_view_id
```

例：

```text
pne_id      = eye_l.front_30
pne_role    = eye_l
pne_view_id = front_30
```

Three.js：

```js
scene.traverse((obj) => {
  const id = obj.userData.pne_id;
});
```

GLB ExportではCustom Propertiesを保持する。

---

# 11. Texture Atlas

Atlasは使用可能。

ただし **全View共通巨大Atlasは禁止**。

推奨：

```text
1 View = 1 Texture Pack
```

例：

```text
front_30/
├─ base
├─ face_parts
├─ occlusion
└─ jaw
```

face_parts Atlasには十分なPaddingを設ける。

初期基準：

```text
各Island周囲 32px以上
```

ShapeKey変形によって隣接Atlas領域へUVが侵入しないこと。

Validatorでチェック対象とする。

---

# 12. Source AssetとRuntime Assetを分離

生成素材は高解像度のまま保存する。

```text
source/
├─ 4K PNG
├─ AI生成原本
└─ 編集用素材
```

Runtime Build時に変換：

```text
source
  ↓
Resize
  ↓
Atlas
  ↓
KTX2
  ↓
runtime
```

例：

```text
BASE          2048
FACE PARTS    1024
OCCLUSION     1024
JAW           512～1024
```

Source Assetは変更・破棄しない。

---

# 13. Runtime Texture Format

Three.jsでは原則 **KTX2 / Basis** を使用。

```text
PNG/WebP
→ Source / Preview

KTX2
→ Runtime
```

端末側で対応するGPU圧縮形式へ変換する。

```text
BC
ASTC
ETC
```

等。

---

# 14. Texture Residency Manager

全TextureをVRAMへ常駐させない。

基本：

```text
Active View A
Active View B
Prefetch View C
LRU Cache
```

のみVRAMへ保持。

例：

```text
yaw 25°

Active
front_0
front_30

Prefetch
side_30
```

30°を超えたら：

```text
Active
front_30
side_30

front_0
→ LRU Cache
```

即disposeは禁止。

境界付近でロード／破棄を繰り返さないようLRU方式を使う。

---

# 15. Texture Budget

JSONにRuntime Policyを持つ。

```json
{
  "texture_policy": {
    "active_views": 2,
    "prefetch_views": 1,
    "cache_views": 2,
    "max_gpu_memory_mb": 256
  }
}
```

メモリ上限はRuntime側で変更可能。

---

# 16. Mipmap

用途別に設定する。

### Face Parts

基本：

```text
mipmap = false
```

### BASE

カメラ距離変化が大きい場合のみ：

```text
mipmap = true
```

すべてに無条件でMipMapを生成しない。

---

# 17. Blender UI

```text
PNE 2.5D
────────────────────

Character
[ character ▼ ]

Yaw
━━━━●━━━━

Pitch
━━━━●━━━━

Transition
[ DITHER ▼ ]

State A : front_0
State B : front_30
Blend   : 0.473

────────────────────
Expression

Blink L
Blink R
Brow
Mouth Open
Smile
Jaw

────────────────────
View States

front_0       0°
front_30     30°
side_30      60°
side_0       90°

[ Add View ]
[ Duplicate ]
[ Remove ]

────────────────────
Texture Memory

Active      38 MB
Prefetch    17 MB
Cache       29 MB

Estimated   84 / 256 MB

[ Purge Cache ]

────────────────────
Debug

[ Show Mesh ]
[ Show Raw Alpha ]
[ Show Render Order ]
[ 50/50 Preview ]

[ Validate Character ]

────────────────────
Export

[ Build Runtime Assets ]
[ Export Runtime Bundle ]

────────────────────
Sample

[ Build Sample Character ]
```

---

# 18. Debug表示

最低限常時確認可能にする。

```text
Yaw        : 17.4
Pitch      : 0

View A     : front_0
View B     : front_30

Transition : DITHER
Blend      : 0.581

Mirror     : false

Resident
front_0
front_30
side_30
```

Blender Text Data：

```text
PNE_DEBUG_LOG
```

にも記録する。

---

# 19. Validator

Export前に検査。

```text
View ID重複
Yaw重複
pne_id重複
Role不足
Object不存在
ShapeKey不存在
Texture不存在
UV Padding不足
Texture解像度不正
Custom Property不足
RenderOrder不足
Mirror Source不存在
```

例：

```text
✓ front_0
✓ front_30

✗ side_30
  Missing MOUTH

⚠ front_30 EYE_L
  UV safety margin < 32px
```

---

# 20. Export Bundle

```text
export/
├─ character.glb
├─ character.states.json
└─ textures/
   ├─ front_0/
   ├─ front_30/
   ├─ side_30/
   └─ side_0/
```

GLB：

```text
Mesh
ShapeKey
Custom Properties
```

JSON：

```text
View定義
Runtime ID
Transition
Render Order
Mirror
Texture Path
Texture Policy
Expression Mapping
```

を保持。

---

# 21. サンプルキャラクター

Add-onに同梱する。

特徴：

```text
左右対称
前髪あり
目・眉・口が大きい
顎形状が分かりやすい
4方向
```

`Build Sample Character` で、

```text
Collection生成
Mesh生成
Material生成
ShapeKey生成
View State登録
Texture登録
Custom Properties設定
```

まで自動化。

---

# 22. v0.1完成条件

以下が全部通ればFIX版v0.1完成。

1. Add-onインストール成功
2. Sample Character自動生成成功
3. Yaw 0〜90°を連続操作可能
4. Ditherで4 View遷移可能
5. Transition中もBlink/Mouth/Jaw同期
6. Occlusionが正常
7. RenderOrder正常
8. Blender再起動後もState保持
9. Validator動作
10. Runtime Texture Build成功
11. KTX2出力
12. GLB + JSON Export成功
13. Texture Residency情報をJSON出力

---

## 実装順もFIX

```text
01 Add-on骨格
↓
02 Sample Character Builder
↓
03 View State管理
↓
04 front_0 / front_30切替
↓
05 Dither Transition
↓
06 Eye / Mouth / Jaw
↓
07 Occlusion / RenderOrder
↓
08 4 View化
↓
09 Runtime ID / Custom Properties
↓
10 Validator
↓
11 Texture Runtime Build
↓
12 JSON Export
↓
13 GLB Export
↓
14 Three.js Texture Residency Manager検証
```

**最初のGo/No-Go地点は05のDither Transition。**

ここで `front_0 → front_30` が十分「顔が回って見える」なら、そのまま本実装へ進む。微妙なら構造を捨てずに `WARP_DITHER` を追加する。

これで **PNE 2.5D View State Editor v0.1 仕様FIX** でいいと思う。
