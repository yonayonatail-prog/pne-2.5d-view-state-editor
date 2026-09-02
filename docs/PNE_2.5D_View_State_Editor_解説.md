# PNE 2.5D View State Editor 解説

この文書は、Blender用アドオン **PNE 2.5D View State Editor v0.1.1** の使い方と、画面に表示される項目の意味を説明するものです。

添付されている画面は、Blenderの3D Viewportにある `PNE 2.5D` サイドバーです。アドオン本体の画面を示す参考画像であり、画像内のラベルを別の操作指示として扱うものではありません。

## 1. このアドオンでできること

PNE 2.5Dは、1体のキャラクターを完全な3Dモデルとして変形するのではなく、**複数方向から見た完成絵をView Stateとして管理する**ためのBlenderアドオンです。

各View Stateには、次の情報を持たせます。

- キャラクターを何度の方向から見た絵か
- その方向に属するメッシュとShape Key
- 表情用の顔パーツ
- Base、顔パーツ、遮蔽、顎の4種類のテクスチャ
- 左右反転やミラー元
- ランタイムで使うID、描画順、概念的な奥行き

ビューポート上では、Yawに応じて隣り合う2つのView Stateを選び、DITHERなどの方式で切り替えます。切り替え中も、瞬き・眉・口・顎などの表情値を両方のViewへ同期します。

最終的には、Three.jsなどのランタイムへ渡す次のファイルを出力できます。

```text
character.glb
character.states.json
texture_build.json
textures/
  <view_id>/
    base.png
    base.ktx2
    face_parts.png
    face_parts.ktx2
    occlusion.png
    occlusion.ktx2
    jaw.png
    jaw.ktx2
```

## 2. インストール

対応バージョンはBlender 4.2以降です。リポジトリには、インストール用のZIPが次の場所にあります。

```text
blender_addon/dist/pne_2_5d_view_state_editor_v0.1.1.zip
```

1. Blenderで `Edit > Preferences > Add-ons` を開く。
2. `Install from Disk...` を選ぶ。
3. `pne_2_5d_view_state_editor_v0.1.1.zip` を指定する。
4. `PNE 2.5D View State Editor` を有効にする。
5. 3D Viewportの右側にあるSidebarを開き、`PNE 2.5D` タブを選ぶ。

サイドバーが見えない場合は、3D Viewport上で `N` キーを押します。

## 3. 基本用語

### View State

特定の視点に対応する1枚分のキャラクター状態です。例えば次の4つを登録します。

| View ID | Yaw |
| --- | ---: |
| `front_0` | 0° |
| `front_30` | 30° |
| `side_30` | 60° |
| `side_0` | 90° |

名前は自由に変更できますが、同じView IDや同じYawを複数登録することはできません。

### State A / State B

現在のYawを挟んでいる2つのView Stateです。Yawが15°なら、通常は0°のViewがState A、30°のViewがState Bになります。

### Blend

State AからState Bへどの程度進んでいるかを表す値です。0ならA、1ならBに近い状態です。`Smoothstep`を使うと、切り替えの始めと終わりが滑らかになります。

### Expression

View Stateを切り替えても共通して適用する表情値です。Shape Keyの名前を直接操作するのではなく、アドオンがオブジェクトのRoleに応じて適切なShape Keyへ値を渡します。

## 4. 画面の各セクション

### Character

#### Character

出力やデバッグに使うキャラクター識別子です。例として `pne_sample` や `sample_character` を指定します。

#### Yaw

左右方向の視点角度です。現在のView Stateの決定と、隣接View間の補間に使われます。

- 0°：正面
- 正の値：登録したYawの向きに進む
- 負の値：負方向の視点を扱える

登録したViewのYawの間に現在値が入ると、State AとState Bの2つが有効になります。

#### Pitch

上下方向の角度です。View Stateごとにも保存されます。

v0.1では、Viewの選択と補間はYawを基準に行います。Pitchは将来の上下視点対応に備えて保持される値であり、PitchによるView Stateの自動切り替えは現行版の中心機能ではありません。

#### Transition

View Stateの切り替え方法です。

