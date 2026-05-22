# User Input Templates
English/Japanese concise templates for Phase 14 workflows.

- RDKit descriptors / RDKit記述子: `Compute descriptors from examples/smiles_list.csv (type=smiles_csv, columns id/smiles), dry-run only.` / `examples/smiles_list.csv から記述子計算（type=smiles_csv、列 id/smiles）、dry-run のみ。`
- Filter by descriptors / 記述子フィルタ: `Filter molecules by MolWt <= 300 and NumHDonors <= 5.` / `MolWt<=300 かつ NumHDonors<=5 で分子を抽出。`
- Geometry analysis / 幾何解析: `Analyze geometry of examples/example.xyz (type=xyz), do not run xTB relaxation.` / `examples/example.xyz を解析、xTB緩和は実行しない。`
- xTB single-point / xTB一点計算: `Run xTB single-point energy from examples/example.xyz, do not optimize geometry.` / `examples/example.xyz で最適化なしのxTB一点エネルギー計算。`
- xTB relax dry-run / xTB緩和dry-run: `Prepare xyz_to_xtb_relax dry-run only; execution not allowed.` / `xyz_to_xtb_relax のdry-runのみ、実行許可なし。`
- Compare XYZ / XYZ比較: `Compare two geometries: examples/geometry_a.xyz and examples/geometry_b.xyz.` / `2つの構造を比較: examples/geometry_a.xyz と examples/geometry_b.xyz。`
- RMSD / RMSD計算: `Compute RMSD between two XYZ files.` / `2つのXYZのRMSDを計算。`
- Count atoms / 原子数カウント: `Count Fe atoms` or `count C/H/O atoms` / `Fe原子数、またはC/H/O原子数を数える。`
- Split by atom ranges / 原子範囲分割: `Split by file-order indices 1-3 and 4-9.` / `ファイル順インデックス1-3と4-9で分割。`
- Unsupported handling / 非対応処理: `If task is DFT TS or NEB, return unsupported.` / `DFT TS/NEBはunsupportedで停止。`
- Backend unavailable / バックエンド不足: `If molSimplify unavailable, return backend_unavailable.` / `molSimplify未導入時はbackend_unavailable。`
