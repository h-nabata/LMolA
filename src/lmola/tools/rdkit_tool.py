from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from lmola.schemas import MoleculeBuildRequest, ToolCallRecord, ToolResult


def _record(status: str, run_dir: Path, message: str = "", stderr: str = "") -> ToolCallRecord:
    return ToolCallRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tool="rdkit",
        command=[],
        cwd=str(run_dir),
        returncode=None,
        stdout_excerpt=message[:2000],
        stderr_excerpt=stderr[:2000],
        status=status,
    )


def _write_xyz(mol, conf_id: int, xyz_path: Path) -> None:
    conf = mol.GetConformer(conf_id)
    atoms = mol.GetAtoms()
    lines = [str(len(atoms)), "LMolA RDKit-generated structure"]
    for atom in atoms:
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol()} {pos.x:.8f} {pos.y:.8f} {pos.z:.8f}")
    xyz_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_energy(mol, conf_id: int, force_field: str):
    from rdkit.Chem import AllChem

    try:
        if force_field == "mmff":
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is None:
                return None, "MMFF properties unavailable"
            ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=conf_id)
            if ff is None:
                return None, "MMFF force field unavailable"
            return float(ff.CalcEnergy()), None
        ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
        if ff is None:
            return None, "UFF force field unavailable"
        return float(ff.CalcEnergy()), None
    except Exception as exc:
        return None, str(exc)


def run_rdkit_generation(req: MoleculeBuildRequest, run_dir: Path) -> ToolResult:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except Exception:
        msg = "RDKit is unavailable. Install LMolA with the rdkit extra or install RDKit in the environment."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    smiles = (req.smiles or "").strip()
    if not smiles:
        msg = "SMILES input is required for small_molecule RDKit generation."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        msg = f"Invalid SMILES string: {smiles}"
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    opts = req.build_options
    if opts.add_hydrogens:
        mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3() if hasattr(AllChem, "ETKDGv3") and opts.embed_method.upper() == "ETKDGV3" else AllChem.ETKDG()
    if opts.random_seed is not None:
        params.randomSeed = int(opts.random_seed)

    num_confs = max(1, int(opts.num_conformers))
    if opts.prune_rms_thresh is not None:
        params.pruneRmsThresh = float(opts.prune_rms_thresh)
    if opts.max_embed_attempts is not None:
        params.maxAttempts = int(opts.max_embed_attempts)

    if num_confs <= 1:
        conf_ids = [AllChem.EmbedMolecule(mol, params)]
        if conf_ids[0] < 0:
            conf_ids = []
    else:
        conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=num_confs, params=params))

    if not conf_ids:
        msg = "RDKit failed to embed a 3D conformer for the provided SMILES."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    optimize = (opts.optimize or "").lower()
    ff_requested = (opts.force_field or optimize or "").lower() or None
    if ff_requested not in {None, "uff", "mmff"}:
        ff_requested = None

    conformer_rows = []
    conformer_dir = run_dir / "conformers"
    if num_confs > 1:
        conformer_dir.mkdir(parents=True, exist_ok=True)

    for idx, conf_id in enumerate(conf_ids):
        warnings: list[str] = []
        energy = None
        status = "not_requested"
        if optimize in {"uff", "mmff"}:
            try:
                if optimize == "uff":
                    AllChem.UFFOptimizeMolecule(mol, confId=conf_id)
                    status = "ok"
                else:
                    props = AllChem.MMFFGetMoleculeProperties(mol)
                    if props is None:
                        status = "unavailable"
                        warnings.append("MMFF properties unavailable")
                    else:
                        AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", confId=conf_id)
                        status = "ok"
            except Exception as exc:
                status = "error"
                warnings.append(str(exc))
        if ff_requested in {"uff", "mmff"}:
            energy, energy_warn = _safe_energy(mol, conf_id, ff_requested)
            if energy_warn:
                warnings.append(energy_warn)

        xyz_rel = "molecule.xyz" if num_confs <= 1 else f"conformers/conformer_{idx:03d}.xyz"
        _write_xyz(mol, conf_id, run_dir / xyz_rel)
        conformer_rows.append({
            "conformer_id": int(conf_id),
            "energy": energy,
            "energy_units": "kcal/mol" if energy is not None else None,
            "xyz_path": xyz_rel,
            "sdf_path": None,
            "optimization_status": status,
            "warnings": warnings,
        })

    sortable = [row for row in conformer_rows if row["energy"] is not None]
    if sortable:
        sortable.sort(key=lambda row: row["energy"])
        ranked_ids = {row["conformer_id"]: rank for rank, row in enumerate(sortable, start=1)}
        for row in conformer_rows:
            row["rank"] = ranked_ids.get(row["conformer_id"])
        best = sortable[0]
    else:
        for rank, row in enumerate(conformer_rows, start=1):
            row["rank"] = rank
        best = conformer_rows[0]

    generated = [row["xyz_path"] for row in conformer_rows]
    best_conf_id = int(best["conformer_id"])
    if num_confs > 1:
        _write_xyz(mol, best_conf_id, run_dir / "molecule.xyz")
        generated.append("molecule.xyz")

    if any(fmt.lower() == "sdf" for fmt in opts.output_formats):
        sdf_path = run_dir / "molecule.sdf"
        writer = Chem.SDWriter(str(sdf_path))
        writer.write(mol, best_conf_id)
        writer.close()
        generated.append("molecule.sdf")

    ensemble_payload = {
        "smiles": smiles,
        "num_requested": num_confs,
        "num_embedded": len(conf_ids),
        "num_optimized": sum(1 for row in conformer_rows if row["optimization_status"] == "ok"),
        "force_field": ff_requested,
        "best_conformer_id": best_conf_id,
        "conformers": conformer_rows,
    }
    ensemble_path = run_dir / "conformer_ensemble.json"
    ensemble_path.write_text(json.dumps(ensemble_payload, indent=2), encoding="utf-8")
    generated.append("conformer_ensemble.json")

    msg = "RDKit generation completed"
    return ToolResult(status="ok", message=msg, cwd=str(run_dir), generated_files=sorted(set(generated)), tool_calls=[_record("ok", run_dir, msg)])