| モード | 説明 |
| --- | --- |
| `STEP` | 途中の補間を行わず、境界で切り替える。 |
| `SHARP` | 短い範囲で急に切り替えるデバッグ向け方式。 |
| `DITHER` | ピクセル単位のマスクでA/Bを入れ替える。v0.1の標準方式。 |
| `ALPHA (Debug)` | 通常のアルファによるクロスフェードを確認するデバッグ方式。二重像が出やすいため、本番の標準方式にはしない。 |
| `WARP_DITHER (Future)` | 将来用の予約項目。現行実装ではDITHERとして処理されます。 |

`DITHER`は2枚の画像を半透明で重ねるのではなく、画面上のピクセルごとにAまたはBを表示します。そのため、回転途中の二重像を抑えやすい設計です。

#### Interpolation

Yawから得られた補間値のカーブです。

- `Linear`：一定速度で変化
- `Smoothstep`：始まりと終わりが滑らか
- `Sharp`：中央付近で素早く切り替え

### Expression

表情値はスライダーで調整します。変更すると、登録済みのPNEオブジェクトへ自動的に反映されます。

| 項目 | 範囲 | 動作 |
| --- | ---: | --- |
| `Blink L` | 0〜1 | キャラクターから見て左目の開閉。0が開眼、1が閉眼。 |
| `Blink R` | 0〜1 | キャラクターから見て右目の開閉。 |
| `Brow` | -1〜1 | 眉の上下。正の値で上げ、負の値で下げる。 |
| `Mouth Open` | 0〜1 | 口の開き具合。 |
| `Smile` | -1〜1 | 正の値で笑顔、負の値で不機嫌・下向き。 |
| `Jaw` | 0〜1 | 顎の開き。JawDown Shape Keyへ反映。 |

まばたきに `BlinkHalf` Shape Keyがある場合、0〜0.5と0.5〜1の区間を使って半目状態を滑らかに表現します。`BlinkHalf`がない場合は、`Blink` Shape Keyだけで処理します。

View Stateの切り替え中は、State AとState Bの両方へ同じExpression値が適用されます。例えばBlinkが0.7のとき、A側だけ閉じてB側が開くという不連続な状態にならないように設計されています。

### View States

登録されているView Stateの一覧です。各行にはView IDとYawが表示されます。

#### `Add View`

空のView Stateと、それに対応するコレクションを追加します。追加直後は、オブジェクトとテクスチャがないため、Validatorではエラーになります。

#### `Duplicate`

選択中のView Stateを、独立したコレクションとして複製します。メッシュ、Shape Key、テクスチャ設定、左右反転設定などを引き継ぎます。

複製後は、View ID、Yaw、テクスチャ、必要な顔パーツを確認してください。

#### `Remove`

選択中のView Stateと、それに紐づく生成オブジェクトを削除します。必要なViewを誤って選択していないか確認してから実行してください。

一覧の下には、選択中のViewに対する個別設定があります。

- `Pitch`：そのView固有の上下角
- `Flip X`：テクスチャやパーツを左右反転する設定
- `Mirror Source`：ミラー元にする別ViewのID

`Mirror Source`を入力した場合、指定したView IDが実際に存在している必要があります。

#### Texture Pack

各Viewが使用する4種類の入力画像です。

| 項目 | 役割 | 必須ファイルの例 |
| --- | --- | --- |
| `Base` | キャラクターの基本絵・身体 | `base.png` |
| `Face Parts` | 目、眉、口などの顔パーツ | `face_parts.png` |
| `Occlusion` | 前髪など、後ろのパーツを隠す遮蔽 | `occlusion.png` |
| `Jaw` | 顎・口元の独立レイヤー | `jaw.png` |

これらは編集用のSource画像です。Export時に解像度を整え、ランタイム用PNGとKTX2へ変換します。Source画像自体は上書きされません。

### Texture Memory

ランタイムでどのViewのテクスチャを保持するかを確認する欄です。

| 表示 | 意味 |
| --- | --- |
| `Active` | 現在表示しているState A/B。通常は2View。 |
| `Prefetch` | 次に使う可能性が高いため先読みするView。 |
| `Cache` | 直前に使ったViewなどを残す論理キャッシュ。 |
| `Estimated` | 上記を合計した推定容量とGPU Budget。 |

下段の `A`、`P`、`C` は、それぞれActive、Prefetch、Cacheの保持数です。`GPU Budget`はランタイムで許容するテクスチャ容量の目安で、初期値は256MBです。

`Purge Cache`を押すと、ActiveとPrefetchを残して論理キャッシュだけを消去します。境界付近での読み込みと破棄の繰り返しを避けるため、現在表示中のViewは消去しません。

### Debug

表示確認用のスイッチです。

- `Show Mesh`：メッシュのワイヤ表示を確認する
- `Show Raw Alpha`：DITHERではなく、素材のアルファによる見え方を確認する
- `Show Render Order`：オブジェクト名と描画順の確認に使う
- `50/50 Preview`：A/Bの中間値を強制して、境界の見え方を確認する

#### `Validate Character`

View Stateと書き出し条件を検査します。主に次を確認します。

- Character ID、View ID、Yawの重複
- View Stateに紐づくCollectionの存在
- 必須Roleの不足
- `pne_id`、`pne_role`、`pne_view_id`などのCustom Property
- 必須Shape Key
- `Base`、`Face Parts`、`Occlusion`、`Jaw`テクスチャの存在
- Texture解像度
- Render Orderと概念的な奥行き
- Mirror Sourceの参照先
- Trace-to-ShapeKey出力の頂点数・面数・メタデータ

検査結果は画面に表示され、デバッグ用のテキストデータ `PNE_DEBUG_LOG` にも現在のYaw、State A/B、Blend、Resident情報が記録されます。

表示の意味は次の通りです。

- `0 error(s), 0 warning(s)`：書き出し可能な状態
- `ERROR`：書き出し前に修正が必要
- `WARNING`：書き出しは可能な場合があるが、意図した品質か確認が必要
- `INFO`：View Stateが有効であることを示す情報

### Export

#### Output

出力先フォルダーです。初期値は、現在のBlendファイルを基準にした相対パス `//pne_export` です。相対パスを使う場合は、先にBlendファイルを保存してください。

#### 解像度

ランタイム用テクスチャの出力解像度です。初期値は次の通りです。

| テクスチャ | 初期解像度 |
| --- | ---: |
| Base | 2048×2048 |
| Face Parts | 1024×1024 |
| Occlusion | 1024×1024 |
| Jaw | 512×512 |

#### `toktx / basisu`

`toktx`の実行ファイルを指定できます。未指定でもPATH上に`toktx`があれば自動検出します。

- 利用できる場合：Basis LZ圧縮KTX2を生成
- 利用できない場合：内蔵の非圧縮RGBA8 KTX2ライターへフォールバック

したがって、`toktx`がなくてもKTX2出力自体は試行できます。ただし、ランタイム向けの圧縮効率やGPU向け形式が必要な場合は`toktx`を設定してください。

#### `Build Runtime Assets`

Source画像を指定解像度へ変換し、各Viewのフォルダーへ次を生成します。

- ランタイム確認用のPNG
- 実行時テクスチャのKTX2
- ビルド結果をまとめた`texture_build.json`

この処理はGLBや状態JSONを作らず、テクスチャ関連のビルドだけを行います。

#### `Export Runtime Bundle`

次の順番で処理します。

1. Validatorを実行する。
2. ERRORがあれば書き出しを停止する。
3. ランタイム用テクスチャを作る。
4. PNEオブジェクトをGLBへ書き出す。
5. View State、Transition、Render Order、Expression Mapping、Texture Policyを`character.states.json`へ書き出す。

GLBにはメッシュ、Shape Key、Custom Propertyなどが含まれます。JSONにはBlenderのオブジェクト名ではなく、ランタイム用の`pne_id`を使った情報が保存されます。

### Sample

#### `Build Sample Character`

動作確認用の4方向サンプルを自動生成します。次の作業をまとめて行います。

- `PNE_2_5D_CHARACTER`コレクションの作成
- 4つのView Stateと対応Collectionの作成
- Base、目、眉、口、顎、Occlusionのメッシュ作成
- Shape Keyの作成
- DITHER用マテリアルの作成
- View ID、Role、描画順などのCustom Property設定
- サンプルテクスチャの生成と登録

初めて使う場合は、まずBlendファイルを保存してからこのボタンを押してください。

## 5. Trace-to-ShapeKey

`Trace-to-ShapeKey`は、開眼・閉眼などの画像輪郭から、同じトポロジーを持つRibbon MeshとShape Keyを生成する機能です。

画像を単にPlaneへ貼るのではなく、BasisとTargetが同じ頂点構成になるように再構築します。そのため、Shape Keyで開眼から閉眼へ変形できます。

### 入力項目

#### Current View

生成したメッシュを割り当てる現在のView Stateです。先にView Stateを作成またはサンプルをビルドしてください。

#### Role

生成するパーツの種類です。

- `Upper Eyelid`：上まぶた。Blink Shape Keyを作る
- `Brow`：眉
- `Mouth Line`：口の線
- `Nose`：鼻の線

#### Side

左右または中央を指定します。

- `Left`
- `Right`
- `Center`

上まぶたと眉はLeftまたはRightが必要です。口や鼻はCenterを使います。

#### Basis / Open

基準となる画像です。上まぶたなら開眼画像を指定します。

#### Target / Closed

変形先の画像です。上まぶたなら閉眼画像を指定します。

#### Half (Optional)

半目状態の画像です。指定すると、`BlinkHalf`と`Blink`の2段階Shape Keyを生成できます。

### Trace設定

- `Alpha`：画像のアルファチャンネルを輪郭として使う
- `Threshold`：アルファを考慮しながら暗い画素を輪郭として使う
- `Edge`：アルファや輝度の勾配を輪郭として使う
- `Threshold`：閾値方式で使う判定値
- `Min Area`：小さなノイズ領域を除外する基準
- `Smooth`：抽出経路を滑らかにする量
- `Stations`：輪郭上に配置するサンプル点の数
- `Mesh Width`：輪郭からRibbon Meshを作る幅
- `Reverse Direction`：輪郭の進行方向を反転する

### 操作手順

1. RoleとSideを選ぶ。
2. Basis / Open、Target / Closedを指定する。
3. 必要ならHalfを指定する。
4. `Preview Paths`で抽出経路を確認する。
5. `Build ShapeKey Pair`でメッシュとShape Keyを生成する。
6. `Blink Preview`で変形を確認する。
7. 問題がなければ`Assign To Current View`で現在のView Stateへ移動する。

`Preview Paths`では、BasisとTargetの経路をガイド表示します。不要になったガイドや生成プレビューは`Clear`で、Trace-to-ShapeKeyが生成したものだけを削除できます。

初期値の`Stations = 32`では、通常64頂点・31 QuadのRibbon Meshになります。Halfを指定した場合は、同じトポロジー上に次のShape Keyを持ちます。

```text
Basis
BlinkHalf
Blink
```

処理結果とエラーは、BlenderのText datablock `PNE_TRACE_LOG` に記録されます。

## 6. 最短の動作確認手順

1. Blendファイルを保存する。
2. `Build Sample Character`を押す。
3. Yawを0〜90°で動かす。
4. `State A`と`State B`が隣接Viewになることを確認する。
5. Transitionを`DITHER`にして、二重像を抑えた切り替えを確認する。
6. `Blink L/R`、`Brow`、`Mouth Open`、`Smile`、`Jaw`を動かす。
7. `50/50 Preview`でA/B境界の表情同期を確認する。
8. `Validate Character`を押す。
9. Outputを指定する。
10. 必要なら`Build Runtime Assets`でテクスチャだけを先に確認する。
11. `Export Runtime Bundle`を押す。

## 7. 自作キャラクターを登録する場合

各View Stateには、最低限次のRoleを揃えます。

```text
base
jaw
eye_l
eye_r
brow_l
brow_r
mouth
occlusion
```

各オブジェクトには、少なくとも次のCustom Propertyが必要です。

```text
pne_id
pne_role
pne_view_id
pne_render_order
pne_concept_z
```

標準の描画順は次の通りです。

| Role | Render Order |
| --- | ---: |
| `base` | 0 |
| `jaw` | 10 |
| `eye_l` / `eye_r` | 20 |
| `brow_l` / `brow_r` | 21 |
| `mouth` | 22 |
| `occlusion` | 30 |
| `foreground` | 40 |

Occlusionは、目や眉などが前髪を突き抜けて見えるのを防ぐ独立レイヤーです。前髪をBaseへ完全に焼き込まず、必要に応じてOcclusionまたはForegroundとして分けてください。

## 8. よくあるエラーと対処

| 症状 | 原因・対処 |
| --- | --- |
| `No View States are registered` | `Build Sample Character`を押すか、`Add View`でViewを作成する。 |
| `Texture does not exist` | 各Viewの4つのTexture Packに、実在する画像を指定する。 |
| `Missing role` | View StateのCollectionに、必要なRoleのオブジェクトを追加する。 |
| `missing Shape Key(s)` | Roleに応じたShape Keyを作成する。目はBlink/Wide/Squint、眉はUp/Downなどが基準。 |
| `Duplicate View ID` / `Duplicate Yaw` | View IDまたはYawを一意にする。 |
| `Mirror Source does not exist` | Mirror Sourceに存在するView IDを入力するか、空欄に戻す。 |
| `UV safety margin < 32px` | 警告。アトラス上の隣接領域へのにじみやShape Key変形時のUV侵入を確認し、必要なら余白を増やす。 |
| Exportが停止する | `Validate Character`でERRORを確認する。ExportはERRORが1件でもあると停止する。 |
| `toktx`が見つからない | 致命的とは限らない。内蔵の非圧縮RGBA8 KTX2へフォールバックする。圧縮出力が必要ならtoktxのパスを指定する。 |
| Yawを動かしてもViewが変わらない | View StateのYawが重複していないか、Viewが登録されているか確認する。 |
| 前髪を目が突き抜ける | Occlusionのテクスチャ・描画順・概念Zを確認する。 |

## 9. v0.1での注意点

- View Stateの補間はYaw中心です。Pitchは保存されますが、現行版ではYawのような上下方向のView選択には使いません。
- `ALPHA (Debug)`は見え方を確認するためのモードです。実際のView遷移にはDITHERを推奨します。
- `WARP_DITHER (Future)`は予約項目です。現行版で独自のワープ変形を行うものではありません。
- `Build Runtime Assets`はテクスチャビルド、`Export Runtime Bundle`はGLB・JSONを含む一式の出力です。
- v0.1の画面は、タイムライン編集、髪の物理、音声推論を行う汎用アニメーションエディタではありません。主な役割はView State、表情Shape Key、テクスチャ、ランタイム出力のオーサリングと検証です。
- 出力先の初期値`//pne_export`はBlendファイル基準の相対パスです。未保存のBlendでは、絶対パスを指定するか、先に保存してください。

## 10. 関連ファイル

実装やテストを確認したい場合は、次のファイルを参照してください。

- アドオン概要：[blender_addon/README.md](../blender_addon/README.md)
- UI定義：[blender_addon/pne_2_5d/ui.py](../blender_addon/pne_2_5d/ui.py)
- Blenderプロパティ：[blender_addon/pne_2_5d/properties.py](../blender_addon/pne_2_5d/properties.py)
- View補間・キャッシュ：[blender_addon/pne_2_5d/core.py](../blender_addon/pne_2_5d/core.py)
- プレビュー・表情同期：[blender_addon/pne_2_5d/runtime.py](../blender_addon/pne_2_5d/runtime.py)
- Validator：[blender_addon/pne_2_5d/validator.py](../blender_addon/pne_2_5d/validator.py)
- GLB・テクスチャ出力：[blender_addon/pne_2_5d/exporter.py](../blender_addon/pne_2_5d/exporter.py)
- Trace-to-ShapeKey：[blender_addon/pne_2_5d/trace_shape_keys.py](../blender_addon/pne_2_5d/trace_shape_keys.py)
- 動作確認用Blend：[pne_view_state_editor_demo.blend](../pne_view_state_editor_demo.blend)
- Trace確認用Blend：[pne_trace_to_shapekey_demo.blend](../pne_trace_to_shapekey_demo.blend)
